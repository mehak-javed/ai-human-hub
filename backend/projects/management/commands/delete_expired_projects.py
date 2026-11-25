"""Delete projects past the retention period (P3). Run daily.

    python manage.py delete_expired_projects --dry-run
    python manage.py delete_expired_projects
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from projects.models import DeletionRecord
from projects.retention import delete_project, expired_projects


class Command(BaseCommand):
    help = f"Delete projects older than DATA_RETENTION_DAYS (now {settings.DATA_RETENTION_DAYS} days)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Only count what would be deleted.")

    def handle(self, *args, **options):
        projects = list(expired_projects())
        if options["dry_run"]:
            self.stdout.write(f"{len(projects)} project(s) would be deleted.")
            return
        for project in projects:
            delete_project(project, DeletionRecord.Reason.RETENTION)
        self.stdout.write(self.style.SUCCESS(f"Deleted {len(projects)} expired project(s)."))
