from django import forms
from .models import UserProfile, Job

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


