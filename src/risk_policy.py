"""Shared deterministic risk policy for ChangeGuard."""

def calculate_risk_policy(
    ml,
    change,
    similar,
    schedule,
):
    """
    Calculate the authoritative recommendation and risk level.

    This preserves the existing controlled-agent fallback policy
    so both controlled and autonomous modes can use the same
    decision logic.
    """

    prob = ml.get("risk_probability", 0.3)

    failed_similar = [
        s
        for s in similar
        if s.get("outcome") in ["Failed", "Caused-Incident"]
    ]

    has_rollback = change.get("rollback_plan_exists") == "Yes"
    tested_rollback = change.get("rollback_plan_tested") == "Yes"

    has_conflict = (
        change.get("schedule_conflict") == "Yes"
        or schedule.get("conflict_frequency", 0) > 0.3
    )

    # Existing ChangeGuard composite risk policy.
    score = prob * 0.4

    if not has_rollback:
        score += 0.25
    elif not tested_rollback:
        score += 0.1

    if has_conflict:
        score += 0.2

    if len(failed_similar) > 0:
        score += 0.15

    if score >= 0.55:
        recommendation = "REJECT"
        risk_level = "High"
    elif score >= 0.30:
        recommendation = "REVIEW"
        risk_level = "Medium"
    else:
        recommendation = "APPROVE"
        risk_level = "Low"

    return {
        "score": round(score, 3),
        "recommendation": recommendation,
        "risk_level": risk_level,
        "failed_similar_count": len(failed_similar),
        "has_rollback": has_rollback,
        "tested_rollback": tested_rollback,
        "has_schedule_conflict": has_conflict,
    }
