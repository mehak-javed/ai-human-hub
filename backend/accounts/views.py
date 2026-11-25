from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(["GET"])
def me(request):
    """Return the signed-in user. Requires a valid Clerk session token."""
    user = request.user
    return Response(
        {
            "id": user.id,
            "clerk_id": user.clerk_id,
            "role": user.role,
            "email": user.email,
            "name": user.display_name,
        }
    )