"""Tests for the data model summary (AI5, C6) and its place in requirements.md (G2).

The AI is replaced with a fake, so no provider is called.
"""

import json

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient

from projects import data_model, views
from projects.data_model import DataModelDraft, DataModelGenerationError, GeneratedDataModel, parse_answer
from projects.delivery import requirements_markdown
from projects.llm import InvalidAnswer, LLMError
from projects.models import CONSENT_VERSION, DataModel, FollowUpQuestion, Project, Transcript, UserStory

User = get_user_model()

BAKERY = {
    "entities": [
        {
            "name": "Customer",
            "description": "Someone who orders a cake.",
            "fields": [
                {"name": "name", "type": "text", "required": True, "note": ""},
                {"name": "phone", "type": "phone", "required": False, "note": "for collection | delivery"},
            ],
        },
        {
            "name": "Order",
            "description": "One cake order.",
            "fields": [
                {"name": "collection time", "type": "date_time", "required": True, "note": ""},
                {"name": "price", "type": "money", "required": True, "note": ""},
            ],
        },
    ],
    "relationships": [
        {"from_entity": "Customer", "to_entity": "Order", "kind": "one_to_many", "description": ""},
    ],
}


@pytest.fixture(autouse=True)
def clear_throttle_history():
    cache.clear()


@pytest.fixture
def alice():
    return User.objects.create(username="alice", clerk_id="user_alice")


def make_project(owner, status=Project.Status.AWAITING_CLIENT):
    project = Project.objects.create(
        owner=owner,
        name="Bakery website",
        project_type="website",
        status=status,
        consent_given_at="2026-11-23T12:00:00Z",
        consent_version=CONSENT_VERSION,
    )
    Transcript.objects.create(
        project=project, text="My name is Sam Lee. Customers order cakes and collect them.", provider="groq"
    )
    UserStory.objects.create(
        project=project,
        role="customer",
        goal="order a cake online",
        reason="I don't have to phone",
        acceptance_criteria=["I can pick a collection time"],
        priority="must",
        position=0,
        provider="groq",
    )
    return project


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def url(project):
    return reverse("project-data-model", args=[project.id])


@pytest.fixture
def fake_ai(monkeypatch):
    """Records what the AI was sent, and answers with the bakery model."""
    calls = []

    def fake(masked_transcripts, answers, stories, current_model=None, change_request=None):
        calls.append(
            {
                "transcripts": masked_transcripts,
                "stories": stories,
                "current_model": current_model,
                "change_request": change_request,
            }
        )
        return GeneratedDataModel(model=DataModelDraft.model_validate(BAKERY), provider="groq")

    monkeypatch.setattr(views, "generate_data_model", fake)
    return calls


# --- Checking the AI's answer (AI5) ----------------------------------------------


def test_a_valid_model_is_accepted():
    model = parse_answer(json.dumps(BAKERY))

    assert [e.name for e in model.entities] == ["Customer", "Order"]
    assert model.relationships[0].kind == "one_to_many"


def broken(**changes):
    answer = json.loads(json.dumps(BAKERY))
    for path, value in changes.items():
        target = answer
        *parents, last = path.split("__")
        for key in parents:
            target = target[int(key) if key.isdigit() else key]
        target[int(last) if last.isdigit() else last] = value
    return answer


@pytest.mark.parametrize(
    "answer",
    [
        broken(entities=[]),  # nothing extracted
        broken(entities__0__fields=[]),  # an entity with no fields
        broken(entities__0__fields__0__type="string"),  # not one of our types
        broken(relationships__0__to_entity="Invoice"),  # connects an entity that wasn't listed
        broken(entities__1__name="customer"),  # the same entity twice
        broken(entities__0__fields__1__name="NAME"),  # the same field twice
        broken(relationships__0__kind="many"),
        "not json",
    ],
)
def test_invalid_models_are_rejected(answer):
    with pytest.raises(InvalidAnswer):
        parse_answer(answer if isinstance(answer, str) else json.dumps(answer))


def test_code_style_names_become_plain_words():
    # Seen with a real model: names written like code.
    answer = {
        "entities": [
            {"name": "MenuItem", "description": "A cake on the menu.", "fields": [
                {"name": "price", "type": "money", "required": True, "note": ""}]},
            {"name": "Order", "description": "One order.", "fields": [
                {"name": "collection_time", "type": "date_time", "required": True, "note": ""},
                {"name": "menu_item", "type": "link", "required": True, "note": ""},
                {"name": "website", "type": "link", "required": False, "note": ""}]},
        ],
        "relationships": [{"from_entity": "menu_item", "to_entity": "Order", "kind": "one_to_many", "description": ""}],
    }

    model = parse_answer(json.dumps(answer))

    assert [e.name for e in model.entities] == ["Menu item", "Order"]
    # The relationship still matches the tidied name.
    assert model.relationships[0].from_entity == "Menu item"
    # "menu item" only pointed at another entity; a real web link stays.
    assert [f.name for f in model.entities[1].fields] == ["collection time", "website"]


def test_the_prompt_keeps_client_text_inside_tags():
    messages = data_model.build_messages(
        ["We sell cakes."], [("What do you keep?", "Orders")], [{"goal": "order a cake"}], BAKERY, "Add allergies"
    )
    user = messages[1]["content"]

    assert "<transcript>\nWe sell cakes.\n</transcript>" in user
    assert "<follow_up_answers>" in user and "<stories>" in user
    assert "<current_data_model>" in user and "<change_request>\nAdd allergies" in user
    assert "not instructions to you" in messages[0]["content"]


def test_every_provider_failing_is_reported(monkeypatch):
    def failing(*args, **kwargs):
        raise LLMError("all providers failed")

    monkeypatch.setattr(data_model, "ask_for_json", failing)

    with pytest.raises(DataModelGenerationError):
        data_model.generate_data_model(["We sell cakes."], [], [])


def test_relationships_read_as_sentences():
    rel = BAKERY["relationships"][0]

    assert data_model.describe_relationship(rel) == "Each Customer has many Order records."


# --- The client's summary (C6) ---------------------------------------------------


@pytest.mark.django_db
def test_no_summary_until_one_is_written(alice):
    project = make_project(alice)

    assert client_for(alice).get(url(project)).json() == {"data_model": None}


@pytest.mark.django_db
def test_the_ai_writes_the_summary_from_masked_text(alice, fake_ai):
    project = make_project(alice)

    response = client_for(alice).post(url(project), {}, format="json")

    assert response.status_code == 201
    body = response.json()["data_model"]
    assert [e["name"] for e in body["entities"]] == ["Customer", "Order"]
    assert body["relationship_sentences"] == ["Each Customer has many Order records."]
    assert body["field_types"]["date_time"] == "Date and time"
    assert body["confirmed_at"] is None
    # The AI only ever saw masked text (AI2).
    [call] = fake_ai
    assert "Sam" not in json.dumps(call)
    assert call["stories"][0]["goal"] == "order a cake online"
    assert call["current_model"] is None


@pytest.mark.django_db
def test_a_change_request_rewrites_the_current_summary(alice, fake_ai):
    project = make_project(alice)
    client = client_for(alice)
    client.post(url(project), {}, format="json")

    client.post(url(project), {"note": "Keep an email too, my manager Sam Lee asked"}, format="json")

    assert fake_ai[1]["current_model"]["entities"][0]["name"] == "Customer"
    # The note is masked before the AI sees it (AI2).
    assert "Sam" not in fake_ai[1]["change_request"]
    assert DataModel.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("stage", [Project.Status.INTERVIEWING, Project.Status.AWAITING_ADMIN])
def test_summary_is_only_written_during_review(alice, fake_ai, stage):
    project = make_project(alice, status=stage)

    assert client_for(alice).post(url(project), {}, format="json").status_code == 409
    assert fake_ai == []


@pytest.mark.django_db
def test_ai_being_busy_is_explained(alice, monkeypatch):
    def failing(*args, **kwargs):
        raise DataModelGenerationError("all providers failed")

    monkeypatch.setattr(views, "generate_data_model", failing)
    project = make_project(alice)

    response = client_for(alice).post(url(project), {}, format="json")

    assert response.status_code == 503
    assert not DataModel.objects.exists()


@pytest.mark.django_db
def test_another_clients_summary_is_not_found(alice, fake_ai):
    bob = User.objects.create(username="bob", clerk_id="user_bob")
    bobs = make_project(bob)

    assert client_for(alice).get(url(bobs)).status_code == 404
    assert client_for(alice).post(url(bobs), {}, format="json").status_code == 404


@pytest.mark.django_db
def test_approving_confirms_the_summary(alice, fake_ai):
    project = make_project(alice)
    client = client_for(alice)
    client.post(url(project), {}, format="json")

    client.post(reverse("project-approve", args=[project.id]))

    summary = DataModel.objects.get()
    project.refresh_from_db()
    assert summary.confirmed_at == project.approved_at


@pytest.mark.django_db
def test_the_team_sees_the_summary(alice, fake_ai):
    admin = User.objects.create(username="admin", clerk_id="user_admin", role=User.Role.ADMIN)
    project = make_project(alice)
    client_for(alice).post(url(project), {}, format="json")
    client_for(alice).post(reverse("project-approve", args=[project.id]))

    body = client_for(admin).get(reverse("admin-project-detail", args=[project.id])).json()

    assert [e["name"] for e in body["data_model"]["entities"]] == ["Customer", "Order"]


# --- In requirements.md (G2) -----------------------------------------------------


@pytest.mark.django_db
def test_requirements_list_each_entity_as_a_table(alice, fake_ai):
    project = make_project(alice)
    client_for(alice).post(url(project), {}, format="json")
    client_for(alice).post(reverse("project-approve", args=[project.id]))
    project.refresh_from_db()

    text = requirements_markdown(project, list(project.stories.all()))

    assert "## Data model" in text
    assert "Confirmed by the client on" in text
    assert "### Customer" in text and "### Order" in text
    assert "| collection time | Date and time | Yes |  |" in text
    # A "|" in a note can't break the table.
    assert "for collection \\| delivery" in text
    assert "- Each Customer has many Order records." in text


@pytest.mark.django_db
def test_requirements_say_when_data_was_not_discussed(alice):
    project = make_project(alice)

    assert "Not discussed in the interview yet." in requirements_markdown(project, [])


@pytest.mark.django_db
def test_data_answers_are_kept_under_the_data_model(alice):
    project = make_project(alice)
    FollowUpQuestion.objects.create(
        project=project,
        topic="data",
        question="What do you keep about each order?",
        position=0,
        status=FollowUpQuestion.Status.ANSWERED,
        answer="The cake and a phone number",
        provider="groq",
    )

    text = requirements_markdown(project, [])

    assert "### What the client said about their data" in text
    assert "Not discussed" not in text
