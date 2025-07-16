from django.db import models

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.urls import reverse

class Company(models.Model):
    name = models.CharField(max_length=200,blank=True,null=True)
    description = models.TextField(blank=True,null=True)
    industry = models.CharField(max_length=100,blank=True,null=True)
    location = models.CharField(max_length=200,blank=True,null=True)
    size = models.CharField(max_length=50, choices=[
        ('startup', 'Startup (1-50)'),
        ('medium', 'Medium (51-500)'),
        ('large', 'Large (501-5000)'),
        ('enterprise', 'Enterprise (5000+)')
    ],blank=True,null=True)
    
    class Meta:
        verbose_name_plural = "Companies"
    
    def __str__(self):
        return self.name

class Job(models.Model):
    title = models.CharField(max_length=255,blank=True,null=True)
    description = models.TextField(blank=True,null=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="jobs",blank=True,null=True)  # Link to Company
    location = models.CharField(max_length=255,blank=True,null=True)
    category = models.CharField(max_length=100,blank=True,null=True)
    created_date = models.DateField(blank=True,null=True)
    deadline = models.DateField(blank=True,null=True)
    salary = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(0)],blank=True,null=True)
    requirements = models.TextField(blank=True,null=True)
    responsibilities = models.TextField(blank=True,null=True)
    contact_email = models.EmailField(blank=True,null=True)
    required_skills = models.TextField(blank=True,null=True)
    education_level = models.CharField(max_length=100,blank=True,null=True)
    is_active = models.BooleanField(default=True,blank=True,null=True)

    def __str__(self):
        return f"{self.title} at {self.company.name}"

    @property
    def required_skills_list(self):
        """Converts the required_skills string into a list."""
        return [skill.strip() for skill in self.required_skills.split(',')]

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE,blank=True,null=True)
    skills = models.TextField(help_text="Comma-separated skills",blank=True,null=True)
    experience_years = models.IntegerField(default=0,blank=True,null=True)
    preferred_location = models.CharField(max_length=200,blank=True,null=True)
    preferred_salary_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    preferred_job_type = models.CharField(max_length=20, choices=[
        ('full_time', 'Full Time'),
        ('part_time', 'Part Time'),
        ('contract', 'Contract'),
        ('internship', 'Internship')
    ],blank=True,null=True)
    preferred_remote = models.BooleanField(default=False,blank=True,null=True)
    bio = models.TextField(blank=True,null=True)
    
    def __str__(self):
        return f"Profile of {self.user.username}"
    
    def get_skills_list(self):
        return [skill.strip() for skill in self.skills.split(',')]

class JobInteraction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE,blank=True,null=True)
    job = models.ForeignKey(Job, on_delete=models.CASCADE,blank=True,null=True)
    interaction_type = models.CharField(max_length=20, choices=[
        ('view', 'View'),
        ('apply', 'Apply'),
        ('save', 'Save'),
    ],blank=True,null=True)
    rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True, blank=True,
        help_text="Rating from 1 to 5"
    )
    timestamp = models.DateTimeField(auto_now_add=True,blank=True,null=True)
    
    class Meta:
        unique_together = ['user', 'job', 'interaction_type']
    
    def __str__(self):
        return f"{self.user.username} {self.interaction_type} {self.job.title}"
