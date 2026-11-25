from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class AppUserAdmin(UserAdmin):
    list_display = ("username", "email", "clerk_id", "role", "is_staff", "date_joined")
    list_filter = ("role", "is_staff", "is_active")
    search_fields = ("username", "email", "clerk_id")
    fieldsets = UserAdmin.fieldsets + (
        ("AI Human Hub", {"fields": ("clerk_id", "role", "clerk_synced_at")}),
    )
    readonly_fields = ("clerk_synced_at",)