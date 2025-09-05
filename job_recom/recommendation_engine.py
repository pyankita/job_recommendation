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
    def __init__(self):
        self.tfidf_vectorizer = TfidfVectorizer(
            max_features=5000,
            stop_words='english',
            ngram_range=(1, 2)
        )
        self.job_features_matrix = None
        self.job_ids = None
        self.user_job_ratings = None

    def preprocess_text(self, text):
        if not text:
            return ""
        return re.sub(r'[^a-zA-Z\s]', '', str(text).lower())

    def extract_job_features(self, job):
        features = []

        features.append(self.preprocess_text(job.title))
        features.append(self.preprocess_text(job.description))
        features.append(self.preprocess_text(job.requirements))

        if getattr(job, 'skills_required', None):
            skills = job.skills_required.split(',')
            skills_text = ' '.join([skill.strip() for skill in skills] * 2)
            features.append(self.preprocess_text(skills_text))

        if job.company:
            features.append(self.preprocess_text(job.company.name))
            features.append(self.preprocess_text(job.company.industry))

        features.append(job.experience_level if getattr(job, 'experience_level', None) else "")
        features.append(job.job_type if getattr(job, 'job_type', None) else "")
        features.append(self.preprocess_text(job.location))

        return ' '.join(features)

    def build_content_features(self):
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
        features = []

        if user_profile.skills:
            skills = user_profile.skills.split(',')
            skills_text = ' '.join([skill.strip() for skill in skills] * 3)
            features.append(self.preprocess_text(skills_text))

        features.append(self.preprocess_text(user_profile.bio))
        features.append(self.preprocess_text(user_profile.preferred_location))

        # Removed preferred_job_type because it's not in your model

        user_features_text = ' '.join(features)

        if self.job_features_matrix is None:
            self.build_content_features()

        return self.tfidf_vectorizer.transform([user_features_text])

    def content_based_recommendations(self, user_id, num_recommendations=10):
        try:
            user_profile = UserProfile.objects.get(user_id=user_id)
        except UserProfile.DoesNotExist:
            return []

        if self.job_features_matrix is None:
            self.build_content_features()

        if self.job_features_matrix is None:
            return []

        user_vector = self.get_user_profile_vector(user_profile)
        similarities = cosine_similarity(user_vector, self.job_features_matrix).flatten()

        interacted_jobs = JobInteraction.objects.filter(user_id=user_id).values_list('job_id', flat=True)

        recommendations = []
        for idx, similarity in enumerate(similarities):
            job_id = self.job_ids[idx]
            if job_id not in interacted_jobs:
                recommendations.append({
                    'job_id': job_id,
                    'similarity_score': similarity,
                    'recommendation_type': 'content_based'
                })

        recommendations.sort(key=lambda x: x['similarity_score'], reverse=True)
        return recommendations[:num_recommendations]

    def build_user_item_matrix(self):
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
        if self.user_job_ratings is None:
            return 0

        if user_id not in self.user_job_ratings.index or other_user_id not in self.user_job_ratings.index:
            return 0

        user1_ratings = self.user_job_ratings.loc[user_id]
        user2_ratings = self.user_job_ratings.loc[other_user_id]

        common_jobs = (user1_ratings != 0) & (user2_ratings != 0)

        if common_jobs.sum() < 2:
            return 0

        user1_common = user1_ratings[common_jobs]
        user2_common = user2_ratings[common_jobs]

        try:
            correlation, _ = pearsonr(user1_common, user2_common)
            return correlation if not np.isnan(correlation) else 0
        except Exception:
            return 0

    def collaborative_filtering_recommendations(self, user_id, num_recommendations=10):
        user_item_matrix = self.build_user_item_matrix()

        if user_item_matrix is None or user_id not in user_item_matrix.index:
            return []

        user_similarities = {}
        for other_user_id in user_item_matrix.index:
            if other_user_id != user_id:
                similarity = self.calculate_user_similarity(user_id, other_user_id)
                if similarity > 0:
                    user_similarities[other_user_id] = similarity

        if not user_similarities:
            return []

        target_user_ratings = user_item_matrix.loc[user_id]
        unrated_jobs = target_user_ratings[target_user_ratings == 0].index

        job_scores = defaultdict(float)
        similarity_sums = defaultdict(float)

        for similar_user_id, similarity in user_similarities.items():
            similar_user_ratings = user_item_matrix.loc[similar_user_id]

            for job_id in unrated_jobs:
                if similar_user_ratings[job_id] > 0:
                    job_scores[job_id] += similarity * similar_user_ratings[job_id]
                    similarity_sums[job_id] += abs(similarity)

        recommendations = []
        for job_id, score in job_scores.items():
            if similarity_sums[job_id] > 0:
                predicted_rating = score / similarity_sums[job_id]
                recommendations.append({
                    'job_id': job_id,
                    'predicted_rating': predicted_rating,
                    'recommendation_type': 'collaborative'
                })

        recommendations.sort(key=lambda x: x['predicted_rating'], reverse=True)
        return recommendations[:num_recommendations]

    def hybrid_recommendations(self, user_id, num_recommendations=5):
        """
        Hybrid recommendation logic:
        - If the user has no ratings/interactions, fall back to content-based recommendations.
        - Otherwise, combine collaborative and content-based recommendations.
        """
        # Ensure the user-item matrix is loaded
        self.build_user_item_matrix()

        # Step 1: Cold-start check
        if self.user_job_ratings is None or user_id not in self.user_job_ratings.index:
            print(f"Cold start for user {user_id} — using content-based only.")
            return self.content_based_recommendations(user_id, num_recommendations)

        # Step 2: Get recommendations
        collaborative_recs = self.collaborative_filtering_recommendations(user_id, num_recommendations * 2)
        content_recs = self.content_based_recommendations(user_id, num_recommendations * 2)

        collaborative_ids = {rec['job_id']: rec for rec in collaborative_recs}
        content_ids = {rec['job_id']: rec for rec in content_recs}

        # Combine based on presence in both
        hybrid_recs = []
        added = set()

        # Step 3: Prioritize common jobs
        for job_id in (set(collaborative_ids) & set(content_ids)):
            hybrid_score = (collaborative_ids[job_id]['predicted_rating'] +
                            content_ids[job_id]['similarity_score']) / 2
            hybrid_recs.append((job_id, {'hybrid_score': hybrid_score}))
            added.add(job_id)

        # Step 4: Fill remaining with content-only
        for job_id in content_ids:
            if job_id not in added:
                hybrid_recs.append((job_id, {'hybrid_score': content_ids[job_id]['similarity_score']}))
                added.add(job_id)

        # Step 5: Fill remaining with collaborative-only
        for job_id in collaborative_ids:
            if job_id not in added:
                hybrid_recs.append((job_id, {'hybrid_score': collaborative_ids[job_id]['predicted_rating']}))

        # Sort by hybrid score
        hybrid_recs.sort(key=lambda x: x[1]['hybrid_score'], reverse=True)
        return hybrid_recs[:num_recommendations]
