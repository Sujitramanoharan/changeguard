"""Test that the login endpoint is rate-limited against brute force."""

from fastapi.testclient import TestClient

from backend.main import app


def test_login_is_rate_limited_after_repeated_attempts():
    client = TestClient(app)

    payload = {"username": "nonexistent-user", "password": "wrong"}

    statuses = [
        client.post("/api/auth/login", json=payload).status_code
        for _ in range(7)
    ]

    assert 401 in statuses
    assert 429 in statuses
    assert statuses[-1] == 429
