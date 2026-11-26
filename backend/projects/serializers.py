from rest_framework import serializers

from .models import FollowUpQuestion, Project, Transcript, UserStory
from .progress import progress


class ProjectSerializer(serializers.ModelSerializer):
    # Not stored as-is: the view records *when* consent was given and which
    # version of the notice was shown.
    consent = serializers.BooleanField(write_only=True)
    # C10: features done versus total, once the project is on GitHub.
    progress = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id",
            "name",
            "project_type",
            "status",
            "consent",
            "consent_given_at",
            "consent_version",
            "approved_at",
            "progress",
            "created_at",
        ]
        # The client can never set these, even by sending them in the request.
        read_only_fields = ["status", "consent_given_at", "consent_version", "approved_at", "created_at"]

    def get_progress(self, project) -> dict | None:
        return progress(project)

    def validate_consent(self, value: bool) -> bool:
        if value is not True:
            raise serializers.ValidationError(
                "You must agree to the recording notice before starting a project."
            )
        return value

    def create(self, validated_data):
        validated_data.pop("consent")
        return super().create(validated_data)


class TranscriptSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transcript
        fields = ["id", "text", "masked_text", "provider", "duration_seconds", "created_at"]
        read_only_fields = fields


class UserStorySerializer(serializers.ModelSerializer):
    class Meta:
        model = UserStory
        fields = [
            "id",
            "role",
            "goal",
            "reason",
            "acceptance_criteria",
            "priority",
            "provider",
            "origin",
            "client_edited",
            "github_issue_number",
            "github_issue_closed",
            "created_at",
        ]
        read_only_fields = fields


class StoryInputSerializer(serializers.ModelSerializer):
    """The parts of a story a client may write when adding or editing one (C8)."""

    acceptance_criteria = serializers.ListField(
        child=serializers.CharField(max_length=300),
        min_length=1,
        max_length=8,
    )

    class Meta:
        model = UserStory
        fields = ["role", "goal", "reason", "acceptance_criteria", "priority"]


class ChangeRequestSerializer(serializers.Serializer):
    """The client's note asking the AI to rewrite the stories (C9)."""

    note = serializers.CharField(max_length=1000)


class FollowUpQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FollowUpQuestion
        fields = ["id", "topic", "question", "status", "answer", "masked_answer", "answered_at"]
        read_only_fields = fields


class AnswerSerializer(serializers.Serializer):
    """A typed answer, or "Not sure" (C5). Exactly one of the two."""

    answer = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    not_sure = serializers.BooleanField(default=False)

    def validate(self, data):
        has_answer = bool(data.get("answer", "").strip())
        if has_answer == data["not_sure"]:
            raise serializers.ValidationError("Type an answer, or choose Not sure.")
        return data