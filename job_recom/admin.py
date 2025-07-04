from django.contrib import admin

from .models import Company, Job, UserProfile, JobInteraction

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ['name', 'industry', 'location', 'size']
    list_filter = ['industry', 'size']
    search_fields = ['name', 'industry', 'location']

@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ['title', 'company', 'location', 'experience_level', 'job_type', 'is_active', 'posted_date']
    list_filter = ['experience_level', 'job_type', 'is_active', 'company__industry']
    search_fields = ['title', 'company__name', 'skills_required']
    date_hierarchy = 'posted_date'

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'experience_years', 'preferred_location', 'preferred_job_type']
    list_filter = ['preferred_job_type', 'preferred_remote']
    search_fields = ['user__username', 'skills']

@admin.register(JobInteraction)
class JobInteractionAdmin(admin.ModelAdmin):
    list_display = ['user', 'job', 'interaction_type', 'rating', 'timestamp']
    list_filter = ['interaction_type', 'rating']
    search_fields = ['user__username', 'job__title']
    date_hierarchy = 'timestamp'
