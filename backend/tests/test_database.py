import pytest
from django.contrib.auth import get_user_model
from django.db import connection


@pytest.mark.django_db
def test_database_is_postgresql():
    assert connection.vendor == "postgresql"


@pytest.mark.django_db
def test_can_save_and_read_a_user():
    User = get_user_model()
    User.objects.create_user(username="alice", password="test-only-password")

    assert User.objects.filter(username="alice").exists()