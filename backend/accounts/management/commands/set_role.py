"""Give a user the Admin or Client role.

    python manage.py set_role someone@example.com admin

The user must have signed in once, so their account exists. Run it against
the production database to make the first admin (Render's free plan has no
shell).
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

User = get_user_model()


class Command(BaseCommand):
    help = "Set a user's role (admin or client), found by email or Clerk ID."

    def add_arguments(self, parser):
        parser.add_argument("user", help="The user's email address or Clerk ID (user_...)")
        parser.add_argument("role", choices=[choice.value for choice in User.Role])

    def handle(self, *args, **options):
        matches = list(
            User.objects.filter(Q(email__iexact=options["user"]) | Q(clerk_id=options["user"]))
        )
        if not matches:
            raise CommandError("No user found. They must sign in once before getting a role.")
        if len(matches) > 1:
            raise CommandError("More than one user matches. Use their Clerk ID instead.")

        user = matches[0]
        user.role = options["role"]
        user.save(update_fields=["role"])
        self.stdout.write(self.style.SUCCESS(f"{user} is now {user.get_role_display()}."))
