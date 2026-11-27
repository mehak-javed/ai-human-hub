"""Correct a wording slip in audit entries written before it was fixed.

The app wrote "5 storys" and "2 entitys". Only our own formatting changes
here; no event is added, removed or moved.
"""

from django.db import migrations
from django.db.models import Value
from django.db.models.functions import Replace


def fix(apps, schema_editor):
    AuditEvent = apps.get_model("projects", "AuditEvent")
    for wrong, right in (("storys", "stories"), ("entitys", "entities")):
        AuditEvent.objects.filter(detail__contains=wrong).update(detail=Replace("detail", Value(wrong), Value(right)))


class Migration(migrations.Migration):
    dependencies = [("projects", "0014_backfill_audit_events")]

    operations = [migrations.RunPython(fix, migrations.RunPython.noop)]
