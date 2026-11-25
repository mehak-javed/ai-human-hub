"""Deleting projects, on request (C11) or when kept too long (P3).

Deleting a project removes everything linked to it in one transaction:
transcripts, follow-up answers, stories, the change log and GitHub push
records. A DeletionRecord with IDs and counts only is kept as proof.
Issues already delivered to the client's own GitHub repository stay there:
that repository belongs to the client.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import DeletionRecord, Project

logger = logging.getLogger(__name__)


def delete_project(project: Project, reason: str) -> DeletionRecord:
    with transaction.atomic():
        record = DeletionRecord.objects.create(
            project_id=project.pk,
            owner_id=project.owner_id,
            reason=reason,
            transcripts=project.transcripts.count(),
            stories=project.stories.count(),
            project_created_at=project.created_at,
        )
        project.delete()
    logger.warning("Deleted project %s (%s)", record.project_id, reason)
    return record


def expired_projects(now=None):
    """Projects past the retention period (P3).

    A project expires a set time after it was sent to GitHub, or after it was
    last changed if it never got that far (an abandoned interview).
    """
    cutoff = (now or timezone.now()) - timedelta(days=settings.DATA_RETENTION_DAYS)
    return Project.objects.filter(
        Q(sent_to_github_at__lt=cutoff) | Q(sent_to_github_at__isnull=True, updated_at__lt=cutoff)
    )
