from django.contrib import admin

from .models import Company, Job, UserProfile, JobInteraction

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ['name', 'industry', 'location', 'size']
    list_filter = ['industry', 'size']
    search_fields = ['name', 'industry', 'location']

@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    # Use only fields that exist on Job model
    list_display = ['title', 'company', 'location', 'category', 'created_date', 'deadline']
    list_filter = ['category', 'location', 'company']
    search_fields = ['title', 'company__name', 'required_skills', 'description']
    # Use a valid date field for hierarchy, e.g. created_date
    date_hierarchy = 'created_date'

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'experience_years', 'preferred_location']
    list_filter = [ 'preferred_remote']
    search_fields = ['user__username', 'skills']

@admin.register(JobInteraction)
class JobInteractionAdmin(admin.ModelAdmin):
    list_display = ['user', 'job', 'interaction_type', 'rating', 'timestamp']
    list_filter = ['interaction_type', 'rating']
    search_fields = ['user__username', 'job__title']
    date_hierarchy = 'timestamp'
