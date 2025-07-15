from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Avg, Count
from django.http import Http404
from .models import Job, UserProfile, JobInteraction, Company, User
from django.contrib.auth.views import LoginView, LogoutView
#from .  import JobRecommendationEngine
#from .forms import UserProfileForm, JobSearchForm, JobRatingForm
from django.urls import reverse_lazy
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.forms import UserCreationForm
from django.views.generic.edit import CreateView

def home(request):
    """Home page with featured jobs"""
    featured_jobs = Job.objects.filter(is_active=True).select_related('company')[:6]
    latest_jobs = Job.objects.filter(is_active=True).select_related('company')[:8]
    
    context = {
        'featured_jobs': featured_jobs,
        'latest_jobs': latest_jobs,
        'total_jobs': Job.objects.filter(is_active=True).count(),
        'total_companies': Company.objects.count(),
    }
    return render(request, 'home.html', context)




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
                Q(skills_required__icontains=search_query) |
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
    return render(request, 'jobs/job_list.html', context)

def job_detail(request, job_id):
    """Job detail page with interaction tracking"""
    job = get_object_or_404(Job, id=job_id, is_active=True)
    
    # Record view interaction for authenticated users
    if request.user.is_authenticated:
        JobInteraction.objects.get_or_create(
            user=request.user,
            job=job,
            interaction_type='view'
        )
        
        # Get user's existing rating
        user_rating = JobInteraction.objects.filter(
            user=request.user,
            job=job,
            rating__isnull=False
        ).first()
        
        # Get similar jobs using content-based filtering
        engine = JobRecommendationEngine()
        similar_jobs_data = engine.content_based_recommendations(request.user.id, 5)
        similar_job_ids = [rec['job_id'] for rec in similar_jobs_data]
        similar_jobs = Job.objects.filter(id__in=similar_job_ids).select_related('company')
    else:
        user_rating = None
        similar_jobs = Job.objects.filter(
            company=job.company,
            is_active=True
        ).exclude(id=job.id)[:3]
    
    # Handle rating form submission
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
        'skills_list': job.get_skills_list(),
    }
    return render(request, 'jobs/job_detail.html', context)

@login_required
def recommendations(request):
    """User's personalized job recommendations"""
    recommendation_type = request.GET.get('type', 'hybrid')
    
    engine = JobRecommendationEngine()
    
    if recommendation_type == 'content':
        recommendations_data = engine.content_based_recommendations(request.user.id, 10)
        job_ids = [rec['job_id'] for rec in recommendations_data]
        jobs = Job.objects.filter(id__in=job_ids).select_related('company')
        
        # Add scores to jobs
        job_scores = {rec['job_id']: rec['similarity_score'] for rec in recommendations_data}
        for job in jobs:
            job.score = job_scores.get(job.id, 0)
            job.rec_type = 'Content-Based'
    
    elif recommendation_type == 'collaborative':
        recommendations_data = engine.collaborative_filtering_recommendations(request.user.id, 10)
        job_ids = [rec['job_id'] for rec in recommendations_data]
        jobs = Job.objects.filter(id__in=job_ids).select_related('company')
        
        job_scores = {rec['job_id']: rec['predicted_rating'] for rec in recommendations_data}
        for job in jobs:
            job.score = job_scores.get(job.id, 0)
            job.rec_type = 'Collaborative'
    
    else:  # hybrid
        recommendations_data = engine.hybrid_recommendations(request.user.id, 10)
        job_ids = [rec[0] for rec in recommendations_data]
        jobs = Job.objects.filter(id__in=job_ids).select_related('company')
        
        job_scores = {rec[0]: rec[1] for rec in recommendations_data}
        for job in jobs:
            scores = job_scores.get(job.id, {})
            job.score = scores.get('hybrid_score', 0)
            job.content_score = scores.get('content_score', 0)
            job.collab_score = scores.get('collab_score', 0)
            job.rec_type = 'Hybrid'
    
    # Sort jobs by score
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
    
    # Get user's job interactions
    interactions = JobInteraction.objects.filter(
        user=request.user
    ).select_related('job', 'job__company').order_by('-timestamp')[:10]
    
    context = {
        'form': form,
        'interactions': interactions,
        'user_profile': user_profile,
    }
    return render(request, 'jobs/profile.html', context)

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
    return render(request, 'jobs/saved_jobs.html', context)

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
    authentication_form = AuthenticationForm

class CustomLogoutView(LogoutView):
    next_page = reverse_lazy('login')  # Redirect to login page after logout
    template_name = 'templates/index.html'  # Your logged out template

class RegisterView(CreateView):
    form_class = UserCreationForm
    template_name = 'register.html'
    success_url = reverse_lazy('login')

def about(request):
    return render(request, 'about.html')