"""Tests for the user-story prompt and schema (AI4).

Retries and the backup provider are tested in test_llm.py; here the AI
call itself is replaced with a fake.
"""

import json

import pytest

from projects import stories
from projects.llm import InvalidAnswer, LLMError
from projects.stories import (
    StoryGenerationError,
    build_messages,
    generate_stories,
    parse_answer,
)

VALID = {
    "stories": [
        {
            "role": "customer",
            "goal": "order a cake online",
            "reason": "I don't have to visit the shop",
            "acceptance_criteria": ["I can choose a cake", "I can pick a collection time"],
            "priority": "must",
        },
        {
            "role": "bakery owner",
            "goal": "see each day's orders",
            "reason": "I can plan my baking",
            "acceptance_criteria": ["Orders are listed by collection time"],
            "priority": "should",
        },
    ]
}


def test_transcripts_are_sent_inside_transcript_tags():
    messages = build_messages(["First recording by [NAME].", "Second recording."])

    assert messages[0]["role"] == "system"
    assert messages[1] == {
        "role": "user",
        "content": "<transcript>\nFirst recording by [NAME].\n\nSecond recording.\n</transcript>",
    }


def test_follow_up_answers_are_added_after_the_transcript():
    messages = build_messages(
        ["I want a booking site."],
        [("Who will use it?", "Patients and [NAME] at reception."), ("Any deadline?", "Not sure")],
    )

    assert messages[1]["content"] == (
        "<transcript>\nI want a booking site.\n</transcript>\n\n"
        "<follow_up_answers>\n"
        "Q: Who will use it?\nA: Patients and [NAME] at reception.\n\n"
        "Q: Any deadline?\nA: Not sure\n"
        "</follow_up_answers>"
    )


def test_generate_stories_returns_validated_stories(monkeypatch):
    sent = []

    def fake_ask(messages, schema_name, json_schema, parse):
        sent.append((messages, schema_name))
        return parse(VALID), "workers_ai"

    monkeypatch.setattr(stories, "ask_for_json", fake_ask)

    result = generate_stories(["I want customers to order cakes online."])

    assert result.provider == "workers_ai"
    assert [s.goal for s in result.stories] == ["order a cake online", "see each day's orders"]
    assert sent[0][1] == "user_stories"


def test_generate_stories_reports_when_every_provider_fails(monkeypatch):
    def failing(*args):
        raise LLMError("All AI providers failed.")

    monkeypatch.setattr(stories, "ask_for_json", failing)

    with pytest.raises(StoryGenerationError):
        generate_stories(["text"])


# --- The schema: what counts as a valid answer -------------------------------


def story(**changes):
    return {**VALID["stories"][0], **changes}


def test_answer_can_be_a_json_string():
    assert len(parse_answer(json.dumps(VALID))) == 2


def test_extra_whitespace_is_trimmed():
    [parsed] = parse_answer({"stories": [story(role="  customer  ")]})
    assert parsed.role == "customer"


@pytest.mark.parametrize(
    ("goal", "reason"),
    [
        ("I want to order a cake", "so that I save time"),
        ("to order a cake", "So that I save time"),
        ("order a cake", "I save time"),
    ],
)
def test_repeated_sentence_words_are_removed(goal, reason):
    [parsed] = parse_answer({"stories": [story(goal=goal, reason=reason)]})
    assert (parsed.goal, parsed.reason) == ("order a cake", "I save time")


@pytest.mark.parametrize(
    "answer",
    [
        "not json at all",
        [],
        {},
        {"stories": []},
        {"stories": [story(priority="urgent")]},
        {"stories": [story(goal="")]},
        {"stories": [story(goal="x" * 301)]},
        {"stories": [story(acceptance_criteria=[])]},
        {"stories": [story(acceptance_criteria=["ok"] * 9)]},
        {"stories": [{k: v for k, v in story().items() if k != "reason"}]},
        {"stories": [story()] * 31},
    ],
    ids=[
        "not-json",
        "list",
        "empty-object",
        "no-stories",
        "unknown-priority",
        "empty-goal",
        "goal-too-long",
        "no-criteria",
        "too-many-criteria",
        "missing-reason",
        "too-many-stories",
    ],
)
def test_invalid_answers_are_rejected(answer):
    with pytest.raises(InvalidAnswer):
        parse_answer(answer)