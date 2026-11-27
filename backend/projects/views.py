from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from .delivery import requirements_markdown
from .masking import mask_personal_data
from .audit import Action, Actor, plural, provider_name, record
from .data_model import DataModelGenerationError, generate_data_model
from .models import CONSENT_VERSION, DataModel, DeletionRecord, FollowUpQuestion, Project, UserStory
from .progress import refresh_if_stale
from .questions import QuestionGenerationError, generate_questions
from .retention import delete_project
from .serializers import (
    AnswerSerializer,
    ChangeRequestSerializer,
    DataModelRequestSerializer,
    DataModelSerializer,
    FollowUpQuestionSerializer,
    ProjectSerializer,
    StoryInputSerializer,
    TranscriptSerializer,
    UserStorySerializer,
)
from .stories import NOT_SURE, StoryGenerationError, generate_stories
from .transcription import Transcription, TranscriptionError, transcribe

ALLOWED_AUDIO_TYPES = {"audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav", "audio/x-wav"}
# N2: at most 15 minutes of audio per interview.
MAX_INTERVIEW_AUDIO_SECONDS = 15 * 60
# Actions that spend our free AI quota, and their rate-limit scope.
THROTTLED_ACTIONS = {
    "transcripts": "transcription",
    "questions": "questions",
    "stories": "stories",
    "revise_stories": "stories",
    "data_model": "stories",
}

AI_BUSY = "Our AI is busy right now. Please try again in a few minutes."


def interview_ended() -> Response:
    return Response(
        {"detail": "This interview has ended, so it can't be changed."},
        status=status.HTTP_409_CONFLICT,
    )


def not_in_review() -> Response:
    return Response(
        {"detail": "Your stories can only be changed while they are waiting for your review."},
        status=status.HTTP_409_CONFLICT,
    )


def story_for_ai(story: UserStory) -> dict:
    """A story as the AI sees it: client edits may contain personal data (AI2)."""
    return {
        "role": mask_personal_data(story.role),
        "goal": mask_personal_data(story.goal),
        "reason": mask_personal_data(story.reason),
        "acceptance_criteria": [mask_personal_data(c) for c in story.acceptance_criteria],
        "priority": story.priority,
    }


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
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """The signed-in client's own projects: list, create (C3), view one and
    delete one (C11)."""

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

    def retrieve(self, request, *args, **kwargs):
        # G4: a delivered project's progress is at most a minute old when viewed.
        refresh_if_stale(self.get_object())
        return super().retrieve(request, *args, **kwargs)

    def perform_destroy(self, project):
        # C11: everything is removed at once, and only IDs and counts are kept.
        delete_project(project, DeletionRecord.Reason.CLIENT_REQUEST)

    @action(detail=True, methods=["get"])
    def export(self, request, pk=None):
        """Download the approved requirements as Markdown (P4)."""
        project = self.get_object()
        if project.status not in (Project.Status.AWAITING_ADMIN, Project.Status.SENT_TO_GITHUB):
            return Response(
                {"detail": "You can download your requirements once you've approved them."},
                status=status.HTTP_409_CONFLICT,
            )
        markdown = requirements_markdown(project, list(project.stories.order_by("position")))
        response = HttpResponse(markdown, content_type="text/markdown; charset=utf-8")
        filename = f"{slugify(project.name) or 'project'}-requirements.md"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    def perform_create(self, serializer):
        # Owner and consent details come from the server, never the request.
        project = serializer.save(
            owner=self.request.user,
            consent_given_at=timezone.now(),
            consent_version=CONSENT_VERSION,
        )
        record(project, Action.PROJECT_CREATED, Actor.CLIENT, f"Consent version {CONSENT_VERSION}", self.request.user)

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
        seconds = round(result.duration_seconds or 0)
        record(project, Action.RECORDING_TRANSCRIBED, Actor.AI, f"{provider_name(result.provider)}, {seconds} s of audio")
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
        record(
            project,
            Action.QUESTIONS_ASKED,
            Actor.AI,
            f"{provider_name(result.provider)} asked {plural(len(result.questions), 'question')}",
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
        how = "Not sure" if not_sure else ("by voice" if request.content_type.startswith("multipart/") else "in writing")
        record(project, Action.QUESTION_ANSWERED, Actor.CLIENT, f"Question {question.position + 1} ({question.topic}): {how}", request.user)
        return Response(FollowUpQuestionSerializer(question).data)

    # --- User stories (AI4, C8, C9) -----------------------------------------

    @action(detail=True, methods=["get", "post"])
    def stories(self, request, pk=None):
        """GET: the project's user stories. POST: end the interview and have
        the AI write them; the project then waits for the client's review."""
        project = self.get_object()
        if request.method == "GET":
            refresh_if_stale(project)
            return Response(UserStorySerializer(project.stories.all(), many=True).data)
        return self.write_stories(project)

    def interview_for_ai(self, project):
        """The masked transcripts and follow-up answers (AI2)."""
        masked_transcripts = list(project.transcripts.values_list("masked_text", flat=True))
        answers = [
            (q.question, NOT_SURE if q.status == FollowUpQuestion.Status.NOT_SURE else q.masked_answer)
            for q in project.questions.exclude(status=FollowUpQuestion.Status.OPEN)
        ]
        return masked_transcripts, answers

    def replace_stories(self, project, result, rewritten=False):
        # In one transaction: the client sees either the old set or the new
        # one, never a mix or an empty list.
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
            project.status = Project.Status.AWAITING_CLIENT
            project.save(update_fields=["status", "updated_at"])
        record(
            project,
            Action.STORIES_REWRITTEN if rewritten else Action.STORIES_WRITTEN,
            Actor.AI,
            f"{provider_name(result.provider)} wrote {plural(len(result.stories), 'story')}"
            + (", following the client's note" if rewritten else ""),
        )
        return Response(
            UserStorySerializer(project.stories.all(), many=True).data,
            status=status.HTTP_201_CREATED,
        )

    def write_stories(self, project):
        if project.status != Project.Status.INTERVIEWING:
            return interview_ended()

        masked_transcripts, answers = self.interview_for_ai(project)
        if not masked_transcripts:
            return Response(
                {"detail": "Record your explanation first, then we can write your stories."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = generate_stories(masked_transcripts, answers)
        except StoryGenerationError:
            return Response({"detail": AI_BUSY}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return self.replace_stories(project, result)

    @action(detail=True, methods=["post"], url_path="stories/revise")
    def revise_stories(self, request, pk=None):
        """Ask the AI to rewrite the stories, following the client's note (C9)."""
        project = self.get_object()
        if project.status != Project.Status.AWAITING_CLIENT:
            return not_in_review()

        serializer = ChangeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        masked_transcripts, answers = self.interview_for_ai(project)
        try:
            result = generate_stories(
                masked_transcripts,
                answers,
                current_stories=[story_for_ai(story) for story in project.stories.all()],
                change_request=mask_personal_data(serializer.validated_data["note"]),
            )
        except StoryGenerationError:
            return Response({"detail": AI_BUSY}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return self.replace_stories(project, result, rewritten=True)

    @action(detail=True, methods=["post"], url_path="stories/add")
    def add_story(self, request, pk=None):
        """Add a story the AI missed (C8)."""
        project = self.get_object()
        if project.status != Project.Status.AWAITING_CLIENT:
            return not_in_review()

        serializer = StoryInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        last = project.stories.order_by("-position").first()
        story = serializer.save(
            project=project,
            position=last.position + 1 if last else 0,
            origin=UserStory.Origin.CLIENT,
        )
        record(project, Action.STORY_ADDED, Actor.CLIENT, f"Story {story.pk}", request.user)
        return Response(UserStorySerializer(story).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch", "delete"], url_path=r"stories/(?P<story_id>\d+)")
    def story(self, request, pk=None, story_id=None):
        """PATCH: change a story's wording or priority. DELETE: remove it (C8)."""
        project = self.get_object()
        # Looked up through the client's own project, so other clients'
        # stories are "not found" too (P2).
        story = get_object_or_404(project.stories, pk=story_id)
        if project.status != Project.Status.AWAITING_CLIENT:
            return not_in_review()

        if request.method == "DELETE":
            record(project, Action.STORY_REMOVED, Actor.CLIENT, f"Story {story.pk}", request.user)
            story.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = StoryInputSerializer(story, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        # AI7: remember that the client changed what the AI wrote.
        story = serializer.save(client_edited=story.origin == UserStory.Origin.AI)
        record(project, Action.STORY_EDITED, Actor.CLIENT, f"Story {story.pk}", request.user)
        return Response(UserStorySerializer(story).data)

    @action(detail=True, methods=["get", "post"], url_path="data-model")
    def data_model(self, request, pk=None):
        """GET: the data summary, or null. POST: have the AI write it, or
        rewrite it following the client's note (AI5, C6). Only in review."""
        project = self.get_object()
        current = DataModel.objects.filter(project=project).first()
        if request.method == "GET":
            return Response({"data_model": DataModelSerializer(current).data if current else None})
        if project.status != Project.Status.AWAITING_CLIENT:
            return not_in_review()

        serializer = DataModelRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = serializer.validated_data.get("note", "").strip()
        masked_transcripts, answers = self.interview_for_ai(project)
        try:
            result = generate_data_model(
                masked_transcripts,
                answers,
                [story_for_ai(story) for story in project.stories.all()],
                # Rewrite from the current summary only when asked for a change.
                current_model=current.for_ai() if current and note else None,
                change_request=mask_personal_data(note) if note else None,
            )
        except DataModelGenerationError:
            return Response({"detail": AI_BUSY}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        data = result.model.model_dump()
        saved, _ = DataModel.objects.update_or_create(
            project=project,
            defaults={
                "entities": data["entities"],
                "relationships": data["relationships"],
                "provider": result.provider,
                "confirmed_at": None,
            },
        )
        record(
            project,
            Action.DATA_MODEL_REWRITTEN if note and current else Action.DATA_MODEL_WRITTEN,
            Actor.AI,
            f"{provider_name(result.provider)} listed {plural(len(data['entities']), 'entity').replace('entitys', 'entities')}"
            + (", following the client's note" if note and current else ""),
        )
        return Response({"data_model": DataModelSerializer(saved).data}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Approve the stories and send them to the admin (C9). They lock."""
        project = self.get_object()
        if project.status != Project.Status.AWAITING_CLIENT:
            return not_in_review()
        if not project.stories.exists():
            return Response(
                {"detail": "Add at least one story before approving."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            project.status = Project.Status.AWAITING_ADMIN
            project.approved_at = timezone.now()
            project.save(update_fields=["status", "approved_at", "updated_at"])
            # Approving also confirms the data summary, if there is one (C6).
            DataModel.objects.filter(project=project).update(confirmed_at=project.approved_at)
            record(project, Action.APPROVED, Actor.CLIENT, f"{plural(project.stories.count(), 'story')}", request.user)
        return Response(ProjectSerializer(project).data)
