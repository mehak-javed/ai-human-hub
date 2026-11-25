"""The team's side of the API: review client-approved stories and send
them to GitHub (A3, A4, A5, A6).

Only users with the Admin role can call these endpoints (IsAdminRole).
Admins see the masked transcripts and answers, never the raw text: they
need the requirements, not the client's personal details (AI2, least
privilege). Every change to a story is recorded in StoryChange (A4).
"""

from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import IsAdminRole

from . import github
from .delivery import send_to_github
from .models import FollowUpQuestion, GitHubPush, Project, StoryChange, UserStory
from .serializers import StoryInputSerializer, UserStorySerializer

MAX_STORIES_IN_ONE_CHANGE = 10


# --- Serializers ---------------------------------------------------------------


class ClientSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.CharField()
    name = serializers.CharField(source="display_name")


class AdminProjectListSerializer(serializers.ModelSerializer):
    client = ClientSerializer(source="owner")
    story_count = serializers.IntegerField(source="stories.count")

    class Meta:
        model = Project
        fields = [
            "id",
            "name",
            "project_type",
            "status",
            "client",
            "story_count",
            "github_repo",
            "approved_at",
            "sent_to_github_at",
            "created_at",
        ]


class GitHubPushSerializer(serializers.ModelSerializer):
    pushed_by = serializers.CharField(source="pushed_by.display_name", default="(removed user)")

    class Meta:
        model = GitHubPush
        fields = [
            "id",
            "repo",
            "status",
            "issues_created",
            "issues_updated",
            "commit_url",
            "error",
            "pushed_by",
            "started_at",
            "finished_at",
        ]


class StoryChangeSerializer(serializers.ModelSerializer):
    changed_by = serializers.CharField(source="changed_by.display_name", default="(removed user)")

    class Meta:
        model = StoryChange
        fields = ["id", "action", "changed_by", "before", "after", "note", "created_at"]


class AdminProjectDetailSerializer(AdminProjectListSerializer):
    masked_transcripts = serializers.SerializerMethodField()
    answers = serializers.SerializerMethodField()
    stories = UserStorySerializer(many=True)
    changes = StoryChangeSerializer(source="story_changes", many=True)
    pushes = serializers.SerializerMethodField()
    github = serializers.SerializerMethodField()

    class Meta(AdminProjectListSerializer.Meta):
        fields = AdminProjectListSerializer.Meta.fields + [
            "masked_transcripts",
            "answers",
            "stories",
            "changes",
            "pushes",
            "github",
        ]

    def get_pushes(self, project) -> list[dict]:
        return GitHubPushSerializer(project.github_pushes.all()[:5], many=True).data

    def get_github(self, project) -> dict:
        """Whether our GitHub App is set up, and where to install it."""
        return {"configured": github.is_configured(), "install_url": github.install_url()}

    def get_masked_transcripts(self, project) -> list[str]:
        return list(project.transcripts.values_list("masked_text", flat=True))

    def get_answers(self, project) -> list[dict]:
        return [
            {
                "question": q.question,
                "answer": "Not sure" if q.status == FollowUpQuestion.Status.NOT_SURE else q.masked_answer,
            }
            for q in project.questions.exclude(status=FollowUpQuestion.Status.OPEN)
        ]


class ConnectRepoSerializer(serializers.Serializer):
    repo = serializers.CharField(max_length=140)


class RejectSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500)


class MergeSerializer(serializers.Serializer):
    story_ids = serializers.ListField(
        child=serializers.IntegerField(), min_length=2, max_length=MAX_STORIES_IN_ONE_CHANGE
    )
    story = StoryInputSerializer()

    def validate_story_ids(self, ids):
        if len(set(ids)) != len(ids):
            raise serializers.ValidationError("Each story can only be merged once.")
        return ids


class SplitSerializer(serializers.Serializer):
    stories = StoryInputSerializer(many=True)

    def validate_stories(self, stories):
        if not 2 <= len(stories) <= MAX_STORIES_IN_ONE_CHANGE:
            raise serializers.ValidationError(
                f"Split a story into 2 to {MAX_STORIES_IN_ONE_CHANGE} stories."
            )
        return stories


# --- Helpers -------------------------------------------------------------------


def not_awaiting_admin() -> Response:
    return Response(
        {"detail": "Stories can only be changed while the project is waiting for our review."},
        status=status.HTTP_409_CONFLICT,
    )


def github_not_set_up() -> Response:
    return Response(
        {"detail": "Our GitHub App isn't set up yet, so nothing can be sent to GitHub."},
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def renumber(project) -> None:
    """Keep positions 0, 1, 2… after stories are removed or inserted."""
    stories = list(project.stories.order_by("position", "id"))
    for position, story in enumerate(stories):
        story.position = position
    UserStory.objects.bulk_update(stories, ["position"])


def new_story(project, data: dict, position: int) -> UserStory:
    return UserStory.objects.create(
        project=project,
        position=position,
        origin=UserStory.Origin.ADMIN,
        **data,
    )


def make_room(project, after_position: int, count: int) -> None:
    """Move later stories down to fit `count` new ones after a position."""
    later = list(project.stories.filter(position__gt=after_position))
    for story in later:
        story.position += count
    UserStory.objects.bulk_update(later, ["position"])


# --- Views ---------------------------------------------------------------------


class AdminProjectViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Every client's projects, for our team. Filter with ?status= and ?client=."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    def get_queryset(self):
        # Most recently approved first; projects not yet approved come last
        # (Postgres would otherwise sort NULLs first).
        projects = Project.objects.select_related("owner").order_by(
            F("approved_at").desc(nulls_last=True), "-created_at"
        )
        status_filter = self.request.query_params.get("status")
        if status_filter:
            projects = projects.filter(status=status_filter)
        client = self.request.query_params.get("client")
        if client and client.isdigit():
            projects = projects.filter(owner_id=int(client))
        return projects

    def get_serializer_class(self):
        if self.action == "list":
            return AdminProjectListSerializer
        return AdminProjectDetailSerializer

    def record(self, project, action_name, before, after, note=""):
        StoryChange.objects.create(
            project=project,
            action=action_name,
            changed_by=self.request.user,
            before=before,
            after=after,
            note=note,
        )

    def editable_project(self):
        """The project, or a 409 response if it isn't waiting for our review."""
        project = self.get_object()
        if project.status != Project.Status.AWAITING_ADMIN:
            return project, not_awaiting_admin()
        return project, None

    @action(detail=True, methods=["patch"], url_path=r"stories/(?P<story_id>\d+)")
    def edit_story(self, request, pk=None, story_id=None):
        """Change a story's wording or priority (A4)."""
        project, refused = self.editable_project()
        story = get_object_or_404(project.stories, pk=story_id)
        if refused:
            return refused

        serializer = StoryInputSerializer(story, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        before = story.snapshot()
        with transaction.atomic():
            story = serializer.save()
            self.record(project, StoryChange.Action.EDIT, [before], [story.snapshot()])
        return Response(UserStorySerializer(story).data)

    @action(detail=True, methods=["post"], url_path=r"stories/(?P<story_id>\d+)/reject")
    def reject_story(self, request, pk=None, story_id=None):
        """Remove a story that shouldn't be built, with a reason (A4)."""
        project, refused = self.editable_project()
        story = get_object_or_404(project.stories, pk=story_id)
        if refused:
            return refused

        serializer = RejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            self.record(
                project,
                StoryChange.Action.REJECT,
                [story.snapshot()],
                [],
                note=serializer.validated_data["reason"],
            )
            story.delete()
            renumber(project)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="stories/merge")
    def merge_stories(self, request, pk=None):
        """Replace two or more overlapping stories with one (A4)."""
        project, refused = self.editable_project()
        if refused:
            return refused

        serializer = MergeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data["story_ids"]
        originals = list(project.stories.filter(pk__in=ids).order_by("position"))
        # Only this project's stories can be merged (P2).
        if len(originals) != len(ids):
            return Response(
                {"story_ids": ["Some of these stories aren't in this project."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            position = originals[0].position
            before = [story.snapshot() for story in originals]
            project.stories.filter(pk__in=ids).delete()
            merged = new_story(project, serializer.validated_data["story"], position)
            renumber(project)
            merged.refresh_from_db()
            self.record(project, StoryChange.Action.MERGE, before, [merged.snapshot()])
        return Response(UserStorySerializer(merged).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path=r"stories/(?P<story_id>\d+)/split")
    def split_story(self, request, pk=None, story_id=None):
        """Replace one story that does too much with several smaller ones (A4)."""
        project, refused = self.editable_project()
        story = get_object_or_404(project.stories, pk=story_id)
        if refused:
            return refused

        serializer = SplitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        parts = serializer.validated_data["stories"]

        with transaction.atomic():
            position = story.position
            before = [story.snapshot()]
            story.delete()
            make_room(project, position, len(parts) - 1)
            created = [new_story(project, data, position + i) for i, data in enumerate(parts)]
            renumber(project)
            for part in created:
                part.refresh_from_db()
            self.record(project, StoryChange.Action.SPLIT, before, [part.snapshot() for part in created])
        return Response(UserStorySerializer(created, many=True).data, status=status.HTTP_201_CREATED)

    # --- GitHub (A5, A6) ------------------------------------------------------

    @action(detail=True, methods=["post"], url_path="github")
    def connect_github(self, request, pk=None):
        """Link the project to a private repo and test the connection (A6)."""
        project = self.get_object()
        if project.status == Project.Status.SENT_TO_GITHUB:
            return Response(
                {"detail": "This project has already been sent to GitHub."},
                status=status.HTTP_409_CONFLICT,
            )
        if not github.is_configured():
            return github_not_set_up()

        serializer = ConnectRepoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with github.make_http_client() as http:
                repo = github.GitHub(http).connect(serializer.validated_data["repo"].strip())
        except github.GitHubError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        project.github_repo = repo.full_name
        project.save(update_fields=["github_repo", "updated_at"])
        return Response({"repo": repo.full_name, "url": repo.html_url})

    @action(detail=True, methods=["post"], url_path="send")
    def send(self, request, pk=None):
        """Send the reviewed stories to GitHub as issues plus requirements.md (A5)."""
        project = self.get_object()
        if project.status != Project.Status.AWAITING_ADMIN:
            return not_awaiting_admin()
        if not github.is_configured():
            return github_not_set_up()
        if not project.github_repo:
            return Response(
                {"detail": "Connect a GitHub repository first."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not project.stories.exists():
            return Response(
                {"detail": "There are no stories to send."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        push = send_to_github(project, request.user)
        project.refresh_from_db()
        body = {"push": GitHubPushSerializer(push).data, "status": project.status}
        if push.status == GitHubPush.Status.FAILED:
            # 502: GitHub, not our request, was the problem. Safe to try again.
            return Response(body, status=status.HTTP_502_BAD_GATEWAY)
        return Response(body)
