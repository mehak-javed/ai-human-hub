from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from .models import CONSENT_VERSION, FollowUpQuestion, Project, UserStory
from .questions import QuestionGenerationError, generate_questions
from .serializers import (
    AnswerSerializer,
    FollowUpQuestionSerializer,
    ProjectSerializer,
    TranscriptSerializer,
    UserStorySerializer,
)
from .stories import NOT_SURE, StoryGenerationError, generate_stories
from .transcription import Transcription, TranscriptionError, transcribe

ALLOWED_AUDIO_TYPES = {"audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav", "audio/x-wav"}
# N2: at most 15 minutes of audio per interview.
MAX_INTERVIEW_AUDIO_SECONDS = 15 * 60
# Actions that spend our free AI quota, and their rate-limit scope.
THROTTLED_ACTIONS = {"transcripts": "transcription", "stories": "stories", "questions": "questions"}


def interview_ended() -> Response:
    return Response(
        {"detail": "This interview has ended, so it can't be changed."},
        status=status.HTTP_409_CONFLICT,
    )


class RecordingRejected(Exception):
    """An uploaded recording can't be used; `response` explains why."""

    def __init__(self, response: Response):
        super().__init__(response.data)
        self.response = response


def transcribe_upload(request) -> Transcription:
    """Check an uploaded recording and turn it into text (C4, AI1, P1).

    Raises RecordingRejected with the response to send back.
    """
    # Check the size before reading the body, so huge uploads are refused
    # without being processed.
    content_length = int(request.META.get("CONTENT_LENGTH") or 0)
    if content_length > settings.MAX_RECORDING_BYTES:
        raise RecordingRejected(
            Response(
                {"detail": "This recording is too large. Please keep it under 10 minutes."},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
        )

    upload = request.FILES.get("audio")
    if upload is None:
        raise RecordingRejected(
            Response({"audio": ["Attach a recording."]}, status=status.HTTP_400_BAD_REQUEST)
        )

    content_type = (upload.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_AUDIO_TYPES:
        raise RecordingRejected(
            Response(
                {"audio": ["This audio format isn't supported."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        )

    # P1: the audio only ever exists in memory, inside this request.
    try:
        result = transcribe(upload.read(), content_type)
    except TranscriptionError:
        raise RecordingRejected(
            Response(
                {"detail": "Transcription is unavailable right now. Please try again in a few minutes."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        ) from None
    finally:
        upload.close()

    if not result.text:
        raise RecordingRejected(
            Response(
                {"detail": "We couldn't hear any speech. Please try recording again."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        )
    return result


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
        # A spoken answer is transcribed, so it counts as a recording.
        if self.action == "answer_question" and self.request.content_type.startswith("multipart/"):
            scope = "transcription"
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

    # --- Recordings (C4, AI1) ------------------------------------------------

    @action(detail=True, methods=["get", "post"], parser_classes=[MultiPartParser])
    def transcripts(self, request, pk=None):
        """GET: the project's transcripts. POST: upload a recording."""
        project = self.get_object()
        if request.method == "GET":
            return Response(TranscriptSerializer(project.transcripts.all(), many=True).data)
        return self.add_transcript(request, project)

    def add_transcript(self, request, project):
        if project.status != Project.Status.INTERVIEWING:
            return interview_ended()

        used = project.transcripts.aggregate(total=Sum("duration_seconds"))["total"] or 0
        if used >= MAX_INTERVIEW_AUDIO_SECONDS:
            return Response(
                {"detail": "This interview has reached its 15-minute recording limit."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = transcribe_upload(request)
        except RecordingRejected as rejected:
            return rejected.response

        transcript = project.transcripts.create(
            text=result.text,
            provider=result.provider,
            duration_seconds=result.duration_seconds,
        )
        return Response(TranscriptSerializer(transcript).data, status=status.HTTP_201_CREATED)

    # --- Follow-up questions (AI3, C5) ---------------------------------------

    @action(detail=True, methods=["get", "post"])
    def questions(self, request, pk=None):
        """GET: the project's follow-up questions. POST: have the AI find gaps."""
        project = self.get_object()
        if request.method == "GET":
            return Response(FollowUpQuestionSerializer(project.questions.all(), many=True).data)
        return self.ask_questions(project)

    def ask_questions(self, project):
        if project.status != Project.Status.INTERVIEWING:
            return interview_ended()
        # Asked once per interview, so the client's answers are never thrown away.
        if project.questions.exists():
            return Response(
                {"detail": "The follow-up questions for this project have already been asked."},
                status=status.HTTP_409_CONFLICT,
            )

        # AI2: only the masked text is ever sent to an AI model.
        masked_transcripts = list(project.transcripts.values_list("masked_text", flat=True))
        if not masked_transcripts:
            return Response(
                {"detail": "Record your explanation first, then we can check for missing details."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = generate_questions(masked_transcripts)
        except QuestionGenerationError:
            return Response(
                {"detail": "Our AI is busy right now. Please try again in a few minutes."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        FollowUpQuestion.objects.bulk_create(
            FollowUpQuestion(
                project=project,
                position=position,
                provider=result.provider,
                topic=draft.topic,
                question=draft.question,
            )
            for position, draft in enumerate(result.questions)
        )
        return Response(
            FollowUpQuestionSerializer(project.questions.all(), many=True).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=["post"],
        url_path=r"questions/(?P<question_id>\d+)/answer",
        parser_classes=[JSONParser, MultiPartParser],
    )
    def answer_question(self, request, pk=None, question_id=None):
        """Answer one question by text, by voice, or with "Not sure" (C5).

        JSON: {"answer": "..."} or {"not_sure": true}. Multipart: an "audio"
        recording, which is transcribed and saved as the answer.
        """
        project = self.get_object()
        # Looked up through the client's own project, so other clients'
        # questions are "not found" too (P2).
        question = get_object_or_404(project.questions, pk=question_id)
        if project.status != Project.Status.INTERVIEWING:
            return interview_ended()

        if request.content_type.startswith("multipart/"):
            try:
                answer = transcribe_upload(request).text
            except RecordingRejected as rejected:
                return rejected.response
            not_sure = False
        else:
            serializer = AnswerSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            answer = serializer.validated_data.get("answer", "")
            not_sure = serializer.validated_data["not_sure"]

        question.answer = "" if not_sure else answer
        question.status = (
            FollowUpQuestion.Status.NOT_SURE if not_sure else FollowUpQuestion.Status.ANSWERED
        )
        question.answered_at = timezone.now()
        question.save()
        return Response(FollowUpQuestionSerializer(question).data)

    # --- User stories (AI4) --------------------------------------------------

    @action(detail=True, methods=["get", "post"])
    def stories(self, request, pk=None):
        """GET: the project's user stories. POST: have the AI write them."""
        project = self.get_object()
        if request.method == "GET":
            return Response(UserStorySerializer(project.stories.all(), many=True).data)
        return self.write_stories(project)

    def write_stories(self, project):
        if project.status != Project.Status.INTERVIEWING:
            return interview_ended()

        # AI2: only the masked text is ever sent to an AI model.
        masked_transcripts = list(project.transcripts.values_list("masked_text", flat=True))
        if not masked_transcripts:
            return Response(
                {"detail": "Record your explanation first, then we can write your stories."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        answers = [
            (q.question, NOT_SURE if q.status == FollowUpQuestion.Status.NOT_SURE else q.masked_answer)
            for q in project.questions.exclude(status=FollowUpQuestion.Status.OPEN)
        ]

        try:
            result = generate_stories(masked_transcripts, answers)
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