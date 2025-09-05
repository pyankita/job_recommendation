from django.apps import AppConfig


class JobRecomConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'job_recom'

    def ready(self):
        # Import the signals module to register signal handlers
        import job_recom.signals