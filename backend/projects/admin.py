from django.contrib import admin

from .models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "project_type", "status", "created_at")
    list_filter = ("status", "project_type")
    search_fields = ("name", "owner__email", "owner__clerk_id")
    # Consent is evidence of what the client agreed to; nobody should edit it.
    readonly_fields = ("consent_given_at", "consent_version", "created_at", "updated_at")