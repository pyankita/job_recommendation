import re
from collections import defaultdict
import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from django.contrib.auth.models import User
from .models import Job, UserProfile, JobInteraction



def display_recommendation_details(user_id, engine, recommendation_type="content"):
    """
    Display detailed recommendations for a user:
    - User info
    - User vector
    - Recommended jobs with vectors and scores
    """
    try:
        user = User.objects.get(id=user_id)
        user_profile = UserProfile.objects.get(user_id=user_id)
    except (User.DoesNotExist, UserProfile.DoesNotExist):
        print(f"User with ID {user_id} not found.")
        return

    print(f"\n{'='*50}\nUser: {user.username}\nSkills: {user_profile.skills}\n{'='*50}")

    # Ensure TF-IDF is built
    if engine.job_features_matrix is None:
        engine.build_content_features()

    # --- User Vector ---
    user_vector = engine.get_user_profile_vector(user_profile)
    print("\nUser TF-IDF Vector:\n", user_vector.toarray())

    # --- Get Recommendations ---
    if recommendation_type == "content":
        recommendations = engine.content_based_recommendations(user_id, num_recommendations=5)
    elif recommendation_type == "collaborative":
        recommendations = engine.collaborative_filtering_recommendations(user_id, num_recommendations=5)
    else:
        recommendations = engine.hybrid_recommendations(user_id, num_recommendations=5)

    # --- Print Job Details ---
    for idx, rec in enumerate(recommendations, start=1):
        job = Job.objects.get(id=rec['job_id'] if isinstance(rec, dict) else rec[0])
        job_vector = engine.tfidf_vectorizer.transform([engine.extract_job_features(job)])

        print(f"\n🔹 Job {idx}: {job.title}")
        print("Job Vector:\n", job_vector.toarray())

        if isinstance(rec, dict):
            if 'similarity_score' in rec:
                print(f"Similarity Score: {rec['similarity_score']:.4f}")
            if 'predicted_rating' in rec:
                print(f"Predicted Rating: {rec['predicted_rating']:.4f}")
        elif isinstance(rec, tuple):
            print(f"Hybrid Score: {rec[1]['hybrid_score']:.4f}")
    print(f"\n{'='*50}\n")


class JobRecommendationEngine:
    """
    Job Recommendation Engine with:
    1. Content-based filtering (TF-IDF + cosine similarity)
    2. Collaborative filtering (Pearson correlation)
    3. Hybrid filtering (combination)
    """

    def __init__(self):
        self.tfidf_vectorizer = TfidfVectorizer(max_features=5000, stop_words='english', ngram_range=(1, 2))
        self.job_features_matrix = None
        self.job_ids = None
        self.user_job_ratings = None

    @staticmethod
    def preprocess_text(text):
        if not text:
            return ""
        return re.sub(r'[^a-zA-Z\s]', '', str(text).lower())

    def extract_job_features(self, job):
        features = []

        # Title (moderate weight)
        if job.title:
            features.append(self.preprocess_text(job.title) * 2)

        # Description (regular weight)
        if job.description:
            features.append(self.preprocess_text(job.description))

        # Requirements (high weight)
        if job.requirements:
            requirements_text = ' '.join(job.requirements.split())
            features.append(self.preprocess_text(requirements_text * 3))

        # Skills (very high weight)
        if getattr(job, 'required_skills', None):
            skills = [skill.strip() for skill in job.required_skills.split(',')]
            features.append(self.preprocess_text(' '.join(skills * 5)))

        # Company & industry
        if job.company:
            features.append(self.preprocess_text(job.company.name))
            if hasattr(job.company, 'industry') and job.company.industry:
                features.append(self.preprocess_text(job.company.industry))

        # Experience level & job type
        if hasattr(job, 'experience_level') and job.experience_level:
            features.append(str(job.experience_level))
        if hasattr(job, 'job_type') and job.job_type:
            features.append(str(job.job_type))

        # Location
        features.append(self.preprocess_text(job.location or ""))

        return ' '.join(features)
    def build_content_features(self):
        jobs = Job.objects.filter(is_active=True).select_related('company')
        job_features, job_ids = [], []

        for job in jobs:
            job_features.append(self.extract_job_features(job))
            job_ids.append(job.id)

        if job_features:
            self.job_features_matrix = self.tfidf_vectorizer.fit_transform(job_features)
            self.job_ids = job_ids

        return self.job_features_matrix, self.job_ids

    def get_user_profile_vector(self, user_profile):
        features = []

        # Skills (very high weight)
        if user_profile.skills:
            skills = [skill.strip() for skill in user_profile.skills.split(',')]
            features.append(self.preprocess_text(' '.join(skills * 5)))

        # Bio (moderate weight)
        if user_profile.bio:
            features.append(self.preprocess_text(user_profile.bio) * 2)

        # Preferred location
        if user_profile.preferred_location:
            features.append(self.preprocess_text(user_profile.preferred_location))

        user_features_text = ' '.join(features)

        if self.job_features_matrix is None:
            self.build_content_features()

        return self.tfidf_vectorizer.transform([user_features_text])

    # ----------------------------
    # Content-Based Recommendations
    # ----------------------------
    def content_based_recommendations(self, user_id, num_recommendations=10):
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

    def hybrid_recommendations(self, user_id, num_recommendations=5):
        self.build_user_item_matrix()

        if self.user_job_ratings is None or user_id not in self.user_job_ratings.index:
            print(f"🧊 Cold start: Using content-based only for user {user_id}")
            return self.content_based_recommendations(user_id, num_recommendations)

        collab = self.collaborative_filtering_recommendations(user_id, num_recommendations * 2)
        content = self.content_based_recommendations(user_id, num_recommendations * 2)

        collab_dict = {r['job_id']: r for r in collab}
        content_dict = {r['job_id']: r for r in content}

        hybrid = []
        added = set()

        # Common jobs: average score
        for job_id in set(collab_dict) & set(content_dict):
            score = (collab_dict[job_id]['predicted_rating'] + content_dict[job_id]['similarity_score']) / 2
            hybrid.append((job_id, {'hybrid_score': score}))
            added.add(job_id)

        # Remaining content jobs
        for job_id, r in content_dict.items():
            if job_id not in added:
                hybrid.append((job_id, {'hybrid_score': r['similarity_score']}))
                added.add(job_id)

        # Remaining collaborative jobs
        for job_id, r in collab_dict.items():
            if job_id not in added:
                hybrid.append((job_id, {'hybrid_score': r['predicted_rating']}))

        hybrid.sort(key=lambda x: x[1]['hybrid_score'], reverse=True)
        return hybrid[:num_recommendations]
