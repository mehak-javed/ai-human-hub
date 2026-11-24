from django.conf import settings
from django.db import models

from .masking import mask_personal_data

# The version of the recording notice the client agreed to (C2). Change it
# whenever the notice text in the frontend changes, so we always know exactly
# which wording each client accepted.
CONSENT_VERSION = "2026-11-23"


class Project(models.Model):
    """A client's project brief, from interview to GitHub issues."""

    class Type(models.TextChoices):
        WEBSITE = "website", "Website"
        APP = "app", "App"
        DASHBOARD = "dashboard", "Dashboard"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        INTERVIEWING = "interviewing", "Interviewing"
        AWAITING_CLIENT = "awaiting_client", "Awaiting client"
        AWAITING_ADMIN = "awaiting_admin", "Awaiting admin"
        SENT_TO_GITHUB = "sent_to_github", "Sent to GitHub"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="projects",
    )
    name = models.CharField(max_length=120)
    project_type = models.CharField(max_length=16, choices=Type.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.INTERVIEWING)
    consent_given_at = models.DateTimeField()
    consent_version = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name


class Transcript(models.Model):
    """The text of one voice recording (C4, AI1).

    There is deliberately no field for the audio itself (P1): only the text
    is ever stored. `masked_text` is the same text with personal data hidden
    (AI2); it is the only version ever sent to an AI model.
    """

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="transcripts")
    text = models.TextField()
    masked_text = models.TextField(editable=False)
    provider = models.CharField(max_length=20)
    duration_seconds = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"Transcript {self.pk} for {self.project}"

    def save(self, *args, **kwargs):
        # Always recomputed, so the masked copy can never fall out of step.
        self.masked_text = mask_personal_data(self.text)
        super().save(*args, **kwargs)