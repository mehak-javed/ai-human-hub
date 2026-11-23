from django.urls import reverse
from rest_framework.test import APIClient


def test_health_returns_ok():
    response = APIClient().get(reverse("health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_rejects_post():
    response = APIClient().post(reverse("health"))

    assert response.status_code == 405


def test_health_allows_the_frontend_origin():
    response = APIClient().get(reverse("health"), HTTP_ORIGIN="http://localhost:3000")

    assert response["Access-Control-Allow-Origin"] == "http://localhost:3000"


def test_health_does_not_allow_unknown_origins():
    response = APIClient().get(reverse("health"), HTTP_ORIGIN="https://evil.example")

    assert "Access-Control-Allow-Origin" not in response