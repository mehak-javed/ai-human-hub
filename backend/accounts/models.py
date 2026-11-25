from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """A person who uses AI Human Hub.

    Clients sign in through Clerk; `clerk_id` links this row to their Clerk
    user. Staff accounts made with `createsuperuser` have no Clerk ID.
    """

    class Role(models.TextChoices):
        CLIENT = "client", "Client"
        ADMIN = "admin", "Admin"

    clerk_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.CLIENT)
    # When the name and email were copied from Clerk (see clerk_profile.py).
    clerk_synced_at = models.DateTimeField(null=True, blank=True, editable=False)

    @property
    def display_name(self) -> str:
        return self.get_full_name() or self.email or self.username

    def __str__(self) -> str:
        return self.email or self.username