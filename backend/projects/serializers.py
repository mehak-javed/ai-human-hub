from rest_framework import serializers

from .models import Project, Transcript


class ProjectSerializer(serializers.ModelSerializer):
    # Not stored as-is: the view records *when* consent was given and which
    # version of the notice was shown.
    consent = serializers.BooleanField(write_only=True)

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
            "created_at",
        ]
        # The client can never set these, even by sending them in the request.
        read_only_fields = ["status", "consent_given_at", "consent_version", "created_at"]

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