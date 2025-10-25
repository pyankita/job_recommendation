from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from .views import CustomPasswordChangeView,save_job_ajax


urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.CustomLogoutView.as_view(), name='logout'),
    path('register/', views.RegisterView.as_view(), name='register'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('about/', views.about, name='about'),
    path('jobs/', views.job_list, name='job_list'),
    path('browse_jobs/', views.job, name='browse_jobs'),
    path('jobs/<int:job_id>/', views.job_detail, name='job_detail'),
    path('recommendations/', views.recommendations, name='recommendations'),
    path('profile/', views.profile, name='profile'),
    path('jobs/<int:job_id>/save/', views.save_job, name='save_job'),
    path('jobs/<int:job_id>/apply/', views.apply_job, name='apply_job'),
    path('saved-jobs/', views.saved_jobs, name='saved_jobs'),
    path("profile/edit/", views.edit_profile, name="edit_profile"),
    path("settings/", views.settings, name="settings"),
    path("change-password/", CustomPasswordChangeView.as_view(), name="change_password"),
    path('save-job-ajax/', save_job_ajax, name='save_job_ajax'),

]