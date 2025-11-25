from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Job, UserProfile, JobInteraction, Company, User
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.views.generic.edit import CreateView
from .forms import UserRegistrationForm
from .models import UserProfile 
from django.contrib.auth.views import PasswordChangeView
from django.contrib import messages
from .management.commands.recommendation import JobRecommendationEngine
from django.views.decorators.csrf import csrf_exempt
import json
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from .models import Job, JobRating
from datetime import date
from .forms import UserProfileForm, JobSearchForm, JobRatingForm
from django.shortcuts import render
from .recommendation_engine import JobRecommendationEngine
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
@login_required
def dashboard(request):
    engine = JobRecommendationEngine()
    engine.build_user_item_matrix()
    engine.build_content_features()

    user = request.user
    user_id = user.id

    # Get recommendations
    content_recs = engine.content_based_recommendations(user_id, 50)  # get more for pagination
    collab_recs = engine.collaborative_filtering_recommendations(user_id, 50)
    hybrid_recs = engine.hybrid_recommendations(user_id, 50)

    if not hybrid_recs:
        messages.info(
            request,
            "No recommendations available yet. Update your skills or rate jobs to get personalized recommendations."
        )
    def extract_jobs_with_scores(recs):
        scores_dict = {}
        for rec in recs:
            if isinstance(rec, dict):
                job_id = rec.get('job_id')
                score = rec.get('similarity_score') or rec.get('predicted_rating', 0)
                scores_dict[job_id] = round(score, 4)
            elif isinstance(rec, (tuple, list)) and len(rec) >= 1:
                job_id = rec[0]
                score = rec[1].get('hybrid_score', 0)
                scores_dict[job_id] = round(score, 4)

        # Only jobs with scores
        jobs = Job.objects.filter(id__in=scores_dict.keys(), is_active=True).order_by('-deadline')
        jobs_with_scores = []

        for job in jobs:
            job.score = scores_dict[job.id]
            job.is_saved = job.jobinteraction_set.filter(
                user=request.user,
                interaction_type='save'
            ).exists()
            jobs_with_scores.append(job)

        return jobs_with_scores

    content_jobs_list = extract_jobs_with_scores(content_recs)
    collab_jobs_list = extract_jobs_with_scores(collab_recs)
    hybrid_jobs_list = extract_jobs_with_scores(hybrid_recs)

    # ---------------- Pagination ----------------
    def paginate_jobs(job_list, page_param):
        paginator = Paginator(job_list, 6)  # 6 jobs per page
        page_number = request.GET.get(page_param, 1)
        return paginator.get_page(page_number)

    context = {
        'content_jobs': paginate_jobs(content_jobs_list, 'content_page'),
        'collab_jobs': paginate_jobs(collab_jobs_list, 'collab_page'),
        'hybrid_jobs': paginate_jobs(hybrid_jobs_list, 'hybrid_page'),
    }

    return render(request, 'dashboard.html', context)

@login_required
def job_list(request):
    """List all jobs with search and filtering"""
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
                Q(required_skills__icontains=search_query) | 
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
        'today': date.today()
    }
    return render(request, 'browse_jobs.html', context)

@login_required
def job_detail(request, job_id):
    job = get_object_or_404(Job, id=job_id, is_active=True)

    # Track view
    JobInteraction.objects.get_or_create(
        user=request.user,
        job=job,
        interaction_type='view'
    )

    # Saved & Applied status
    job.is_saved = JobInteraction.objects.filter(
        user=request.user, job=job, interaction_type='save'
    ).exists()
    job.is_applied = JobInteraction.objects.filter(
        user=request.user, job=job, interaction_type='apply'
    ).exists()

    # User rating
    user_rating_obj = JobInteraction.objects.filter(
        user=request.user, job=job, rating__isnull=False
    ).first()
    user_rating = user_rating_obj.rating if user_rating_obj else 0  # default 0 if not rated

    # Handle rating POST
    if request.method == 'POST' and 'rating' in request.POST:
        rating = int(request.POST['rating'])
        interaction, created = JobInteraction.objects.get_or_create(
            user=request.user, job=job, interaction_type='rating',
            defaults={'rating': rating}
        )
        if not created:
            interaction.rating = rating
            interaction.save()
        messages.success(request, 'Your rating has been saved!')
        return redirect('job_detail', job_id=job.id)

    context = {
        'job': job,
        'user_rating': user_rating,
        'skills_list': job.required_skills.split(',') if job.required_skills else [],
        'today': date.today(),
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
        request.user.first_name = request.POST.get("first_name")
        request.user.last_name = request.POST.get("last_name")
        request.user.save()

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
    search_query = request.GET.get('search_query', '')
    location = request.GET.get('location', '')
    salary_range = request.GET.get('salary_range', '')

    jobs = Job.objects.filter(is_active=True)

    if search_query:
        jobs = jobs.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(company__name__icontains=search_query) |
            Q(required_skills__icontains=search_query)
        )

    if location:
        jobs = jobs.filter(location__icontains=location)

    if salary_range:
        parts = salary_range.split('-')
        try:
            if len(parts) == 2:
                min_salary = float(parts[0])
                max_salary = float(parts[1])
                jobs = jobs.filter(salary__gte=min_salary, salary__lte=max_salary)
            elif len(parts) == 1:
                min_salary = float(parts[0])
                jobs = jobs.filter(salary__gte=min_salary)
        except ValueError:
            pass

    paginator = Paginator(jobs, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'location': location,
        'salary_range': salary_range,
    }

    return render(request, 'browse_jobs.html', context)

@login_required
@csrf_exempt
def save_job_ajax(request):
    if request.method == "POST":
        data = json.loads(request.body)
        job_id = data.get("job_id")
        job = get_object_or_404(Job, id=job_id, is_active=True)

        interaction, created = JobInteraction.objects.get_or_create(
            user=request.user,
            job=job,
            interaction_type='save'
        )

        if not created:
            interaction.delete()
            return JsonResponse({"status": "unsaved"})
        return JsonResponse({"status": "saved"})

    return JsonResponse({"error": "Invalid request"}, status=400)



@csrf_exempt
def rate_job_ajax(request):
    if request.method == "POST":
        data = json.loads(request.body)
        job_id = data.get("job_id")
        rating_value = data.get("rating")
        user = request.user

        if not user.is_authenticated:
            return JsonResponse({"status": "error", "message": "Login required"})

        try:
            job = Job.objects.get(id=job_id)
        except Job.DoesNotExist:
            return JsonResponse({"status": "error", "message": "Job not found"})

        rating_obj, created = JobRating.objects.get_or_create(user=user, job=job)
        rating_obj.rating = rating_value
        rating_obj.save()

        return JsonResponse({"status": "rated"})
    
def extract_jobs_with_scores(recs, user):
    """
    Takes a list of recommendation dicts and returns Job objects with attached scores.
    """
    jobs_with_scores = []
    job_ids = []
    scores_dict = {}

    for rec in recs:
        if isinstance(rec, dict):
            job_id = rec.get('job_id')
            score = rec.get('similarity_score') or rec.get('predicted_rating', 0)
        elif isinstance(rec, (tuple, list)) and len(rec) >= 1:
            job_id = rec[0]
            score = rec[1].get('hybrid_score', 0)
        else:
            continue
        job_ids.append(job_id)
        scores_dict[job_id] = round(score, 4)

    jobs = Job.objects.filter(id__in=job_ids, is_active=True).select_related('company')
    job_dict = {job.id: job for job in jobs}

    for job_id in job_ids:
        if job_id in job_dict:
            job = job_dict[job_id]
            job.score = scores_dict[job_id]
            # Optional: attach saved status
            job.is_saved = job.jobinteraction_set.filter(
                user=user,
                interaction_type='save'
            ).exists()
            jobs_with_scores.append(job)

    return jobs_with_scores


@login_required
@csrf_exempt
def rate_job_ajax(request):
    if request.method == "POST":
        data = json.loads(request.body)
        job_id = data.get("job_id")
        rating = data.get("rating")

        try:
            job = Job.objects.get(id=job_id)
        except Job.DoesNotExist:
            return JsonResponse({"status": "error", "message": "Job not found"}, status=404)

        # Get or create rating, update if exists
        interaction, created = JobInteraction.objects.get_or_create(
            user=request.user,
            job=job,
            interaction_type='rating',  # Important!
            defaults={"rating": rating}
        )

        if not created:
            interaction.rating = rating
            interaction.save()

        return JsonResponse({"status": "rated", "rating": interaction.rating})
    return JsonResponse({"status": "error", "message": "Invalid request"}, status=400)


@login_required
def hybrid_recommendations_ajax(request):
    engine = JobRecommendationEngine()
    recommendations = engine.hybrid_recommendations(request.user.id, num_recommendations=5)
    data = [
        {"job_id": jid, "hybrid_score": score_dict["hybrid_score"]}
        for jid, score_dict in recommendations
    ]
    return JsonResponse({"recommendations": data})