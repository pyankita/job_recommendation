from django.core.management.base import BaseCommand
from job_recom.recommendation_engine import JobRecommendationEngine

class Command(BaseCommand):
    help = "Generate job recommendations for a user"

    def add_arguments(self, parser):
        parser.add_argument('--user_id', type=int, required=True, help="User ID for recommendations")
        parser.add_argument('--num', type=int, default=10, help="Number of recommendations")

    def handle(self, *args, **options):
        user_id = options['user_id']
        num = options['num']

        engine = JobRecommendationEngine()
        recs = engine.hybrid_recommendations(user_id, num)

        for idx, (job_id, scores) in enumerate(recs, start=1):
            self.stdout.write(f"{idx}. Job ID: {job_id} | Hybrid Score: {scores['hybrid_score']:.4f} | Content Score: {scores['content_score']:.4f} | Collab Score: {scores['collab_score']:.4f}")
