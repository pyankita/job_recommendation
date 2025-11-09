import re
from collections import defaultdict
import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from django.contrib.auth.models import User
from .models import Job, UserProfile, JobInteraction


class JobRecommendationEngine:
    """
    Job Recommendation Engine:
    1. Content-based filtering (TF-IDF + cosine similarity)
    2. Collaborative filtering (Pearson correlation)
    3. Hybrid filtering (mean of content + collaborative scores)
    """

    def __init__(self):
        self.tfidf_vectorizer = TfidfVectorizer(stop_words='english')
        self.job_features_matrix = None
        self.job_ids = None
        self.user_job_ratings = None

    @staticmethod
    def preprocess_text(text):
        if not text:
            return ""
        return re.sub(r'[^a-zA-Z\s]', '', str(text).lower())

    def extract_job_features(self, job):
        if getattr(job, 'required_skills', None):
            skills = [s.strip() for s in job.required_skills.split(',')]
            return self.preprocess_text(' '.join(skills))
        return ""

    def build_content_features(self):
        jobs = Job.objects.filter(is_active=True)
        job_features, job_ids = [], []

        for job in jobs:
            job_features.append(self.extract_job_features(job))
            job_ids.append(job.id)

        if job_features:
            self.job_features_matrix = self.tfidf_vectorizer.fit_transform(job_features)
            self.job_ids = job_ids

        return self.job_features_matrix, self.job_ids

    def get_user_profile_vector(self, user_profile):
        skills = [s.strip() for s in (user_profile.skills or "").split(',')]
        text = self.preprocess_text(' '.join(skills))
        if self.job_features_matrix is None:
            self.build_content_features()
        return self.tfidf_vectorizer.transform([text])

    # ======================== Content-Based Filtering ========================
    def content_based_recommendations(self, user_id, num_recommendations=10):
        try:
            user_profile = UserProfile.objects.get(user_id=user_id)
        except UserProfile.DoesNotExist:
            return []

        # Handle users with no skills
        if not user_profile.skills or user_profile.skills.strip() == "":
            return []

        if self.job_features_matrix is None:
            self.build_content_features()

        user_vector = self.get_user_profile_vector(user_profile)
        similarities = cosine_similarity(user_vector, self.job_features_matrix).flatten()

        interacted_jobs = JobInteraction.objects.filter(user_id=user_id).values_list('job_id', flat=True)

        recommendations = [
            {'job_id': job_id, 'similarity_score': sim, 'recommendation_type': 'content_based'}
            for job_id, sim in zip(self.job_ids, similarities)
            if job_id not in interacted_jobs and sim > 0
        ]

        recommendations.sort(key=lambda x: x['similarity_score'], reverse=True)
        return recommendations[:num_recommendations]

    # ======================== Collaborative Filtering ========================
    def build_user_item_matrix(self):
        interactions = JobInteraction.objects.filter(rating__isnull=False).values('user_id', 'job_id', 'rating')
        if not interactions:
            return None

        df = pd.DataFrame(interactions)
        self.user_job_ratings = df.pivot_table(index='user_id', columns='job_id', values='rating', fill_value=0)
        return self.user_job_ratings

    def calculate_user_similarity(self, user_id, other_user_id):
        if self.user_job_ratings is None:
            return 0
        if user_id not in self.user_job_ratings.index or other_user_id not in self.user_job_ratings.index:
            return 0

        user1 = self.user_job_ratings.loc[user_id]
        user2 = self.user_job_ratings.loc[other_user_id]
        common = (user1 != 0) & (user2 != 0)
        if common.sum() < 2:
            return 0

        try:
            corr, _ = pearsonr(user1[common], user2[common])
            return corr if not np.isnan(corr) else 0
        except Exception:
            return 0

    def collaborative_filtering_recommendations(self, user_id, num_recommendations=10):
        self.build_user_item_matrix()
        if self.user_job_ratings is None or user_id not in self.user_job_ratings.index:
            return []

        user_sims = {other: self.calculate_user_similarity(user_id, other)
                     for other in self.user_job_ratings.index if other != user_id}
        user_sims = {k: v for k, v in user_sims.items() if v > 0}

        if not user_sims:
            return []

        target_ratings = self.user_job_ratings.loc[user_id]
        unrated_jobs = target_ratings[target_ratings == 0].index

        scores, sim_sums = defaultdict(float), defaultdict(float)

        for other_id, sim in user_sims.items():
            other_ratings = self.user_job_ratings.loc[other_id]
            for job_id in unrated_jobs:
                if other_ratings[job_id] > 0:
                    scores[job_id] += sim * other_ratings[job_id]
                    sim_sums[job_id] += abs(sim)

        recommendations = [
            {'job_id': jid, 'predicted_rating': scores[jid] / sim_sums[jid], 'recommendation_type': 'collaborative'}
            for jid in scores if sim_sums[jid] > 0
        ]

        recommendations.sort(key=lambda x: x['predicted_rating'], reverse=True)
        return recommendations[:num_recommendations]

    # ======================== Hybrid Recommendations (Mean Score) ========================
    def hybrid_recommendations(self, user_id, num_recommendations=5):
        self.build_user_item_matrix()
        if self.job_features_matrix is None:
            self.build_content_features()

        content = self.content_based_recommendations(user_id, num_recommendations * 2)
        collab = self.collaborative_filtering_recommendations(user_id, num_recommendations * 2)

        # If both are empty, return empty
        if not content and not collab:
            return []

        content_dict = {r['job_id']: r['similarity_score'] for r in content}
        collab_dict = {r['job_id']: r['predicted_rating'] for r in collab}

        all_job_ids = set(content_dict.keys()).union(set(collab_dict.keys()))
        hybrid = []

        for job_id in all_job_ids:
            content_score = content_dict.get(job_id, 0)
            collab_score = collab_dict.get(job_id, 0)
            mean_score = (content_score + collab_score) / 2
            hybrid.append((job_id, {'hybrid_score': mean_score}))

        hybrid.sort(key=lambda x: x[1]['hybrid_score'], reverse=True)
        return hybrid[:num_recommendations]
