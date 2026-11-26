from django.contrib import admin

from .models import AIUsage, DeletionRecord, FollowUpQuestion, GitHubPush, Project, StoryChange, Transcript, UserStory


class TranscriptInline(admin.TabularInline):
    model = Transcript
    extra = 0
    fields = ("created_at", "provider", "duration_seconds", "text", "masked_text")
    readonly_fields = fields
    can_delete = False


class FollowUpQuestionInline(admin.TabularInline):
    model = FollowUpQuestion
    extra = 0
    fields = ("topic", "question", "status", "answer", "masked_answer", "provider")
    readonly_fields = fields
    can_delete = False


class UserStoryInline(admin.StackedInline):
    model = UserStory
    extra = 0
    fields = ("priority", "role", "goal", "reason", "acceptance_criteria", "provider")
    readonly_fields = fields
    can_delete = False


class StoryChangeInline(admin.TabularInline):
    model = StoryChange
    extra = 0
    fields = ("created_at", "action", "changed_by", "note", "before", "after")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        # The change log is written by the app only (A4).
        return False


class GitHubPushInline(admin.TabularInline):
    model = GitHubPush
    extra = 0
    fields = ("started_at", "status", "repo", "issues_created", "issues_updated", "commit_url", "error", "pushed_by")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "project_type", "status", "created_at")
    list_filter = ("status", "project_type")
    search_fields = ("name", "owner__email", "owner__clerk_id")
    # Consent is evidence of what the client agreed to; nobody should edit it.
    readonly_fields = ("consent_given_at", "consent_version", "approved_at", "sent_to_github_at", "created_at", "updated_at")
    inlines = [TranscriptInline, FollowUpQuestionInline, UserStoryInline, StoryChangeInline, GitHubPushInline]


@admin.register(DeletionRecord)
class DeletionRecordAdmin(admin.ModelAdmin):
    """Read-only proof of deletions (C11, P3)."""

    list_display = ("project_id", "reason", "transcripts", "stories", "project_created_at", "deleted_at")
    list_filter = ("reason",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AIUsage)
class AIUsageAdmin(admin.ModelAdmin):
    """Daily AI usage against the free limits (A7). Read-only."""

    list_display = ("day", "provider", "feature", "calls", "neurons", "requests_remaining", "request_limit")
    list_filter = ("provider", "feature")
    date_hierarchy = "day"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
