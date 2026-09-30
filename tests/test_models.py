"""Tests for the real-data risk models and their feature extraction."""

import json
import math

import pytest

import agent
import code_risk
import ticket_risk
from config import METRICS_PATH


# -------------------------------------------------------------------
# Code metrics from a GitHub diff (must match ApacheJIT's definitions)
# -------------------------------------------------------------------

def gh_file(name, added, deleted):
    return {"filename": name, "additions": added, "deletions": deleted}


def test_code_metrics_counts():
    m = code_risk.metrics_from_files([
        gh_file("core/src/a.py", 10, 2),
        gh_file("core/src/b.py", 5, 0),
        gh_file("docs/readme.md", 1, 1),
    ])

    assert m["la"] == 16
    assert m["ld"] == 3
    assert m["nf"] == 3
    assert m["nd"] == 2  # core/src, docs
    assert m["ns"] == 2  # core, docs


def test_code_metrics_entropy_is_shannon_over_modified_lines():
    even = code_risk.metrics_from_files([gh_file("a.py", 5, 0), gh_file("b.py", 5, 0)])
    single = code_risk.metrics_from_files([gh_file("a.py", 50, 0)])

    assert even["ent"] == pytest.approx(1.0)
    assert single["ent"] == 0.0

    skewed = code_risk.metrics_from_files([gh_file("a.py", 3, 0), gh_file("b.py", 1, 0)])
    expected = -(0.75 * math.log2(0.75) + 0.25 * math.log2(0.25))
    assert skewed["ent"] == pytest.approx(expected, abs=1e-4)


def test_root_level_files_count_as_one_subsystem():
    m = code_risk.metrics_from_files([gh_file("setup.py", 1, 0), gh_file("README.md", 1, 0)])

    assert m["ns"] == 1


def test_bigger_commits_score_riskier():
    small = code_risk.predict({"la": 3, "ld": 1, "nf": 1, "nd": 1, "ns": 1, "ent": 0.0})
    large = code_risk.predict({"la": 2000, "ld": 300, "nf": 40, "nd": 15, "ns": 5, "ent": 4.5})

    assert large["risk_probability"] > small["risk_probability"]
    assert large["risk_level"] == "High"
    assert small["risk_level"] == "Low"
    assert small["factors"] and "label" in small["factors"][0]


# -------------------------------------------------------------------
# Ticket model
# -------------------------------------------------------------------

BASE_TICKET = {
    "ci_type": "computer",
    "ci_subtype": "Windows Server",
    "change_family": "Standard Change Type",
    "risk_classification": "Minor Change",
    "origin": "Problem",
    "incidents_30d": 0,
    "planned_start": "2026-10-06T10:00",
    "planned_hours": 1,
    "systems_affected": 1,
    "downtime": False,
    "emergency": False,
    "cab_required": False,
}


def test_prepare_ticket_derives_start_day_and_hour():
    t = agent.prepare_ticket({**BASE_TICKET, "planned_start": "2026-10-10T21:30"})

    assert t["weekday"] == 5  # Saturday
    assert t["hour"] == 21
    assert t["emergency"] == 0


def test_recent_incidents_raise_ticket_risk():
    calm = ticket_risk.predict(agent.prepare_ticket(BASE_TICKET))
    noisy = ticket_risk.predict(agent.prepare_ticket({
        **BASE_TICKET,
        "ci_type": "application",
        "ci_subtype": "Web Based Application",
        "incidents_30d": 30,
    }))

    assert noisy["relative_risk"] > calm["relative_risk"]
    assert calm["risk_level"] == "Low"


def test_unknown_category_does_not_crash():
    result = ticket_risk.predict(agent.prepare_ticket({**BASE_TICKET, "ci_subtype": "Brand New Thing"}))

    assert 0.0 <= result["risk_probability"] <= 1.0


def test_similar_changes_are_distinct_real_records():
    similar = agent.similar_tickets(agent.prepare_ticket(BASE_TICKET))

    assert len(similar) == 5
    assert len({s["change_id"] for s in similar}) == 5
    assert all(s["outcome"] in ("Incidents increased", "No increase") for s in similar)


def test_risk_summary_levels():
    assert ticket_risk.risk_summary(0.02, 0.05)["risk_level"] == "Low"
    assert ticket_risk.risk_summary(0.07, 0.05)["risk_level"] == "Medium"
    assert ticket_risk.risk_summary(0.20, 0.05)["risk_level"] == "High"
    assert ticket_risk.risk_summary(0.05, 0.05)["risk_index"] == pytest.approx(0.5)


# -------------------------------------------------------------------
# Code rollback readiness rules
# -------------------------------------------------------------------

def test_migration_without_reverse_path_has_no_rollback():
    exists, tested, _ = agent.code_rollback_readiness({
        "change_type": "Database-Schema-Change",
        "analysis": {"detected_rollback_language": False, "touches_tests": True},
    })

    assert (exists, tested) == ("No", "None")


def test_code_change_is_revertible_and_tests_count():
    exists, tested, _ = agent.code_rollback_readiness({
        "change_type": "Deployment",
        "analysis": {"detected_rollback_language": False, "touches_tests": False},
    })

    assert (exists, tested) == ("Yes", "No")


# -------------------------------------------------------------------
# Shipped models meet their reported quality
# -------------------------------------------------------------------

def test_saved_metrics_are_real_and_reasonable():
    metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))["models"]

    assert metrics["ticket"]["roc_auc"] > 0.8
    assert metrics["code"]["roc_auc"] > 0.75
    assert metrics["code"]["unseen_projects_roc_auc"] > 0.75
    # The model must beat the simple baselines it is compared against.
    assert metrics["ticket"]["roc_auc"] > max(metrics["ticket"]["baselines"].values())
    assert metrics["code"]["roc_auc"] > max(metrics["code"]["baselines"].values())


@pytest.mark.parametrize("flag", ["emergency", "cab_required", "downtime"])
def test_risk_flags_never_lower_risk(flag):
    # Monotonic constraints: switching one of these on can only raise
    # the predicted risk, for any kind of change.
    stats = ticket_risk.load_stats()["options"]

    for ci_type in stats["ci_type"][:6]:
        for subtype in stats["ci_subtype_by_type"][ci_type][:3]:
            ticket = agent.prepare_ticket({**BASE_TICKET, "ci_type": ci_type, "ci_subtype": subtype})
            off = ticket_risk.predict({**ticket, flag: 0})["risk_probability"]
            on = ticket_risk.predict({**ticket, flag: 1})["risk_probability"]

            assert on >= off, (flag, ci_type, subtype)


def test_more_incidents_never_lower_risk():
    ticket = agent.prepare_ticket(BASE_TICKET)
    probs = [
        ticket_risk.predict({**ticket, "incidents_30d": n})["risk_probability"]
        for n in (0, 1, 5, 20, 100)
    ]

    assert probs == sorted(probs)


def test_rare_flags_do_not_dominate_similarity():
    # A rare flag (88 emergency changes out of 26,000) must not pull in
    # emergency changes on unrelated systems.
    ticket = agent.prepare_ticket({**BASE_TICKET, "emergency": True})

    similar = agent.similar_tickets(ticket)

    assert all(s["system"].startswith("Windows Server") for s in similar)


def test_release_changes_never_look_safer_than_standard_changes():
    # In the real data releases were followed by more incidents twice as
    # often as standard changes; the model must never say the opposite.
    stats = ticket_risk.load_stats()["options"]

    for ci_type in stats["ci_type"][:6]:
        subtype = stats["ci_subtype_by_type"][ci_type][0]
        ticket = agent.prepare_ticket({**BASE_TICKET, "ci_type": ci_type, "ci_subtype": subtype})

        standard = ticket_risk.predict({**ticket, "change_family": "Standard Change Type"})
        release = ticket_risk.predict({**ticket, "change_family": "Release Type"})

        assert release["risk_probability"] >= standard["risk_probability"], ci_type
