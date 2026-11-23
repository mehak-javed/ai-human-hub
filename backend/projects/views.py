from django.utils import timezone
from rest_framework import mixins, viewsets

from .models import CONSENT_VERSION, Project
from .serializers import ProjectSerializer


class ProjectViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """The signed-in client's own projects: list, create (C3) and view one."""

    serializer_class = ProjectSerializer

    def get_queryset(self):
        # The owner check (P2): every query starts from the user's own
        # projects, so another client's project is simply "not found" (404)
        # and we never reveal that it exists.
        return Project.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        # Owner and consent details come from the server, never the request.
        serializer.save(
            owner=self.request.user,
            consent_given_at=timezone.now(),
            consent_version=CONSENT_VERSION,
        )