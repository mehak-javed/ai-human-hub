"""Turn a reviewed project into GitHub issues and a requirements file (G1, G2).

`send_to_github` is the whole push. It is safe to run again after a failure:
every story stores its issue number the moment the issue exists, so a retry
updates those issues and creates only the missing ones (G5, G6).
"""

import re

from django.utils import timezone

from .github import REQUIREMENTS_PATH, GitHub, GitHubError, Repo, make_http_client
from .models import FollowUpQuestion, GitHubPush, Project, UserStory

PRIORITY_LABELS = {
    UserStory.Priority.MUST: ("priority: must", "b60205"),
    UserStory.Priority.SHOULD: ("priority: should", "fbca04"),
    UserStory.Priority.NICE: ("priority: nice to have", "0e8a16"),
}
SOURCE_LABEL = ("from: ai-human-hub", "5319e7")
MAX_TITLE_LENGTH = 256


# Words whose first letter is misleading: "a user", "a one-off buyer", "an hour".
SOUNDS_LIKE_CONSONANT = re.compile(r"^(?:u(?:s|ni|ti|r[aeiou])|eu|one\b|once\b)", re.IGNORECASE)
SOUNDS_LIKE_VOWEL = re.compile(r"^(?:hour|honest|honou?r|heir)", re.IGNORECASE)


def article(role: str) -> str:
    """'a' or 'an', by how the word sounds: 'an admin', 'a user', 'an hourly worker'."""
    word = role.strip()
    if SOUNDS_LIKE_VOWEL.match(word):
        return "an"
    if SOUNDS_LIKE_CONSONANT.match(word):
        return "a"
    return "an" if word[:1].lower() in "aeiou" else "a"


def sentence(story: UserStory) -> str:
    return (
        f"**As {article(story.role)}** {story.role}, **I want to** {story.goal}, "
        f"**so that** {story.reason.rstrip('.')}."
    )


def issue_for(project: Project, story: UserStory) -> dict:
    """One GitHub issue per story (G1)."""
    title = story.goal[:1].upper() + story.goal[1:]
    criteria = "\n".join(f"- [ ] {criterion}" for criterion in story.acceptance_criteria)
    approved = timezone.localtime(project.approved_at).strftime("%-d %B %Y") if project.approved_at else ""
    body = (
        f"{sentence(story)}\n\n"
        f"### Acceptance criteria\n\n{criteria}\n\n"
        "---\n"
        f"Priority: **{story.get_priority_display()}** · Project: {project.name}"
        + (f" · Approved by the client on {approved}" if approved else "")
        + "\n\n"
        # A hidden marker, so anyone can trace an issue back to its story.
        + f"<!-- ai-human-hub project:{project.pk} story:{story.pk} -->"
    )
    return {
        "title": title[:MAX_TITLE_LENGTH],
        "body": body,
        "labels": [PRIORITY_LABELS[story.priority][0], SOURCE_LABEL[0]],
    }


def requirements_markdown(project: Project, stories: list[UserStory], repo: Repo | None = None) -> str:
    """The whole brief in one file (G2). Also the client's own download (P4).

    With a repo, each story links to its GitHub issue.
    """
    lines = [
        f"# {project.name}: requirements",
        "",
        f"- **Type:** {project.get_project_type_display()}",
    ]
    if project.approved_at:
        lines.append(f"- **Approved by the client:** {timezone.localtime(project.approved_at):%-d %B %Y}")
    lines += [
        f"- **Stories:** {len(stories)}",
        "",
        "Written with AI Human Hub from the client's interview, reviewed and approved by the "
        "client, then reviewed by our team. Each story is also a GitHub issue.",
        "",
    ]

    for priority in UserStory.Priority:
        group = [s for s in stories if s.priority == priority]
        if not group:
            continue
        lines += [f"## {priority.label}", ""]
        for story in group:
            title = story.goal[:1].upper() + story.goal[1:]
            if repo and story.github_issue_number:
                number = story.github_issue_number
                title += f" ([#{number}]({repo.html_url}/issues/{number}))"
            lines.append(f"### {title}")
            lines += ["", sentence(story), ""]
            lines += [f"- [ ] {criterion}" for criterion in story.acceptance_criteria]
            lines.append("")

    # Data model (G2): what the client said about the information the system keeps.
    data_answers = project.questions.filter(topic="data", status=FollowUpQuestion.Status.ANSWERED)
    lines += ["## Information the system keeps", ""]
    if data_answers:
        for qa in data_answers:
            lines += [f"**{qa.question}**", "", qa.masked_answer, ""]
    else:
        lines += ["Not discussed in the interview yet.", ""]
    return "\n".join(lines).rstrip() + "\n"


def send_to_github(project: Project, user) -> GitHubPush:
    """Push the project's stories to its repo. Never raises; the result is recorded."""
    push = GitHubPush.objects.create(project=project, pushed_by=user, repo=project.github_repo)
    stories = list(project.stories.order_by("position"))
    try:
        with make_http_client() as http:
            github = GitHub(http)
            repo = github.connect(project.github_repo)
            github.ensure_labels(repo, dict([*PRIORITY_LABELS.values(), SOURCE_LABEL]))

            for story in stories:
                issue = issue_for(project, story)
                updated = github.update_issue(repo, story.github_issue_number, issue) if story.github_issue_number else None
                if updated:
                    push.issues_updated += 1
                else:
                    created = github.create_issue(repo, issue)
                    # Saved straight away, so a retry never duplicates it (G5).
                    story.github_issue_number = created["number"]
                    story.save(update_fields=["github_issue_number"])
                    push.issues_created += 1

            push.commit_url = github.write_file(
                repo,
                REQUIREMENTS_PATH,
                requirements_markdown(project, stories, repo),
                f"docs: update requirements for {project.name} from AI Human Hub",
            )
    except GitHubError as exc:
        push.status = GitHubPush.Status.FAILED
        push.error = str(exc)
    else:
        push.status = GitHubPush.Status.SUCCEEDED
        project.status = Project.Status.SENT_TO_GITHUB
        project.sent_to_github_at = timezone.now()
        project.save(update_fields=["status", "sent_to_github_at", "updated_at"])

    push.finished_at = timezone.now()
    push.save()
    return push
