from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health(request):
    """Liveness check used by the hosting platform and monitoring.

    Public, and never contacts Clerk or the database, so it stays fast.
    """
    return Response({"status": "ok"})