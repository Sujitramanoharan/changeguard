"""Unit tests for the deterministic risk policy.

This policy is the authoritative source of the APPROVE/REVIEW/REJECT
decision, so it is tested directly rather than only through the API -
the ML model and LLM are advisory inputs, not the decision-maker.
"""

from risk_policy import calculate_risk_policy


def make_change(**overrides):
    change = {
        "rollback_plan_exists": "Yes",
        "rollback_plan_tested": "Yes",
        "schedule_conflict": "No",
    }
    change.update(overrides)
    return change


def test_low_risk_change_is_approved():
    result = calculate_risk_policy(
        ml={"risk_probability": 0.1},
        change=make_change(),
        similar=[],
        schedule={"conflict_frequency": 0.0},
    )

    assert result["recommendation"] == "APPROVE"
    assert result["risk_level"] == "Low"


def test_missing_rollback_plan_escalates_risk():
    baseline = calculate_risk_policy(
        ml={"risk_probability": 0.1},
        change=make_change(),
        similar=[],
        schedule={"conflict_frequency": 0.0},
    )

    no_rollback = calculate_risk_policy(
        ml={"risk_probability": 0.1},
        change=make_change(rollback_plan_exists="No"),
        similar=[],
        schedule={"conflict_frequency": 0.0},
    )

    assert no_rollback["score"] > baseline["score"]
    assert no_rollback["has_rollback"] is False


def test_untested_rollback_penalized_less_than_missing_rollback():
    untested = calculate_risk_policy(
        ml={"risk_probability": 0.1},
        change=make_change(rollback_plan_tested="No"),
        similar=[],
        schedule={"conflict_frequency": 0.0},
    )

    missing = calculate_risk_policy(
        ml={"risk_probability": 0.1},
        change=make_change(rollback_plan_exists="No"),
        similar=[],
        schedule={"conflict_frequency": 0.0},
    )

    assert untested["score"] < missing["score"]


def test_actual_schedule_conflict_adds_risk():
    result = calculate_risk_policy(
        ml={"risk_probability": 0.1},
        change=make_change(schedule_conflict="Yes"),
        similar=[],
        schedule={"conflict_frequency": 0.0},
    )

    assert result["has_schedule_conflict"] is True
    assert result["score"] > 0.1 * 0.4


def test_historical_schedule_risk_without_actual_conflict():
    result = calculate_risk_policy(
        ml={"risk_probability": 0.1},
        change=make_change(schedule_conflict="No"),
        similar=[],
        schedule={"conflict_frequency": 0.5},
    )

    assert result["has_schedule_conflict"] is False
    assert result["historical_schedule_risk"] is True
    assert result["score"] > 0.1 * 0.4


def test_failed_similar_changes_add_risk():
    result = calculate_risk_policy(
        ml={"risk_probability": 0.1},
        change=make_change(),
        similar=[{"outcome": "Failed"}, {"outcome": "Success"}],
        schedule={"conflict_frequency": 0.0},
    )

    assert result["failed_similar_count"] == 1
    assert result["score"] > 0.1 * 0.4


def test_high_probability_missing_rollback_and_conflict_is_rejected():
    result = calculate_risk_policy(
        ml={"risk_probability": 0.9},
        change=make_change(
            rollback_plan_exists="No",
            schedule_conflict="Yes",
        ),
        similar=[{"outcome": "Caused-Incident"}],
        schedule={"conflict_frequency": 0.0},
    )

    assert result["recommendation"] == "REJECT"
    assert result["risk_level"] == "High"


def test_score_thresholds_are_exclusive_boundaries():
    # score == 0.30 -> REVIEW / Medium
    at_review_boundary = calculate_risk_policy(
        ml={"risk_probability": 0.75},
        change=make_change(),
        similar=[],
        schedule={"conflict_frequency": 0.0},
    )
    assert at_review_boundary["score"] == 0.3
    assert at_review_boundary["recommendation"] == "REVIEW"

    # 0.625*0.4 (0.25) + untested rollback (0.1) + schedule conflict (0.2)
    # == 0.55 -> REJECT / High
    at_reject_boundary = calculate_risk_policy(
        ml={"risk_probability": 0.625},
        change=make_change(
            rollback_plan_tested="No",
            schedule_conflict="Yes",
        ),
        similar=[],
        schedule={"conflict_frequency": 0.0},
    )
    assert at_reject_boundary["score"] == 0.55
    assert at_reject_boundary["recommendation"] == "REJECT"
