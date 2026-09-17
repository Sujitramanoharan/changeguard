"""Shared deterministic risk policy for ChangeGuard."""


def calculate_risk_policy(
    ml,
    change,
    similar,
    schedule,
):
    """
    Calculate the authoritative recommendation and risk level.

    The deterministic policy remains authoritative for the final
    recommendation and risk level. Historical schedule evidence is
    tracked separately from an actual conflict on the submitted change.
    """

    prob = ml.get("risk_probability", 0.3)

    failed_similar = [
        s
        for s in similar
        if s.get("outcome") in ["Failed", "Caused-Incident"]
    ]

    has_rollback = change.get("rollback_plan_exists") == "Yes"
    tested_rollback = change.get("rollback_plan_tested") == "Yes"

    # Actual conflict reported for this specific change.
    actual_schedule_conflict = (
        change.get("schedule_conflict") == "Yes"
    )

    # Historical evidence about conflicts in the requested window.
    schedule_conflict_frequency = float(
        schedule.get("conflict_frequency", 0)
    )

    historical_schedule_risk = (
        schedule_conflict_frequency > 0.3
    )

    # Schedule contributes to the risk score when either:
    # 1. this specific change has an actual conflict, or
    # 2. historical data shows a high-conflict requested window.
    schedule_risk = (
        actual_schedule_conflict
        or historical_schedule_risk
    )

    # Existing ChangeGuard composite risk policy.
    score = prob * 0.4

    if not has_rollback:
        score += 0.25
    elif not tested_rollback:
        score += 0.1

    if schedule_risk:
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
        "has_schedule_conflict": actual_schedule_conflict,
        "historical_schedule_risk": historical_schedule_risk,
        "schedule_conflict_frequency": round(
            schedule_conflict_frequency,
            3,
        ),
    }