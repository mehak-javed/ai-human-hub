from rest_framework.permissions import BasePermission


class IsAdminRole(BasePermission):
    """Only users with the Admin role (our team) may use admin endpoints (P2).

    The role lives in our own database and is set with
    `python manage.py set_role`, never from anything the browser sends.
    """

    message = "This is only available to our team."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.role == user.Role.ADMIN)
