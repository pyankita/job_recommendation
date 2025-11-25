import re
from collections import defaultdict
import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from django.contrib.auth.models import User
from .models import Job, UserProfile, JobInteraction
from datetime import date


class JobRecommendationEngine:
    """
    Job Recommendation Engine:
    1. Content-Based Filtering (TF-IDF + Cosine Similarity)
    2. Collaborative Filtering (Pearson Correlation)
    3. Hybrid Filtering (weighted combination of CB + CF)
    """

    def __init__(self):
        self.tfidf_vectorizer = TfidfVectorizer(stop_words='english')
        self.job_features_matrix = None
        self.job_ids = None
        self.user_job_ratings = None

    # -------------------- Utilities --------------------
    @staticmethod
    def deactivate_expired_jobs():
        today = date.today()
        expired_jobs = Job.objects.filter(deadline__lt=today, is_active=True)
        count = expired_jobs.update(is_active=False)
        if count > 0:
            print(f"[JobRecommendationEngine] {count} expired jobs deactivated.")

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

    # -------------------- Content-Based --------------------
    def build_content_features(self):
        self.deactivate_expired_jobs()
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

    def content_based_recommendations(self, user_id, num_recommendations=10):
        self.deactivate_expired_jobs()
        try:
            user_profile = UserProfile.objects.get(user_id=user_id)
        except UserProfile.DoesNotExist:
            return []

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

    # -------------------- Collaborative Filtering --------------------
    def build_user_item_matrix(self):
        interactions = JobInteraction.objects.filter(
            rating__isnull=False,
            interaction_type='rating'
        ).values('user_id', 'job_id', 'rating')

        if not interactions:
            self.user_job_ratings = None
            return None

        df = pd.DataFrame(interactions)
        df = df.sort_values('user_id')
        df = df.drop_duplicates(subset=['user_id', 'job_id'], keep='last')

        self.user_job_ratings = df.pivot_table(
            index='user_id',
            columns='job_id',
            values='rating',
            fill_value=0
        )
        return self.user_job_ratings

    def calculate_user_similarity(self, user_id, other_user_id):
        if self.user_job_ratings is None:
            return 0
        if user_id not in self.user_job_ratings.index or other_user_id not in self.user_job_ratings.index:
            return 0

        user1 = self.user_job_ratings.loc[user_id]
        user2 = self.user_job_ratings.loc[other_user_id]
        common = (user1 != 0) & (user2 != 0)

        if common.sum() < 1:
            return 0

        u1 = user1[common].values
        u2 = user2[common].values

        if np.std(u1) == 0 or np.std(u2) == 0:
            return 0

        try:
            corr, _ = pearsonr(u1, u2)
            return corr if not np.isnan(corr) else 0
        except Exception:
            return 0

    def collaborative_filtering_recommendations(self, user_id, num_recommendations=10):
        self.deactivate_expired_jobs()
        self.build_user_item_matrix()

        if self.user_job_ratings is None or user_id not in self.user_job_ratings.index:
            return []

        target_ratings = self.user_job_ratings.loc[user_id]
        unrated_jobs = target_ratings[target_ratings == 0].index

        if len(unrated_jobs) == 0:
            return []

        user_sims = {}
        for other_id in self.user_job_ratings.index:
            if other_id == user_id:
                continue
            sim = self.calculate_user_similarity(user_id, other_id)
            if sim > 0:
                user_sims[other_id] = sim

        if not user_sims:
            return []

        scores, sim_sums = defaultdict(float), defaultdict(float)
        for other_id, sim in user_sims.items():
            other_ratings = self.user_job_ratings.loc[other_id]
            for job_id in unrated_jobs:
                if other_ratings[job_id] > 0:
                    scores[job_id] += sim * other_ratings[job_id]
                    sim_sums[job_id] += abs(sim)

        recommendations = [
            {'job_id': jid, 'predicted_rating': scores[jid]/sim_sums[jid], 'recommendation_type':'collaborative'}
            for jid in scores if sim_sums[jid] > 0
        ]

        recommendations.sort(key=lambda x: x['predicted_rating'], reverse=True)
        return recommendations[:num_recommendations]

    # -------------------- Hybrid --------------------
    def hybrid_recommendations(self, user_id, num_recommendations=5):
        self.deactivate_expired_jobs()
        self.build_user_item_matrix()
        if self.job_features_matrix is None:
            self.build_content_features()

        cf_recs = self.collaborative_filtering_recommendations(user_id, num_recommendations*2)
        cb_recs = self.content_based_recommendations(user_id, num_recommendations*2)

        cf_dict = {r['job_id']: r.get('predicted_rating', 0) for r in cf_recs}
        cb_dict = {r['job_id']: r.get('similarity_score', 0) for r in cb_recs}

        all_jobs = set(cf_dict.keys()).union(set(cb_dict.keys()))
        hybrid = []

        for jid in all_jobs:
            cf_score = cf_dict.get(jid, 0)
            cb_score = cb_dict.get(jid, 0)

            # Always take the mean
            hybrid_score = (cf_score + cb_score) / 2

            hybrid.append((jid, {'hybrid_score': hybrid_score}))

        hybrid.sort(key=lambda x: x[1]['hybrid_score'], reverse=True)
        return hybrid[:num_recommendations]
