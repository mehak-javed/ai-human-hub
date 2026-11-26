from django.conf import settings
from django.db import models

from .masking import mask_personal_data
from .questions import TOPICS

# The version of the recording notice the client agreed to (C2). Change it
# whenever the notice text in the frontend changes, so we always know exactly
# which wording each client accepted.
CONSENT_VERSION = "2026-11-25"


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
    # When the client approved their stories (C9); they are locked from then on.
    approved_at = models.DateTimeField(null=True, blank=True)
    # The client's private repository, as "owner/name" (A6).
    github_repo = models.CharField(max_length=140, blank=True)
    sent_to_github_at = models.DateTimeField(null=True, blank=True)
    # When issue states were last read from GitHub (G4); webhooks keep them
    # current in between.
    github_synced_at = models.DateTimeField(null=True, blank=True)
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


class UserStory(models.Model):
    """One user story, drafted by the AI (AI4) and reviewed by the client (C8).

    "As a [role], I want [goal], so that [reason]."
    """

    class Priority(models.TextChoices):
        MUST = "must", "Must have"
        SHOULD = "should", "Should have"
        NICE = "nice", "Nice to have"

    class Origin(models.TextChoices):
        AI = "ai", "Written by AI"
        CLIENT = "client", "Added by the client"
        ADMIN = "admin", "Written by our team"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="stories")
    role = models.CharField(max_length=80)
    goal = models.CharField(max_length=300)
    reason = models.CharField(max_length=300)
    acceptance_criteria = models.JSONField(default=list)
    priority = models.CharField(max_length=8, choices=Priority.choices)
    # The order the AI wrote them in, so the list reads the same every time.
    position = models.PositiveSmallIntegerField()
    # Which AI wrote it (AI6), kept for measuring AI quality later (AI7).
    provider = models.CharField(max_length=20, blank=True)
    origin = models.CharField(max_length=8, choices=Origin.choices, default=Origin.AI)
    # True once the client has changed an AI-written story (AI7).
    client_edited = models.BooleanField(default=False)
    # The GitHub issue made from this story, so re-sending updates it (G5).
    github_issue_number = models.PositiveIntegerField(null=True, blank=True)
    # True while the story's GitHub issue is closed: the feature is done (C10).
    github_issue_closed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position"]
        verbose_name_plural = "user stories"

    def __str__(self) -> str:
        return f"As a {self.role}, I want {self.goal}"

    def snapshot(self) -> dict:
        """The story as plain data, kept in the change log."""
        return {
            "id": self.pk,
            "role": self.role,
            "goal": self.goal,
            "reason": self.reason,
            "acceptance_criteria": self.acceptance_criteria,
            "priority": self.priority,
            # Kept so AI quality (AI7) can still count removed AI stories.
            "origin": self.origin,
        }


class DataModel(models.Model):
    """The information the system must keep, as the AI understood it (AI5).

    Written from the masked interview; the client can ask for changes while
    reviewing and confirms it by approving (C6, C9).
    """

    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name="data_model")
    # [{"name", "description", "fields": [{"name", "type", "required", "note"}]}]
    entities = models.JSONField(default=list)
    # [{"from_entity", "to_entity", "kind", "description"}]
    relationships = models.JSONField(default=list)
    provider = models.CharField(max_length=20, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Data model for {self.project}"

    def for_ai(self) -> dict:
        return {"entities": self.entities, "relationships": self.relationships}


class StoryChange(models.Model):
    """One change our team made to a client-approved story (A4).

    Records who made it, when, and the stories before and after, so every
    change can be traced. Rows are never edited or deleted by the app.
    """

    class Action(models.TextChoices):
        EDIT = "edit", "Edited"
        REJECT = "reject", "Rejected"
        MERGE = "merge", "Merged"
        SPLIT = "split", "Split"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="story_changes")
    action = models.CharField(max_length=8, choices=Action.choices)
    # Kept if the admin's account is later removed, so the record survives.
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    before = models.JSONField(default=list)
    after = models.JSONField(default=list)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.get_action_display()} on {self.project} by {self.changed_by}"


class FollowUpQuestion(models.Model):
    """A question the AI asks to fill a gap in the client's explanation (AI3, C5).

    `masked_answer` is the answer with personal data hidden (AI2); it is the
    only version ever sent to an AI model.
    """

    class Status(models.TextChoices):
        OPEN = "open", "Waiting for an answer"
        ANSWERED = "answered", "Answered"
        NOT_SURE = "not_sure", "Not sure"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="questions")
    topic = models.CharField(max_length=16, choices=list(TOPICS.items()))
    question = models.CharField(max_length=300)
    # The order the AI asked them in: the most important first.
    position = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    answer = models.TextField(blank=True)
    masked_answer = models.TextField(blank=True, editable=False)
    provider = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["position"]

    def __str__(self) -> str:
        return self.question

    def save(self, *args, **kwargs):
        # Always recomputed, so the masked copy can never fall out of step.
        self.masked_answer = mask_personal_data(self.answer)
        super().save(*args, **kwargs)


class GitHubPush(models.Model):
    """One attempt to send a project to GitHub (A5, G6), kept as a record."""

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="github_pushes")
    pushed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    repo = models.CharField(max_length=140)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING)
    issues_created = models.PositiveSmallIntegerField(default=0)
    issues_updated = models.PositiveSmallIntegerField(default=0)
    commit_url = models.URLField(blank=True)
    # Shown to the admin when a push fails; never contains a token.
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at", "-id"]

    def __str__(self) -> str:
        return f"Push of {self.project} to {self.repo}: {self.get_status_display()}"


class DeletionRecord(models.Model):
    """Proof that a project was deleted (C11, P3).

    Deliberately holds no content and no name: only IDs, counts and why, so
    the record itself keeps nothing personal.
    """

    class Reason(models.TextChoices):
        CLIENT_REQUEST = "client_request", "Deleted by the client"
        RETENTION = "retention", "Retention period ended"

    project_id = models.PositiveBigIntegerField()
    owner_id = models.PositiveBigIntegerField(null=True)
    reason = models.CharField(max_length=16, choices=Reason.choices)
    transcripts = models.PositiveIntegerField(default=0)
    stories = models.PositiveIntegerField(default=0)
    project_created_at = models.DateTimeField()
    deleted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-deleted_at"]

    def __str__(self) -> str:
        return f"Project {self.project_id}: {self.get_reason_display()}"


class AIUsage(models.Model):
    """How much of each AI provider's free quota we used, per day (A7, N1, N8).

    One row per UTC day, provider and feature. Workers AI reports its cost in
    "neurons" (10,000 free per day); Groq reports its own request limit and
    what's left in response headers, so we store what it last told us.
    """

    day = models.DateField()
    provider = models.CharField(max_length=20)
    # transcription, follow_up_questions or user_stories
    feature = models.CharField(max_length=30)
    calls = models.PositiveIntegerField(default=0)
    neurons = models.FloatField(default=0)
    request_limit = models.PositiveIntegerField(null=True, blank=True)
    requests_remaining = models.PositiveIntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-day", "provider", "feature"]
        constraints = [
            models.UniqueConstraint(fields=["day", "provider", "feature"], name="one_usage_row_per_day")
        ]

    def __str__(self) -> str:
        return f"{self.day} {self.provider} {self.feature}: {self.calls} calls"
