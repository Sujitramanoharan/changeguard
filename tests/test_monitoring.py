"""Monitoring metrics and the gated retraining loop."""

import importlib.util
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import backend.main as main
import monitoring
from backend.auth import create_access_token
from backend.database import create_user

ROOT = Path(__file__).parent.parent


def assessment(rec, decision=None, outcome=None, by="cab-user", start="2026-10-06T10:00",
               kind="ticket", guard=None, created="2026-10-06 10:00", **change):
    details = {"kind": kind, "change": {"planned_start": start, **change}}
    if kind == "code":
        details["code_metrics"] = change
    if guard:
        details["prompt_guard"] = {"status": guard}
    return {
        "recommendation": rec, "cab_decision": decision, "cab_decided_by": by,
        "actual_outcome": outcome, "outcome_recorded_by": by if outcome else None,
        "assessment_type": kind, "created_at": created, "details": details,
    }


# -------------------------------------------------------------------
# Drift
# -------------------------------------------------------------------

def test_psi_is_zero_for_identical_and_large_for_shifted_distributions():
    assert monitoring.psi([0.25, 0.25, 0.5], [0.25, 0.25, 0.5]) == 0
    assert monitoring.psi([0.5, 0.5], [0.95, 0.05]) > monitoring.PSI_SIGNIFICANT


def test_reference_profile_and_drift_detection():
    rng = np.random.default_rng(0)
    train = pd.DataFrame({"planned_hours": rng.normal(10, 2, 5000), "ci_type": rng.choice(["a", "b"], 5000)})
    ref = monitoring.build_reference(train, ["planned_hours"], ["ci_type"], "test")
    spec = ref["features"]["planned_hours"]

    same = rng.normal(10, 2, 400)
    shifted = rng.normal(16, 2, 400)

    psi_same = monitoring.psi(monitoring._expected(spec), monitoring._live_proportions(spec, same))
    psi_shift = monitoring.psi(monitoring._expected(spec), monitoring._live_proportions(spec, shifted))

    assert monitoring.drift_status(psi_same) == "stable"
    assert monitoring.drift_status(psi_shift) == "significant"


def test_drift_needs_a_minimum_sample(monkeypatch):
    items = [assessment("APPROVE", planned_hours=2)] * 5
    report = monitoring.drift_report(items, {"ticket": {"rows": 1, "features": {}}})
    assert report["ticket"]["status"] == "insufficient"
    assert report["code"]["status"] == "no_reference"


def test_reference_profile_is_shipped_for_both_models():
    reference = monitoring.load_reference()
    assert reference["ticket"]["rows"] == 20860
    assert reference["code"]["rows"] == 85339


# -------------------------------------------------------------------
# Trust, outcomes, screening, volume
# -------------------------------------------------------------------

def test_cab_override_rate_counts_only_firm_recommendations():
    items = [
        assessment("APPROVE", "APPROVE"),
        assessment("APPROVE", "REJECT"),      # override
        assessment("REJECT", "REJECT"),
        assessment("REVIEW", "APPROVE"),      # not an override
        assessment("REJECT"),                 # pending
    ]
    cab = monitoring.cab_report(items)

    assert cab["decided"] == 4 and cab["pending"] == 1
    assert cab["firm_recommendations_decided"] == 3
    assert cab["overrides"] == 1
    assert cab["override_rate"] == round(1 / 3, 3)
    assert cab["matrix"]["APPROVE"] == {"APPROVE": 1, "REJECT": 1}


def test_outcomes_compare_flagged_with_approved_and_label_demo_rows():
    items = [
        assessment("APPROVE", "APPROVE", "Success"),
        assessment("APPROVE", "APPROVE", "Failed"),
        assessment("REVIEW", "APPROVE", "Caused-Incident"),
        assessment("REVIEW", "APPROVE", "Success", by=monitoring.DEMO_USER),
    ]
    report = monitoring.outcome_report(items)

    assert report["recorded"] == 4 and report["real"] == 3 and report["demo"] == 1
    assert report["ai_approved"] == {"n": 2, "bad": 1, "bad_rate": 0.5}
    assert report["ai_flagged"] == {"n": 2, "bad": 1, "bad_rate": 0.5}


def test_screening_report_counts_statuses():
    items = [assessment("APPROVE", guard="clean"), assessment("REVIEW", guard="flagged"),
             assessment("APPROVE", guard="unavailable"), assessment("APPROVE")]
    report = monitoring.screening_report(items)
    assert report == {"screened": 2, "clean": 1, "flagged": 1, "unavailable": 1, "not_screened": 1}


def test_volume_is_bucketed_by_day_and_verdict():
    items = [assessment("APPROVE", created="2026-10-06 09:00"),
             assessment("REJECT", created="2026-10-06 15:00"),
             assessment("REVIEW", created="2026-09-01 10:00")]
    report = monitoring.volume_report(items, days=7, today=datetime(2026, 10, 6))

    assert report["in_window"] == 2
    assert report["by_day"][-1] == {"date": "2026-10-06", "APPROVE": 1, "REVIEW": 0, "REJECT": 1}


def test_monitoring_endpoint_requires_login_and_returns_report():
    client = TestClient(main.app)
    assert client.get("/api/monitoring").status_code == 401

    create_user(username="monitor-user", password="password123", role="reviewer")
    token = create_access_token(username="monitor-user", role="reviewer")
    body = client.get("/api/monitoring", headers={"Authorization": f"Bearer {token}"}).json()

    for key in ("volume", "cab", "outcomes", "drift", "screening", "models", "retraining"):
        assert key in body


# -------------------------------------------------------------------
# Gated retraining
# -------------------------------------------------------------------

@pytest.fixture
def retrainer(monkeypatch, tmp_path):
    """The retraining script on a tiny synthetic problem, writing to tmp_path."""

    spec = importlib.util.spec_from_file_location("retrain", ROOT / "scripts" / "retrain_with_feedback.py")
    rt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rt)

    import joblib
    from sklearn.linear_model import LogisticRegression

    rng = np.random.default_rng(1)
    X = pd.DataFrame({"x": rng.normal(size=600)})
    y = pd.Series((X.x + rng.normal(scale=0.5, size=600) > 0).astype(int))
    model_path = tmp_path / "model.pkl"
    joblib.dump({"model": LogisticRegression().fit(X[:400], y[:400])}, model_path)

    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text(json.dumps({"models": {"toy": {"roc_auc": 0.9}}}))

    state = {"feedback": [], "flip": False}

    def data(bundle, items):
        fb_X = pd.DataFrame({"x": [3.0] * len(items)})
        fb_y = pd.Series([1 - int(state["flip"])] * len(items), dtype=int)
        return X[:400], y[:400], X[400:], y[400:].values, fb_X, fb_y

    monkeypatch.setitem(rt.MODELS, "toy", {"path": model_path, "data": data, "new": LogisticRegression})
    monkeypatch.setattr(rt, "feedback_items", lambda kind: (state["feedback"], 3))
    monkeypatch.setattr(rt, "METRICS_PATH", metrics_path)
    monkeypatch.setattr(rt, "ARCHIVE_DIR", tmp_path / "archive")
    return rt, state, model_path, metrics_path, tmp_path


def test_no_real_outcomes_means_nothing_is_retrained(retrainer):
    rt, _, _, _, _ = retrainer
    entry = rt.retrain("toy", weight=5, dry_run=False, force=False)

    assert entry["decision"] == "skipped"
    assert entry["demo_skipped"] == 3


def test_candidate_that_is_not_worse_is_promoted_and_old_model_archived(retrainer):
    rt, state, _, metrics_path, tmp_path = retrainer
    state["feedback"] = [{"actual_outcome": "Failed"}] * 4

    entry = rt.retrain("toy", weight=1, dry_run=False, force=False)

    assert entry["decision"] == "promoted"
    assert entry["candidate_roc_auc"] >= entry["current_roc_auc"]
    assert list((tmp_path / "archive").iterdir())
    assert json.loads(metrics_path.read_text())["models"]["toy"]["feedback_rows"] == 4


def test_worse_candidate_is_rejected_by_the_gate(retrainer):
    rt, state, model_path, _, tmp_path = retrainer
    # Heavily weighted feedback that contradicts the real pattern.
    state["feedback"] = [{"actual_outcome": "Success"}] * 50
    state["flip"] = True
    before = model_path.read_bytes()

    entry = rt.retrain("toy", weight=500, dry_run=False, force=False)

    assert entry["decision"] == "kept"
    assert entry["candidate_roc_auc"] < entry["current_roc_auc"]
    assert model_path.read_bytes() == before
    assert not (tmp_path / "archive").exists()


def test_dry_run_never_replaces_the_model(retrainer):
    rt, state, model_path, _, _ = retrainer
    state["feedback"] = [{"actual_outcome": "Failed"}] * 4
    before = model_path.read_bytes()

    entry = rt.retrain("toy", weight=1, dry_run=True, force=False)

    assert entry["decision"] == "would_promote"
    assert model_path.read_bytes() == before
