import re
from collections import defaultdict
import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from django.contrib.auth.models import User
from .models import Job, UserProfile, JobInteraction


# ================================================================
# DISPLAY FUNCTION — VIEWING USER + JOB RECOMMENDATION DETAILS
# ================================================================
def display_recommendation_details(user_id, engine, recommendation_type="content"):
    """
    Displays recommendation details such as:
    - user info
    - user profile vector
    - recommended job titles, job vectors, and similarity/prediction scores
    """

    try:
        user = User.objects.get(id=user_id)
        user_profile = UserProfile.objects.get(user_id=user_id)
    except (User.DoesNotExist, UserProfile.DoesNotExist):
        print(f"User with ID {user_id} not found.")
        return

    print("\n===================================================")
    print(f"User: {user.username}")
    print(f"Skills: {user_profile.skills}")
    print("===================================================")

    # Ensure TF-IDF model is built
    if engine.job_features_matrix is None:
        engine.build_content_features()

    # --- USER VECTOR ---
    user_vector = engine.get_user_profile_vector(user_profile)
    print("\nUser Input Vector:")
    print(user_vector.toarray())
    print("")

    # --- GET RECOMMENDATIONS ---
    if recommendation_type == "content":
        recommendations = engine.content_based_recommendations(user_id, num_recommendations=5)
    elif recommendation_type == "collaborative":
        recommendations = engine.collaborative_filtering_recommendations(user_id, num_recommendations=5)
    else:
        recommendations = engine.hybrid_recommendations(user_id, num_recommendations=5)

    # --- PRINT JOB DETAILS ---
    for idx, rec in enumerate(recommendations, start=1):
        job = Job.objects.get(id=rec['job_id']) if isinstance(rec, dict) else Job.objects.get(id=rec[0])
        job_vector = engine.tfidf_vectorizer.transform([
            engine.extract_job_features(job)
        ])

        print(f"\n🔹 Job {idx}: {job.title}")
        print("Job Vector:")
        print(job_vector.toarray())

        # Display scoring
        if isinstance(rec, dict):
            if 'similarity_score' in rec:
                print(f"Similarity Score: {rec['similarity_score']:.4f}")
            if 'predicted_rating' in rec:
                print(f"Predicted Rating: {rec['predicted_rating']:.4f}")
        elif isinstance(rec, tuple):
            print(f"Hybrid Score: {rec[1]['hybrid_score']:.4f}")

    print("\n===================================================\n")


# ================================================================
# JOB RECOMMENDATION ENGINE CLASS
# ================================================================
class JobRecommendationEngine:
    """
    Job Recommendation Engine using three approaches:
    1 Content-based filtering (TF-IDF + cosine similarity)
    2 Collaborative filtering (Pearson correlation)
    3 Hybrid approach (combines both)
    """

    def __init__(self):
        self.tfidf_vectorizer = TfidfVectorizer(
            max_features=5000,
            stop_words='english',
            ngram_range=(1, 2)
        )
        self.job_features_matrix = None
        self.job_ids = None
        self.user_job_ratings = None

    # ------------------------------------------------------------
    # TEXT PREPROCESSING
    # ------------------------------------------------------------
    def preprocess_text(self, text):
        """Cleans text by removing special characters and converting to lowercase."""
        if not text:
            return ""
        return re.sub(r'[^a-zA-Z\s]', '', str(text).lower())

    # ------------------------------------------------------------
    # JOB FEATURE EXTRACTION
    # ------------------------------------------------------------
    def extract_job_features(self, job):
        """Extracts combined text features from a job record."""
        features = [
            self.preprocess_text(job.title),
            self.preprocess_text(job.description),
            self.preprocess_text(job.requirements),
        ]

        # Include skills if available
        if getattr(job, 'required_skills', None):
            skills = job.required_skills.split(',')
            skills_text = ' '.join([skill.strip() for skill in skills] * 2)
            features.append(self.preprocess_text(skills_text))

        # Include company and industry info
        if job.company:
            features.append(self.preprocess_text(job.company.name))
            if hasattr(job.company, 'industry'):
                features.append(self.preprocess_text(job.company.industry))

        # Optional: add job type or experience level if available
        if hasattr(job, 'experience_level'):
            features.append(str(job.experience_level))
        if hasattr(job, 'job_type'):
            features.append(str(job.job_type))

        features.append(self.preprocess_text(job.location or ""))

        return ' '.join(features)

    # ------------------------------------------------------------
    # CONTENT-BASED FILTERING
    # ------------------------------------------------------------
    def build_content_features(self):
        """Builds TF-IDF matrix for all active jobs."""
        jobs = Job.objects.filter(is_active=True).select_related('company')
        job_features = []
        job_ids = []

        for job in jobs:
            job_features.append(self.extract_job_features(job))
            job_ids.append(job.id)

        if job_features:
            self.job_features_matrix = self.tfidf_vectorizer.fit_transform(job_features)
            self.job_ids = job_ids

        return self.job_features_matrix, self.job_ids

    def get_user_profile_vector(self, user_profile):
        """Builds TF-IDF vector for the user's profile."""
        features = []

        if user_profile.skills:
            skills = user_profile.skills.split(',')
            skills_text = ' '.join([skill.strip() for skill in skills] * 3)
            features.append(self.preprocess_text(skills_text))

        features.append(self.preprocess_text(user_profile.bio))
        features.append(self.preprocess_text(user_profile.preferred_location))

        user_features_text = ' '.join(features)

        if self.job_features_matrix is None:
            self.build_content_features()

        return self.tfidf_vectorizer.transform([user_features_text])

    def content_based_recommendations(self, user_id, num_recommendations=10):
        """Generates job recommendations using cosine similarity."""
        try:
            user_profile = UserProfile.objects.get(user_id=user_id)
        except UserProfile.DoesNotExist:
            return []

        if self.job_features_matrix is None:
            self.build_content_features()

        user_vector = self.get_user_profile_vector(user_profile)
        similarities = cosine_similarity(user_vector, self.job_features_matrix).flatten()

        interacted_jobs = JobInteraction.objects.filter(user_id=user_id).values_list('job_id', flat=True)

        recommendations = [
            {'job_id': job_id, 'similarity_score': sim, 'recommendation_type': 'content_based'}
            for job_id, sim in zip(self.job_ids, similarities)
            if job_id not in interacted_jobs
        ]

        recommendations.sort(key=lambda x: x['similarity_score'], reverse=True)
        return recommendations[:num_recommendations]

    # ------------------------------------------------------------
    # COLLABORATIVE FILTERING
    # ------------------------------------------------------------
    def build_user_item_matrix(self):
        """Builds user-item matrix from JobInteraction ratings."""
        interactions = JobInteraction.objects.filter(rating__isnull=False).values('user_id', 'job_id', 'rating')

        if not interactions:
            return None

        df = pd.DataFrame(interactions)
        user_item_matrix = df.pivot_table(
            index='user_id',
            columns='job_id',
            values='rating',
            fill_value=0
        )

        self.user_job_ratings = user_item_matrix
        return user_item_matrix

    def calculate_user_similarity(self, user_id, other_user_id):
        """Calculates Pearson correlation between two users."""
        if self.user_job_ratings is None:
            return 0

        if user_id not in self.user_job_ratings.index or other_user_id not in self.user_job_ratings.index:
            return 0

        user1_ratings = self.user_job_ratings.loc[user_id]
        user2_ratings = self.user_job_ratings.loc[other_user_id]

        common_jobs = (user1_ratings != 0) & (user2_ratings != 0)
        if common_jobs.sum() < 2:
            return 0

        try:
            correlation, _ = pearsonr(user1_ratings[common_jobs], user2_ratings[common_jobs])
            return correlation if not np.isnan(correlation) else 0
        except Exception:
            return 0

    def collaborative_filtering_recommendations(self, user_id, num_recommendations=10):
        """Generates recommendations using user-user collaborative filtering."""
        user_item_matrix = self.build_user_item_matrix()
        if user_item_matrix is None or user_id not in user_item_matrix.index:
            return []

        user_similarities = {}
        for other_user_id in user_item_matrix.index:
            if other_user_id != user_id:
                sim = self.calculate_user_similarity(user_id, other_user_id)
                if sim > 0:
                    user_similarities[other_user_id] = sim

        if not user_similarities:
            return []

        target_user_ratings = user_item_matrix.loc[user_id]
        unrated_jobs = target_user_ratings[target_user_ratings == 0].index

        job_scores = defaultdict(float)
        similarity_sums = defaultdict(float)

        for other_user_id, sim in user_similarities.items():
            ratings = user_item_matrix.loc[other_user_id]
            for job_id in unrated_jobs:
                if ratings[job_id] > 0:
                    job_scores[job_id] += sim * ratings[job_id]
                    similarity_sums[job_id] += abs(sim)

        recommendations = []
        for job_id, score in job_scores.items():
            if similarity_sums[job_id] > 0:
                predicted = score / similarity_sums[job_id]
                recommendations.append({
                    'job_id': job_id,
                    'predicted_rating': predicted,
                    'recommendation_type': 'collaborative'
                })

        recommendations.sort(key=lambda x: x['predicted_rating'], reverse=True)
        return recommendations[:num_recommendations]

    # ------------------------------------------------------------
    # HYBRID RECOMMENDATION
    # ------------------------------------------------------------
    def hybrid_recommendations(self, user_id, num_recommendations=5):
        """
        Combines content-based and collaborative approaches:
        - For new users (no ratings), falls back to content-based.
        - Otherwise, averages scores from both.
        """
        self.build_user_item_matrix()

        if self.user_job_ratings is None or user_id not in self.user_job_ratings.index:
            print(f"🧊 Cold start for user {user_id}: using content-based only.")
            return self.content_based_recommendations(user_id, num_recommendations)

        collab_recs = self.collaborative_filtering_recommendations(user_id, num_recommendations * 2)
        content_recs = self.content_based_recommendations(user_id, num_recommendations * 2)

        collab_dict = {r['job_id']: r for r in collab_recs}
        content_dict = {r['job_id']: r for r in content_recs}

        hybrid_recs = []
        added = set()

        # Combine common jobs
        for job_id in (set(collab_dict) & set(content_dict)):
            hybrid_score = (collab_dict[job_id]['predicted_rating'] +
                            content_dict[job_id]['similarity_score']) / 2
            hybrid_recs.append((job_id, {'hybrid_score': hybrid_score}))
            added.add(job_id)

        # Add remaining from content
        for job_id, rec in content_dict.items():
            if job_id not in added:
                hybrid_recs.append((job_id, {'hybrid_score': rec['similarity_score']}))
                added.add(job_id)

        # Add remaining from collaborative
        for job_id, rec in collab_dict.items():
            if job_id not in added:
                hybrid_recs.append((job_id, {'hybrid_score': rec['predicted_rating']}))

        hybrid_recs.sort(key=lambda x: x[1]['hybrid_score'], reverse=True)
        return hybrid_recs[:num_recommendations]
