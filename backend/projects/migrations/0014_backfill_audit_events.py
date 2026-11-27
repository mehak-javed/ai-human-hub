"""Fill the audit log (A8) for projects that existed before it.

Built from the records we already keep, at their real times. Each detail
ends with "(from earlier records)", so nobody mistakes it for a live entry.
Nothing the client said is copied: only counts, IDs, providers and repos.
"""

from django.db import migrations

EARLIER = " (from earlier records)"
PROVIDERS = {"workers_ai": "Workers AI", "groq": "Groq"}
TEAM = {"edit": "team_edit", "reject": "team_reject", "merge": "team_merge", "split": "team_split"}


def plural(count, word):
    if count == 1:
        return f"{count} {word}"
    if word.endswith("y"):
        return f"{count} {word[:-1]}ies"
    return f"{count} {word}s"


def backfill(apps, schema_editor):
    Project = apps.get_model("projects", "Project")
    AuditEvent = apps.get_model("projects", "AuditEvent")
    events = []

    def add(project, at, action, actor, detail, user_id=None):
        if at:
            events.append(
                AuditEvent(
                    project_id=project.pk,
                    created_at=at,
                    action=action,
                    actor=actor,
                    user_id=user_id,
                    detail=(detail + EARLIER)[:200],
                )
            )

    for project in Project.objects.all():
        if AuditEvent.objects.filter(project_id=project.pk).exists():
            continue
        add(project, project.created_at, "project_created", "client", f"Consent version {project.consent_version}", project.owner_id)
        for t in project.transcripts.all():
            add(project, t.created_at, "recording_transcribed", "ai", f"{PROVIDERS.get(t.provider, t.provider)}, {round(t.duration_seconds or 0)} s of audio")
        questions = list(project.questions.order_by("created_at"))
        if questions:
            add(project, questions[0].created_at, "questions_asked", "ai", f"{PROVIDERS.get(questions[0].provider, questions[0].provider)} asked {plural(len(questions), 'question')}")
        for q in questions:
            if q.answered_at:
                how = "Not sure" if q.status == "not_sure" else "answered"
                add(project, q.answered_at, "question_answered", "client", f"Question {q.position + 1} ({q.topic}): {how}", project.owner_id)
        stories = list(project.stories.order_by("created_at"))
        ai_stories = [s for s in stories if s.origin == "ai"]
        if ai_stories:
            first = ai_stories[0]
            add(project, first.created_at, "stories_written", "ai", f"{PROVIDERS.get(first.provider, first.provider)} wrote stories ({plural(len(ai_stories), 'story')} still here)")
        if project.approved_at:
            add(project, project.approved_at, "approved", "client", plural(len(stories), "story"), project.owner_id)
        for change in project.story_changes.all():
            ids = ", ".join(str(s.get("id")) for s in change.before)
            add(project, change.created_at, TEAM[change.action], "team", f"Story {ids}", change.changed_by_id)
        for push in project.github_pushes.all():
            if push.status == "succeeded":
                add(project, push.finished_at or push.started_at, "sent_to_github", "team", f"{push.repo}: {plural(push.issues_created, 'issue')} created, {push.issues_updated} updated", push.pushed_by_id)
            elif push.status == "failed":
                add(project, push.finished_at or push.started_at, "send_failed", "team", push.error[:120], push.pushed_by_id)

    AuditEvent.objects.bulk_create(events)


class Migration(migrations.Migration):
    dependencies = [("projects", "0013_audit_event")]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
