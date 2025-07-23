from django import forms
from .models import UserProfile, Job
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    # Additional fields from UserProfile
    skills = forms.CharField(widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'e.g., Python, Django'}), required=False)
    experience_years = forms.IntegerField(min_value=0, required=False)
    preferred_location = forms.CharField(max_length=200, required=False)
    preferred_salary_min = forms.DecimalField(max_digits=10, decimal_places=2, required=False)
    preferred_remote = forms.BooleanField(required=False)
    bio = forms.CharField(widget=forms.Textarea(attrs={'rows': 4, 'placeholder': 'Tell us about yourself...'}), required=False)

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2', 
                  'skills', 'experience_years', 'preferred_location',
                  'preferred_salary_min', 'preferred_remote', 'bio']

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = [
            'skills', 'experience_years', 'preferred_location',
            'preferred_salary_min', 
            'preferred_remote', 'bio'
        ]
        widgets = {
            'skills': forms.Textarea(attrs={'rows': 3, 'placeholder': 'e.g., Python, Django, React, Machine Learning'}),
            'bio': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Tell us about yourself...'}),
            'preferred_location': forms.TextInput(attrs={'placeholder': 'e.g., San Francisco, CA'}),
            'preferred_salary_min': forms.NumberInput(attrs={'placeholder': 'Minimum salary expectation'}),
        }

class JobSearchForm(forms.Form):
    search_query = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Search jobs, skills, or companies...'})
    )
    location = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Location'})
    )
    # job_type = forms.ChoiceField(
    #     required=False,
    #     choices=[('', 'All Types')] + Job._meta.get_field('job_type').choices
    # )
    # experience_level = forms.ChoiceField(
    #     required=False,
    #     choices=[('', 'All Levels')] + Job._meta.get_field('experience_level').choices
    # )

class JobRatingForm(forms.Form):
    rating = forms.IntegerField(
        min_value=1,
        max_value=5,
        widget=forms.NumberInput(attrs={'min': 1, 'max': 5})
    )


