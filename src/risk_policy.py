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

    # risk_index expresses the model's probability relative to the
    # average historical change (0.5 = average, see ticket_risk.
    # risk_summary). Real outcomes are skewed, so a raw probability of
    # 0.12 can mean "3x riskier than usual".
    prob = ml.get("risk_index", ml.get("risk_probability", 0.3))

    failed_similar = [
        s
        for s in similar
        if s.get("bad") or s.get("outcome") in ["Failed", "Caused-Incident"]
    ]

    # Similar past changes count against this one only when they went
    # wrong more often than changes in general did.
    base_rate = float(ml.get("base_rate") or 0.0)
    similar_failure_rate = (
        len(failed_similar) / len(similar) if similar else 0.0
    )
    similar_risk = (
        len(failed_similar) > 0
        and similar_failure_rate > 2 * base_rate
    )

    has_rollback = change.get("rollback_plan_exists") == "Yes"
    tested_rollback = change.get("rollback_plan_tested") == "Yes"

    # A rollback plan document was uploaded, but the deterministic
    # verification heuristic (src/document_verification.py) found it
    # does not actually substantiate a real rollback procedure - the
    # claim and the evidence disagree.
    rollback_doc_provided = bool(
        change.get("rollback_document_provided")
    )
    rollback_doc_verified = bool(
        change.get("rollback_document_verified")
    )
    evidence_mismatch = (
        has_rollback
        and rollback_doc_provided
        and not rollback_doc_verified
    )

    # Actual conflict reported for this specific change.
    actual_schedule_conflict = (
        change.get("schedule_conflict") == "Yes"
    )

    # Historical evidence about the requested window.
    schedule_conflict_frequency = float(
        schedule.get("conflict_frequency", 0)
    )

    historical_schedule_risk = (
        bool(schedule.get("high_risk_window"))
        or schedule_conflict_frequency > 0.3
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

    if similar_risk:
        score += 0.15

    if evidence_mismatch:
        score += 0.2

    if score >= 0.55:
        recommendation = "REJECT"
        risk_level = "High"
    elif score >= 0.30:
        recommendation = "REVIEW"
        risk_level = "Medium"
    else:
        recommendation = "APPROVE"
        risk_level = "Low"

    # A rollback claim contradicted by its own document is a credibility
    # problem, not a statistical one: never auto-approve it, however
    # safe the model thinks the change is.
    if evidence_mismatch and recommendation == "APPROVE":
        recommendation = "REVIEW"
        risk_level = "Medium"

    # Without a way back, a change that fails stays failed - however
    # unlikely the model thinks failure is. A person must accept that.
    # (Code changes count as revertible unless they alter a database
    # schema with no reverse migration; see agent.code_rollback_readiness.)
    if not has_rollback and recommendation == "APPROVE":
        recommendation = "REVIEW"
        risk_level = "Medium"

    # Text written to manipulate the reviewer (flagged by RedTeamGPT, see
    # prompt_guard.py) says nothing about technical risk, so it does not
    # move the score - but a person must look at a change that contains it.
    prompt_injection = bool(change.get("prompt_injection_flagged"))
    if prompt_injection and recommendation == "APPROVE":
        recommendation = "REVIEW"
        risk_level = "Medium"

    return {
        "score": round(score, 3),
        "recommendation": recommendation,
        "risk_level": risk_level,
        "failed_similar_count": len(failed_similar),
        "similar_failure_rate": round(similar_failure_rate, 3),
        "similar_risk": similar_risk,
        "has_rollback": has_rollback,
        "tested_rollback": tested_rollback,
        "has_schedule_conflict": actual_schedule_conflict,
        "historical_schedule_risk": historical_schedule_risk,
        "schedule_conflict_frequency": round(
            schedule_conflict_frequency,
            3,
        ),
        "rollback_document_provided": rollback_doc_provided,
        "rollback_document_verified": rollback_doc_verified,
        "evidence_mismatch": evidence_mismatch,
        "prompt_injection": prompt_injection,
    }