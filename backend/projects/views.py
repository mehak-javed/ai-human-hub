from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from .models import CONSENT_VERSION, Project, UserStory
from .serializers import ProjectSerializer, TranscriptSerializer, UserStorySerializer
from .stories import StoryGenerationError, generate_stories
from .transcription import TranscriptionError, transcribe

ALLOWED_AUDIO_TYPES = {"audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav", "audio/x-wav"}
# N2: at most 15 minutes of audio per interview.
MAX_INTERVIEW_AUDIO_SECONDS = 15 * 60
# Actions that spend our free AI quota, and their rate-limit scope.
THROTTLED_ACTIONS = {"transcripts": "transcription", "stories": "stories"}


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

    def get_throttles(self):
        # Calls that spend our free AI quota are rate-limited per user.
        scope = THROTTLED_ACTIONS.get(self.action)
        if scope and self.request.method == "POST":
            self.throttle_scope = scope
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def perform_create(self, serializer):
        # Owner and consent details come from the server, never the request.
        serializer.save(
            owner=self.request.user,
            consent_given_at=timezone.now(),
            consent_version=CONSENT_VERSION,
        )

    @action(detail=True, methods=["get", "post"], parser_classes=[MultiPartParser])
    def transcripts(self, request, pk=None):
        """GET: the project's transcripts. POST: upload a recording (C4, AI1)."""
        project = self.get_object()
        if request.method == "GET":
            return Response(TranscriptSerializer(project.transcripts.all(), many=True).data)
        return self.add_transcript(request, project)

    def add_transcript(self, request, project):
        if project.status != Project.Status.INTERVIEWING:
            return Response(
                {"detail": "This project is no longer taking recordings."},
                status=status.HTTP_409_CONFLICT,
            )

        used = project.transcripts.aggregate(total=Sum("duration_seconds"))["total"] or 0
        if used >= MAX_INTERVIEW_AUDIO_SECONDS:
            return Response(
                {"detail": "This interview has reached its 15-minute recording limit."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check the size before reading the body, so huge uploads are refused
        # without being processed.
        content_length = int(request.META.get("CONTENT_LENGTH") or 0)
        if content_length > settings.MAX_RECORDING_BYTES:
            return Response(
                {"detail": "This recording is too large. Please keep it under 10 minutes."},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        upload = request.FILES.get("audio")
        if upload is None:
            return Response({"audio": ["Attach a recording."]}, status=status.HTTP_400_BAD_REQUEST)

        content_type = (upload.content_type or "").split(";")[0].strip().lower()
        if content_type not in ALLOWED_AUDIO_TYPES:
            return Response(
                {"audio": ["This audio format isn't supported."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # P1: the audio only ever exists in memory, inside this request.
        try:
            result = transcribe(upload.read(), content_type)
        except TranscriptionError:
            return Response(
                {"detail": "Transcription is unavailable right now. Please try again in a few minutes."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        finally:
            upload.close()

        if not result.text:
            return Response(
                {"detail": "We couldn't hear any speech. Please try recording again."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        transcript = project.transcripts.create(
            text=result.text,
            provider=result.provider,
            duration_seconds=result.duration_seconds,
        )
        return Response(TranscriptSerializer(transcript).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get", "post"])
    def stories(self, request, pk=None):
        """GET: the project's user stories. POST: have the AI write them (AI4)."""
        project = self.get_object()
        if request.method == "GET":
            return Response(UserStorySerializer(project.stories.all(), many=True).data)
        return self.write_stories(project)

    def write_stories(self, project):
        if project.status != Project.Status.INTERVIEWING:
            return Response(
                {"detail": "The stories can't be rewritten after the interview has ended."},
                status=status.HTTP_409_CONFLICT,
            )

        # AI2: only the masked text is ever sent to an AI model.
        masked_transcripts = list(project.transcripts.values_list("masked_text", flat=True))
        if not masked_transcripts:
            return Response(
                {"detail": "Record your explanation first, then we can write your stories."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = generate_stories(masked_transcripts)
        except StoryGenerationError:
            return Response(
                {"detail": "Our AI is busy right now. Please try again in a few minutes."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # Replace the old drafts in one transaction: the client sees either
        # the old set or the new one, never a mix or an empty list.
        with transaction.atomic():
            project.stories.all().delete()
            UserStory.objects.bulk_create(
                UserStory(
                    project=project,
                    position=position,
                    provider=result.provider,
                    **story.model_dump(),
                )
                for position, story in enumerate(result.stories)
            )
        return Response(
            UserStorySerializer(project.stories.all(), many=True).data,
            status=status.HTTP_201_CREATED,
        )