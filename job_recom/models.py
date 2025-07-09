from django.db import models

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.urls import reverse

class Company(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    industry = models.CharField(max_length=100)
    location = models.CharField(max_length=200)
    size = models.CharField(max_length=50, choices=[
        ('startup', 'Startup (1-50)'),
        ('medium', 'Medium (51-500)'),
        ('large', 'Large (501-5000)'),
        ('enterprise', 'Enterprise (5000+)')
    ])
    
    class Meta:
        verbose_name_plural = "Companies"
    
    def __str__(self):
        return self.name

class Job(models.Model):
    title = models.CharField(max_length=200)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    description = models.TextField()
    requirements = models.TextField()
    skills_required = models.TextField(help_text="Comma-separated skills")
    experience_level = models.CharField(max_length=20, choices=[
        ('entry', 'Entry Level'),
        ('mid', 'Mid Level'),
        ('senior', 'Senior Level'),
        ('lead', 'Lead/Principal')
    ])
    salary_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    salary_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    job_type = models.CharField(max_length=20, choices=[
        ('full_time', 'Full Time'),
        ('part_time', 'Part Time'),
        ('contract', 'Contract'),
        ('internship', 'Internship')
    ])
    remote_option = models.BooleanField(default=False)
    location = models.CharField(max_length=200)
    posted_date = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-posted_date']
    
    def __str__(self):
        return f"{self.title} at {self.company.name}"
    
    def get_absolute_url(self):
        return reverse('job_detail', args=[str(self.id)])
    
    def get_skills_list(self):
        return [skill.strip() for skill in self.skills_required.split(',')]

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    skills = models.TextField(help_text="Comma-separated skills")
    experience_years = models.IntegerField(default=0)
    preferred_location = models.CharField(max_length=200, blank=True)
    preferred_salary_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    preferred_job_type = models.CharField(max_length=20, choices=[
        ('full_time', 'Full Time'),
        ('part_time', 'Part Time'),
        ('contract', 'Contract'),
        ('internship', 'Internship')
    ], blank=True)
    preferred_remote = models.BooleanField(default=False)
    bio = models.TextField(blank=True)
    
    def __str__(self):
        return f"Profile of {self.user.username}"
    
    def get_skills_list(self):
        return [skill.strip() for skill in self.skills.split(',')]

class JobInteraction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    job = models.ForeignKey(Job, on_delete=models.CASCADE)
    interaction_type = models.CharField(max_length=20, choices=[
        ('view', 'View'),
        ('apply', 'Apply'),
        ('save', 'Save'),
    ])
    rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True, blank=True,
        help_text="Rating from 1 to 5"
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['user', 'job', 'interaction_type']
    
    def __str__(self):
        return f"{self.user.username} {self.interaction_type} {self.job.title}"
