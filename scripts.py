import django
import os
import csv
from datetime import datetime

# Setup Django
os.environ['DJANGO_SETTINGS_MODULE'] = 'JOB.settings'
django.setup()

# Import models
from job_recom.models import Job, Company  # Update with your actual app name if needed

# Path to your CSV
csv_file_path = 'generated_jobs.csv'

with open(csv_file_path, mode='r', encoding='utf-8') as file:
    reader = csv.DictReader(file)

    for row in reader:
        try:
            # Get or create the company
            company_name = row['company'].strip()
            company_obj, created = Company.objects.get_or_create(name=company_name, defaults={
                "description": "",
                "industry": "Unknown",
                "location": row['location'],
                "size": "medium"
            })

            # Parse and clean fields
            title = row['title'].strip()
            description = row['description'].strip()
            location = row['location'].strip()
            category = row['category'].strip()

            # Handle date parsing (adjust format if needed)
            created_date = datetime.strptime(row['created_date'], '%m/%d/%Y').date()
            deadline = datetime.strptime(row['deadline'], '%m/%d/%Y').date()

            salary = row['salary'].strip()
            requirements = row['requirements'].strip()
            responsibilities = row['responsibilities'].strip()
            contact_email = row['contact_email'].strip()
            required_skills = row['required_skills'].strip()
            education_level = row['education_level'].strip()

            # Create and save the Job object
            job = Job(
                title=title,
                description=description,
                company=company_obj,
                location=location,
                category=category,
                created_date=created_date,
                deadline=deadline,
                salary=salary,
                requirements=requirements,
                responsibilities=responsibilities,
                contact_email=contact_email,
                required_skills=required_skills,
                education_level=education_level
            )
            job.save()
            print(f"Saved: {title} at {company_name}")

        except Exception as e:
            print(f" Error processing row: {row}")
            print(f"   Reason: {e}")
