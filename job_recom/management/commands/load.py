from django.core.management.base import BaseCommand
import csv
from dateutil import parser
from datetime import date
from job_recom.models import Job, Company


class Command(BaseCommand):
    help = "Load or refresh job data from a CSV file (generated_jobs.csv)."

    def handle(self, *args, **options):
        csv_file_path = 'generated_jobs.csv'

        Job.objects.all().delete()
        self.stdout.write(self.style.WARNING("All previous jobs deleted!"))

        saved_count = 0
        skipped_count = 0

        try:
            with open(csv_file_path, mode='r', encoding='utf-8') as file:
                reader = csv.DictReader(file)

                for row in reader:
                    try:
                        if not any(row.values()):
                            continue

                        def safe_strip(value):
                            return str(value).strip() if value is not None else ""

                        company_name = safe_strip(row.get('company', 'Unknown Company'))
                        company_obj, _ = Company.objects.get_or_create(
                            name=company_name or "Unknown Company",
                            defaults={
                                "description": "",
                                "industry": "Unknown",
                                "location": safe_strip(row.get('location')),
                                "size": "medium",
                            },
                        )

                        def parse_date(value):
                            try:
                                return parser.parse(safe_strip(value)).date()
                            except Exception:
                                return None

                        created_date = parse_date(row.get('created_date')) or date.today()
                        deadline = parse_date(row.get('deadline'))

                        Job.objects.create(
                            title=safe_strip(row.get('title')),
                            description=safe_strip(row.get('description')),
                            company=company_obj,
                            location=safe_strip(row.get('location')),
                            category=safe_strip(row.get('category')),
                            created_date=created_date,
                            deadline=deadline,
                            salary=safe_strip(row.get('salary') or "0"),
                            requirements=safe_strip(row.get('requirements')),
                            responsibilities=safe_strip(row.get('responsibilities')),
                            contact_email=safe_strip(row.get('contact_email')),
                            required_skills=safe_strip(row.get('required_skills')),
                            education_level=safe_strip(row.get('education_level')),
                        )

                        saved_count += 1
                        self.stdout.write(self.style.SUCCESS(
                            f"Saved: {safe_strip(row.get('title')) or 'Untitled Job'} at {company_name}"
                        ))

                    except Exception as inner_error:
                        skipped_count += 1
                        self.stderr.write(self.style.ERROR(f"Error processing row: {row}"))
                        self.stderr.write(self.style.ERROR(f"Reason: {inner_error}"))

            self.stdout.write(self.style.SUCCESS("\nImport Complete!"))
            self.stdout.write(self.style.SUCCESS(f"Total Jobs Saved: {saved_count}"))
            self.stdout.write(self.style.WARNING(f"Skipped Rows (errors only): {skipped_count}"))
            self.stdout.write(self.style.SUCCESS(f"Total in database now: {Job.objects.count()}"))

        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f"CSV file not found at path: {csv_file_path}"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Unexpected error: {e}"))
