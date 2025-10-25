from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Job, UserProfile, JobInteraction, Company, User
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.views.generic.edit import CreateView
from .forms import UserRegistrationForm
from .models import UserProfile 
from django.contrib.auth.views import PasswordChangeView
from django.contrib import messages
#Import your recommendation engine class (adjust path if needed)
from .management.commands.recommendation import JobRecommendationEngine

# Uncomment and import your forms if you have them:
from .forms import UserProfileForm, JobSearchForm, JobRatingForm

from django.shortcuts import render
from .recommendation_engine import JobRecommendationEngine
from .models import Job  # Adjust this import if your Job model is elsewhere


@login_required
def dashboard(request):
    engine = JobRecommendationEngine()
    engine.build_user_item_matrix()
    engine.build_content_features()

    user = request.user
    user_id = user.id

    # --- Hybrid Recommendations (Primary) ---
    recs = engine.hybrid_recommendations(user_id, 6)

    # --- Fallback to Content-based ---
    if not recs:
        print("[DEBUG] Hybrid recommendations returned nothing. Falling back to content-based.")
        recs = engine.content_based_recommendations(user_id, 6)

    print("[DEBUG] Final Recommendations:", recs)

    # --- Extract job IDs properly ---
    job_ids = []
    try:
        for rec in recs:
            if isinstance(rec, dict):  # content-based fallback returns dicts
                job_ids.append(rec.get('job_id'))
            elif isinstance(rec, (tuple, list)) and len(rec) >= 1:  # hybrid returns tuples
                job_ids.append(rec[0])
    except Exception as e:
        print("[ERROR] Recommendation unpacking failed:", e)

    # --- Fetch jobs from DB ---
    jobs = Job.objects.filter(id__in=job_ids, is_active=True)

    # Maintain order of recommendations
    job_dict = {job.id: job for job in jobs}
    ordered_jobs = [job_dict[job_id] for job_id in job_ids if job_id in job_dict]

    # --- Add is_saved flag for each job ---
    for job in ordered_jobs:
        job.is_saved = False
        if request.user.is_authenticated:
            job.is_saved = job.jobinteraction_set.filter(
                user=request.user,
                interaction_type='save'
            ).exists()

    # --- Render template ---
    context = {
        'recommended_jobs': ordered_jobs,
    }
    return render(request, 'dashboard.html', context)

@login_required
def job_list(request):
    """List all jobs with search and filtering"""
    # Make sure JobSearchForm is imported and exists
    form = JobSearchForm(request.GET or None)
    jobs = Job.objects.filter(is_active=True).select_related('company')

    if form.is_valid():
        search_query = form.cleaned_data.get('search_query')
        location = form.cleaned_data.get('location')
        job_type = form.cleaned_data.get('job_type')
        experience_level = form.cleaned_data.get('experience_level')

        if search_query:
            jobs = jobs.filter(
                Q(title__icontains=search_query) |
                Q(description__icontains=search_query) |
                Q(required_skills__icontains=search_query) |  # Fixed field name as per your model
                Q(company__name__icontains=search_query)
            )

        if location:
            jobs = jobs.filter(location__icontains=location)

        if job_type:
            jobs = jobs.filter(job_type=job_type)

        if experience_level:
            jobs = jobs.filter(experience_level=experience_level)

    paginator = Paginator(jobs, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'form': form,
        'page_obj': page_obj,
        'total_jobs': jobs.count(),
    }
    return render(request, 'browse_jobs.html', context)

@login_required
def job_detail(request, job_id):
    """Job detail page with interaction tracking"""
    job = get_object_or_404(Job, id=job_id, is_active=True)

    if request.user.is_authenticated:
        JobInteraction.objects.get_or_create(
            user=request.user,
            job=job,
            interaction_type='view'
        )

        user_rating = JobInteraction.objects.filter(
            user=request.user,
            job=job,
            rating__isnull=False
        ).first()

        engine = JobRecommendationEngine()
        similar_jobs_data = engine.content_based_recommendations(request.user.id, 5)
        similar_job_ids = [rec['job_id'] for rec in similar_jobs_data]
        similar_jobs = Job.objects.filter(id__in=similar_job_ids, is_active=True).select_related('company')

    else:
        user_rating = None
        similar_jobs = Job.objects.filter(
            company=job.company,
            is_active=True
        ).exclude(id=job.id)[:3]

    # Handle rating form submission (make sure JobRatingForm is imported)
    if request.method == 'POST' and request.user.is_authenticated:
        form = JobRatingForm(request.POST)
        if form.is_valid():
            rating = form.cleaned_data['rating']
            interaction, created = JobInteraction.objects.get_or_create(
                user=request.user,
                job=job,
                interaction_type='like',
                defaults={'rating': rating}
            )
            if not created:
                interaction.rating = rating
                interaction.save()

            messages.success(request, 'Your rating has been saved!')
            return redirect('job_detail', job_id=job.id)
    else:
        form = JobRatingForm(initial={'rating': user_rating.rating if user_rating else None})

    context = {
        'job': job,
        'similar_jobs': similar_jobs,
        'form': form,
        'user_rating': user_rating,
        'skills_list': job.required_skills.split(',') if job.required_skills else [],
    }
    return render(request, 'job_detail.html', context)

@login_required
def recommendations(request):
    """User's personalized job recommendations"""
    recommendation_type = request.GET.get('type', 'hybrid')

    engine = JobRecommendationEngine()

    if recommendation_type == 'content':
        recommendations_data = engine.content_based_recommendations(request.user.id, 10)
        job_ids = [rec['job_id'] for rec in recommendations_data]
        jobs = Job.objects.filter(id__in=job_ids, is_active=True).select_related('company')

        job_scores = {rec['job_id']: rec['similarity_score'] for rec in recommendations_data}
        for job in jobs:
            job.score = job_scores.get(job.id, 0)
            job.rec_type = 'Content-Based'

    elif recommendation_type == 'collaborative':
        recommendations_data = engine.collaborative_filtering_recommendations(request.user.id, 10)
        job_ids = [rec['job_id'] for rec in recommendations_data]
        jobs = Job.objects.filter(id__in=job_ids, is_active=True).select_related('company')

        job_scores = {rec['job_id']: rec['predicted_rating'] for rec in recommendations_data}
        for job in jobs:
            job.score = job_scores.get(job.id, 0)
            job.rec_type = 'Collaborative'

    else:  # hybrid
        recommendations_data = engine.hybrid_recommendations(request.user.id, 10)
        job_ids = [rec[0] for rec in recommendations_data]
        jobs = Job.objects.filter(id__in=job_ids, is_active=True).select_related('company')

        job_scores = {rec[0]: rec[1] for rec in recommendations_data}
        for job in jobs:
            scores = job_scores.get(job.id, {})
            job.score = scores.get('hybrid_score', 0)
            job.content_score = scores.get('content_score', 0)
            job.collab_score = scores.get('collab_score', 0)
            job.rec_type = 'Hybrid'

    jobs = sorted(jobs, key=lambda x: x.score, reverse=True)

    context = {
        'jobs': jobs,
        'recommendation_type': recommendation_type,
        'has_profile': hasattr(request.user, 'userprofile'),
    }
    return render(request, 'jobs/recommendations.html', context)

@login_required
def profile(request):
    """User profile management"""
    try:
        user_profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        user_profile = None

    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=user_profile)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.user = request.user
            profile.save()
            messages.success(request, 'Your profile has been updated!')
            return redirect('profile')
    else:
        form = UserProfileForm(instance=user_profile)

    interactions = JobInteraction.objects.filter(
        user=request.user
    ).select_related('job', 'job__company').order_by('-timestamp')[:10]

    context = {
        'form': form,
        'interactions': interactions,
        'user_profile': user_profile,
    }
    return render(request, 'profile.html', context)



@login_required
def edit_profile(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        # Update User basic info
        request.user.first_name = request.POST.get("first_name")
        request.user.last_name = request.POST.get("last_name")
        request.user.save()

        # Update UserProfile info
        profile.location = request.POST.get("location")
        profile.skills = request.POST.get("skills")
        profile.experience_years = request.POST.get("experience_years") or 0
        profile.preferred_location = request.POST.get("preferred_location")
        profile.preferred_salary_min = request.POST.get("preferred_salary_min") or None
        profile.preferred_remote = request.POST.get("preferred_remote") == "True"
        profile.bio = request.POST.get("bio")
        profile.save()

        return redirect("profile")

    return render(request, "edit_profile.html", {"profile": profile})



@login_required
def save_job(request, job_id):
    """Save/unsave a job"""
    job = get_object_or_404(Job, id=job_id, is_active=True)

    interaction, created = JobInteraction.objects.get_or_create(
        user=request.user,
        job=job,
        interaction_type='save'
    )

    if not created:
        interaction.delete()
        messages.success(request, 'Job removed from saved jobs.')
    else:
        messages.success(request, 'Job saved successfully!')

    return redirect('job_detail', job_id=job.id)

@login_required
def saved_jobs(request):
    """List user's saved jobs"""
    saved_interactions = JobInteraction.objects.filter(
        user=request.user,
        interaction_type='save'
    ).select_related('job', 'job__company').order_by('-timestamp')

    context = {
        'saved_interactions': saved_interactions,
    }
    return render(request, 'saved_jobs.html', context)

@login_required
def apply_job(request, job_id):
    """Apply to a job"""
    job = get_object_or_404(Job, id=job_id, is_active=True)

    interaction, created = JobInteraction.objects.get_or_create(
        user=request.user,
        job=job,
        interaction_type='apply'
    )

    if created:
        messages.success(request, f'Successfully applied to {job.title}!')
    else:
        messages.info(request, 'You have already applied to this job.')

    return redirect('job_detail', job_id=job.id)

class CustomLoginView(LoginView):
    template_name = 'login.html'

    def get_success_url(self):
        return '/dashboard/'

class RegisterView(CreateView):
    form_class = UserRegistrationForm
    template_name = 'register.html'
    success_url = reverse_lazy('home')

class CustomLogoutView(LogoutView):
    next_page = reverse_lazy('home')

class CustomPasswordChangeView(PasswordChangeView):
    template_name = "change_password.html"
    success_url = reverse_lazy("profile")

    def form_valid(self, form):
        messages.success(self.request, "Your password has been successfully updated.")
        return super().form_valid(form)
    
@login_required
def settings(request):
    """User account settings"""
    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = None

    if request.method == "POST":
        profile.dark_mode = request.POST.get("dark_mode") == "on"
        profile.allow_location = request.POST.get("allow_location") == "on"
        profile.save()
        messages.success(request, "Settings updated successfully!")
        return redirect("settings")

    return render(request, "settings.html", {"profile": profile})

    
def about(request):
    return render(request, 'about.html')
def home(request):
    return render(request, 'home.html')

def job(request):
    return render(request, 'browse_jobs.html')