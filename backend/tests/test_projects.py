"""Tests for the projects API: creating a project (C3), consent (C2) and
owner-only access (P2).

Authentication itself is tested in test_auth.py, so here we sign users in
directly with `force_authenticate`.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from projects.models import CONSENT_VERSION, Project

User = get_user_model()

VALID_PROJECT = {"name": "Bakery website", "project_type": "website", "consent": True}


@pytest.fixture
def alice():
    return User.objects.create(username="alice", clerk_id="user_alice")


@pytest.fixture
def bob():
    return User.objects.create(username="bob", clerk_id="user_bob")


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def make_project(owner, name="Existing project"):
    return Project.objects.create(
        owner=owner,
        name=name,
        project_type="app",
        consent_given_at="2026-11-23T12:00:00Z",
        consent_version=CONSENT_VERSION,
    )


@pytest.mark.django_db
def test_projects_require_sign_in():
    response = APIClient().get(reverse("project-list"))

    assert response.status_code == 401


@pytest.mark.django_db
def test_create_project_records_owner_status_and_consent(alice):
    response = client_for(alice).post(reverse("project-list"), VALID_PROJECT, format="json")

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Bakery website"
    assert body["status"] == "interviewing"
    assert body["consent_version"] == CONSENT_VERSION
    assert body["consent_given_at"] is not None
    assert "consent" not in body

    project = Project.objects.get(id=body["id"])
    assert project.owner == alice


@pytest.mark.django_db
@pytest.mark.parametrize("consent", [False, None])
def test_project_without_consent_is_rejected(alice, consent):
    data = {**VALID_PROJECT, "consent": consent}
    if consent is None:
        del data["consent"]

    response = client_for(alice).post(reverse("project-list"), data, format="json")

    assert response.status_code == 400
    assert "consent" in response.json()
    assert not Project.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "field, value",
    [("name", ""), ("name", "x" * 121), ("project_type", "spaceship")],
)
def test_invalid_project_fields_are_rejected(alice, field, value):
    data = {**VALID_PROJECT, field: value}

    response = client_for(alice).post(reverse("project-list"), data, format="json")

    assert response.status_code == 400
    assert field in response.json()


@pytest.mark.django_db
def test_client_cannot_set_server_controlled_fields(alice, bob):
    data = {
        **VALID_PROJECT,
        "status": "sent_to_github",
        "owner": bob.id,
        "consent_version": "made-up",
    }

    response = client_for(alice).post(reverse("project-list"), data, format="json")

    project = Project.objects.get(id=response.json()["id"])
    assert project.status == "interviewing"
    assert project.owner == alice
    assert project.consent_version == CONSENT_VERSION


@pytest.mark.django_db
def test_list_shows_only_my_projects(alice, bob):
    make_project(alice, "Alice's app")
    make_project(bob, "Bob's app")

    response = client_for(alice).get(reverse("project-list"))

    assert response.status_code == 200
    assert [p["name"] for p in response.json()] == ["Alice's app"]


@pytest.mark.django_db
def test_owner_can_view_their_project(alice):
    project = make_project(alice)

    response = client_for(alice).get(reverse("project-detail", args=[project.id]))

    assert response.status_code == 200
    assert response.json()["id"] == project.id


@pytest.mark.django_db
def test_other_clients_project_is_not_found(alice, bob):
    bobs_project = make_project(bob)

    response = client_for(alice).get(reverse("project-detail", args=[bobs_project.id]))

    assert response.status_code == 404


@pytest.mark.django_db
def test_projects_cannot_be_changed_or_deleted_yet(alice):
    project = make_project(alice)
    url = reverse("project-detail", args=[project.id])

    assert client_for(alice).patch(url, {"name": "New"}, format="json").status_code == 405
    assert client_for(alice).delete(url).status_code == 405