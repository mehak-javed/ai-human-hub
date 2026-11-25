from django.contrib import admin

from .models import FollowUpQuestion, Project, StoryChange, Transcript, UserStory


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


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "project_type", "status", "created_at")
    list_filter = ("status", "project_type")
    search_fields = ("name", "owner__email", "owner__clerk_id")
    # Consent is evidence of what the client agreed to; nobody should edit it.
    readonly_fields = ("consent_given_at", "consent_version", "created_at", "updated_at")
    inlines = [TranscriptInline, FollowUpQuestionInline, UserStoryInline, StoryChangeInline]