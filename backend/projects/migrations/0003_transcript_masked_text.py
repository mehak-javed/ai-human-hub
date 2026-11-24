"""Add Transcript.masked_text and fill it in for transcripts that already exist."""

from django.db import migrations, models

from projects.masking import mask_personal_data


def mask_existing_transcripts(apps, schema_editor):
    # Migrations use a historical copy of the model without our custom save(),
    # so the masked text is computed here explicitly.
    Transcript = apps.get_model("projects", "Transcript")
    for transcript in Transcript.objects.all():
        transcript.masked_text = mask_personal_data(transcript.text)
        transcript.save(update_fields=["masked_text"])


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0002_transcript"),
    ]

    operations = [
        migrations.AddField(
            model_name="transcript",
            name="masked_text",
            field=models.TextField(default="", editable=False),
            preserve_default=False,
        ),
        migrations.RunPython(mask_existing_transcripts, migrations.RunPython.noop),
    ]