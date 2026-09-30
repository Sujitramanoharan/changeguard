"""API-level tests: authorization, security fixes, and the CAB workflow.

The heavy ML/LLM pipeline is replaced with a fake so these tests exercise
only the HTTP layer and its guarantees.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

import backend.main as main
from backend.auth import create_access_token
from backend.database import create_user


CHANGE = {
    "title": "Patch Windows servers",
    "ci_type": "computer",
    "ci_subtype": "Windows Server",
    "change_family": "Standard Change Type",
    "risk_classification": "Minor Change",
    "origin": "Problem",
    "incidents_30d": 0,
    "planned_start": "2026-10-06T10:00",
    "planned_hours": 2,
    "systems_affected": 1,
    "downtime": False,
    "emergency": False,
    "cab_required": False,
    "rollback_plan_exists": "Yes",
    "rollback_plan_tested": "Yes",
    "schedule_conflict": "No",
    "description": "API test change.",
}

GOOD_DOC = b"""Rollback Procedure

1. Disable the feature flag to stop new writes.
2. Restore the database from the pre-change snapshot.
3. Revert the deployment to the previous release.
4. Verify recovery and notify the on-call channel.
"""


def make_user(role):
    username = f"{role}-{uuid.uuid4().hex[:8]}"
    create_user(username=username, password="password123", role=role)
    token = create_access_token(username=username, role=role)
    return username, {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client():
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def fake_pipeline(monkeypatch):
    """Replace the real pipeline; record the change it was given."""

    seen = {}

    def fake_assess_ticket(change):
        seen["change"] = change
        return {
            "ml_prediction": {"risk_probability": 0.1, "risk_level": "Low"},
            "similar_changes": [],
            "evidence": {},
            "policy": {
                "recommendation": seen.get("recommendation", "APPROVE"),
                "risk_level": "Low",
                "score": 0.04,
            },
            "explanation_source": "fallback",
            "assessment": "JUSTIFICATION: Test justification.",
        }

    monkeypatch.setattr(main, "assess_ticket", fake_assess_ticket)
    return seen


# -------------------------------------------------------------------
# Authorization
# -------------------------------------------------------------------

def test_assess_requires_authentication(client):
    assert client.post("/api/assess", json=CHANGE).status_code == 401


def test_reviewer_cannot_use_autonomous_mode(client):
    _, headers = make_user("reviewer")

    resp = client.post("/api/assess-autonomous", json=CHANGE, headers=headers)

    assert resp.status_code == 403


def test_reviewer_cannot_manage_users(client):
    _, headers = make_user("reviewer")

    assert client.get("/api/admin/users", headers=headers).status_code == 403


# -------------------------------------------------------------------
# Security fixes
# -------------------------------------------------------------------

def test_spa_route_blocks_path_traversal(client, monkeypatch, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>app</html>")
    (tmp_path / "secret.env").write_text("SECRET=leaked")

    monkeypatch.setattr(main, "DIST_DIR", dist)

    for path in ["/%2e%2e/secret.env", "/..%2fsecret.env"]:
        resp = client.get(path)
        assert "leaked" not in resp.text
        assert "app" in resp.text  # falls back to the SPA shell


def test_unhandled_error_returns_json_500(client, monkeypatch):
    _, headers = make_user("reviewer")

    def boom():
        raise RuntimeError("unexpected")

    monkeypatch.setattr(main, "get_stats", boom)

    resp = client.get("/api/stats", headers=headers)

    assert resp.status_code == 500
    assert resp.json()["error"] == "Internal server error"


def test_client_cannot_claim_document_was_verified(client, fake_pipeline):
    _, headers = make_user("reviewer")

    # Old-style booleans from the client are ignored entirely.
    payload = {
        **CHANGE,
        "rollback_document_provided": True,
        "rollback_document_verified": True,
    }
    assert client.post("/api/assess", json=payload, headers=headers).status_code == 200
    assert fake_pipeline["change"]["rollback_document_provided"] is False
    assert fake_pipeline["change"]["rollback_document_verified"] is False

    # A made-up verification ID is rejected.
    payload = {**CHANGE, "rollback_document_id": "does-not-exist"}
    assert client.post("/api/assess", json=payload, headers=headers).status_code == 400


def test_document_verification_is_bound_to_assessment(client, fake_pipeline):
    _, headers = make_user("reviewer")

    upload = client.post(
        "/api/documents/verify-rollback",
        files={"file": ("rollback.txt", GOOD_DOC, "text/plain")},
        headers=headers,
    ).json()

    assert upload["verified"] is True

    payload = {**CHANGE, "rollback_document_id": upload["verification_id"]}
    assert client.post("/api/assess", json=payload, headers=headers).status_code == 200

    assert fake_pipeline["change"]["rollback_document_provided"] is True
    assert fake_pipeline["change"]["rollback_document_verified"] is True


def test_cannot_use_another_users_document(client, fake_pipeline):
    _, owner = make_user("reviewer")
    _, other = make_user("reviewer")

    upload = client.post(
        "/api/documents/verify-rollback",
        files={"file": ("rollback.txt", GOOD_DOC, "text/plain")},
        headers=owner,
    ).json()

    payload = {**CHANGE, "rollback_document_id": upload["verification_id"]}

    assert client.post("/api/assess", json=payload, headers=other).status_code == 400


# -------------------------------------------------------------------
# Human CAB decision and outcome
# -------------------------------------------------------------------

def create_assessment(client, headers):
    resp = client.post("/api/assess", json=CHANGE, headers=headers)
    assert resp.status_code == 200
    return resp.json()["id"]


def test_override_requires_comment(client, fake_pipeline):
    _, headers = make_user("reviewer")
    assessment_id = create_assessment(client, headers)  # AI says APPROVE

    resp = client.post(
        f"/api/assessments/{assessment_id}/decision",
        json={"decision": "REJECT", "comment": ""},
        headers=headers,
    )
    assert resp.status_code == 400

    resp = client.post(
        f"/api/assessments/{assessment_id}/decision",
        json={"decision": "REJECT", "comment": "Freeze window this week."},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["cab_decision"] == "REJECT"


def test_decision_and_outcome_flow(client, fake_pipeline):
    username, headers = make_user("reviewer")
    assessment_id = create_assessment(client, headers)

    # No outcome before the CAB approves.
    resp = client.post(
        f"/api/assessments/{assessment_id}/outcome",
        json={"outcome": "Success"},
        headers=headers,
    )
    assert resp.status_code == 400

    resp = client.post(
        f"/api/assessments/{assessment_id}/decision",
        json={"decision": "APPROVE"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["cab_decided_by"] == username

    resp = client.post(
        f"/api/assessments/{assessment_id}/outcome",
        json={"outcome": "Failed"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["actual_outcome"] == "Failed"

    stats = client.get("/api/stats", headers=headers).json()
    assert stats["outcomes_recorded"] >= 1
    assert stats["bad_outcomes"] >= 1


# -------------------------------------------------------------------
# User management
# -------------------------------------------------------------------

def test_admin_can_create_and_delete_users(client):
    admin, headers = make_user("admin")
    new_name = f"new-{uuid.uuid4().hex[:6]}"

    resp = client.post(
        "/api/admin/users",
        json={"username": new_name, "password": "longpassword", "role": "reviewer"},
        headers=headers,
    )
    assert resp.status_code == 201
    assert "password_hash" not in resp.json()

    listed = client.get("/api/admin/users", headers=headers).json()
    assert any(u["username"] == new_name for u in listed)
    assert all("password_hash" not in u for u in listed)

    assert client.delete(f"/api/admin/users/{new_name}", headers=headers).status_code == 200
    assert client.delete(f"/api/admin/users/{admin}", headers=headers).status_code == 400


# -------------------------------------------------------------------
# Real-data endpoints
# -------------------------------------------------------------------

def test_form_options_come_from_real_data(client):
    _, headers = make_user("reviewer")

    options = client.get("/api/form-options", headers=headers).json()

    assert "Windows Server" in options["ci_subtype_by_type"]["computer"]
    assert "Release Type" in options["change_family"]


def test_ticket_with_mismatched_subtype_is_rejected(client, fake_pipeline):
    _, headers = make_user("reviewer")

    payload = {**CHANGE, "ci_type": "computer", "ci_subtype": "Firewall"}

    assert client.post("/api/assess", json=payload, headers=headers).status_code == 422


def test_code_assessment_refetches_diff_server_side(client, monkeypatch):
    _, headers = make_user("reviewer")
    fetched = []

    analysis = {
        "system": "acme/api",
        "change_type": "Deployment",
        "description": "[Auto-analyzed] tiny fix",
        "rollback_plan_exists": "No",
        "rollback_plan_tested": "None",
        "code_metrics": {"la": 3, "ld": 1, "nf": 1, "nd": 1, "ns": 1, "ent": 0.0},
        "analysis": {"author": "dev", "touches_tests": True, "detected_rollback_language": False},
    }

    def fake_analyze(url):
        fetched.append(url)
        return analysis

    monkeypatch.setattr(main, "analyze_github_url", fake_analyze)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    url = "https://github.com/acme/api/commit/abc1234"
    resp = client.post("/api/assess-code", json={"url": url}, headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert fetched == [url]
    assert body["kind"] == "code"
    assert body["code_metrics"]["la"] == 3
    assert body["recommendation"] == "APPROVE"

    saved = client.get(f"/api/assessments/{body['id']}", headers=headers).json()
    assert saved["assessment_type"] == "code"
    assert saved["change_type"] == "Code change"


# -------------------------------------------------------------------
# GitHub pull-request check
# -------------------------------------------------------------------

PR = {
    "repo": "acme/payments",
    "pr_number": 42,
    "url": "https://github.com/acme/payments/pull/42",
    "title": "Add split payments column",
    "body": "Adds a nullable column.",
    "author": "dev",
    "files": [
        {"filename": "db/migrations/0042_split.sql", "additions": 30, "deletions": 0},
        {"filename": "app/payments.py", "additions": 60, "deletions": 10},
    ],
}


def test_pr_check_is_disabled_without_configured_key(client, monkeypatch):
    monkeypatch.delenv("CHANGEGUARD_CI_API_KEY", raising=False)

    assert client.post("/api/ci/pr-check", json=PR).status_code == 503


def test_pr_check_rejects_missing_or_wrong_key(client, monkeypatch):
    monkeypatch.setenv("CHANGEGUARD_CI_API_KEY", "s3cret-key")

    assert client.post("/api/ci/pr-check", json=PR).status_code == 401
    assert client.post(
        "/api/ci/pr-check", json=PR, headers={"X-ChangeGuard-Key": "wrong"}
    ).status_code == 401


def test_pr_check_assesses_and_returns_comment(client, monkeypatch):
    monkeypatch.setenv("CHANGEGUARD_CI_API_KEY", "s3cret-key")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    resp = client.post("/api/ci/pr-check", json=PR, headers={"X-ChangeGuard-Key": "s3cret-key"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["recommendation"] in ("APPROVE", "REVIEW", "REJECT")
    assert "<!-- changeguard-pr-check -->" in body["comment"]
    assert f"#{body['id']}" in body["comment"]
    assert body["details_url"].endswith(f"/history?id={body['id']}")

    # Migration file with no reverse path -> no rollback, so not approved.
    assert body["recommendation"] != "APPROVE"

    # Saved to the audit trail as a GitHub PR check, awaiting a CAB decision.
    _, headers = make_user("reviewer")
    saved = client.get(f"/api/assessments/{body['id']}", headers=headers).json()
    assert saved["assessment_type"] == "code"
    assert saved["mode"] == "ci"
    assert saved["details"]["user"]["username"] == "github-actions"
    assert saved["cab_decision"] is None
