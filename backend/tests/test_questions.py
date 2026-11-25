"""Tests for the follow-up question prompt and schema (AI3).

Retries and the backup provider are tested in test_llm.py; here the AI
call itself is replaced with a fake.
"""

import pytest

from projects import questions
from projects.llm import InvalidAnswer, LLMError
from projects.questions import (
    MAX_QUESTIONS,
    TOPICS,
    QuestionGenerationError,
    build_messages,
    generate_questions,
    parse_answer,
)

VALID = {
    "questions": [
        {"topic": "payments", "question": "Should customers pay online when they order?"},
        {"topic": "deadlines", "question": "When would you like the website to be ready?"},
    ]
}


def test_prompt_lists_every_checklist_topic():
    system = build_messages(["text"])[0]["content"]

    for topic in ("users", "roles", "features", "data", "payments", "login", "deadlines"):
        assert f"- {topic}:" in system
    assert set(TOPICS) == {"users", "roles", "features", "data", "payments", "login", "deadlines"}


def test_transcripts_are_sent_inside_transcript_tags():
    messages = build_messages(["I'm [NAME].", "I sell cakes."])

    assert messages[1] == {
        "role": "user",
        "content": "<transcript>\nI'm [NAME].\n\nI sell cakes.\n</transcript>",
    }


def test_generate_questions_returns_validated_questions(monkeypatch):
    def fake_ask(messages, schema_name, json_schema, parse):
        assert schema_name == "follow_up_questions"
        return parse(VALID), "groq"

    monkeypatch.setattr(questions, "ask_for_json", fake_ask)

    result = generate_questions(["I sell cakes."])

    assert result.provider == "groq"
    assert [q.topic for q in result.questions] == ["payments", "deadlines"]


def test_generate_questions_reports_when_every_provider_fails(monkeypatch):
    def failing(*args):
        raise LLMError("All AI providers failed.")

    monkeypatch.setattr(questions, "ask_for_json", failing)

    with pytest.raises(QuestionGenerationError):
        generate_questions(["text"])


def test_no_questions_is_a_valid_answer():
    # The client may already have covered everything.
    assert parse_answer({"questions": []}) == []


def question(**changes):
    return {**VALID["questions"][0], **changes}


@pytest.mark.parametrize(
    "answer",
    [
        "not json",
        {},
        {"questions": [question(topic="colours")]},
        {"questions": [question(question="")]},
        {"questions": [question(question="x" * 301)]},
        {"questions": [{"topic": "users"}]},
        {"questions": [question()] * (MAX_QUESTIONS + 1)},
    ],
    ids=[
        "not-json",
        "empty-object",
        "unknown-topic",
        "empty-question",
        "question-too-long",
        "missing-question",
        "too-many-questions",
    ],
)
def test_invalid_answers_are_rejected(answer):
    with pytest.raises(InvalidAnswer):
        parse_answer(answer)