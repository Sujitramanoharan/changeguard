"""
ChangeGuard evidence tools.

Deterministic lookups (no AI) against statistics computed from the real
Rabobank change history at training time (models/ticket_stats.json),
plus the rollback readiness check. The agents call these to gather
evidence; the risk policy uses their results.
"""

from ticket_risk import WEEKDAYS, load_stats

# A historical rate needs this many past changes behind it to count.
MIN_SAMPLES = 50


def _rate(table: dict, key) -> dict | None:
    row = table.get(str(key))
    if not row or row["n"] < MIN_SAMPLES:
        return None
    return row


def get_incident_history(ticket: dict) -> dict:
    """How unstable is the affected system, and how do changes to this
    kind of system usually go?"""

    stats = load_stats()
    base = stats["base_rate"]
    recent = int(ticket.get("incidents_30d") or 0)
    subtype = ticket.get("ci_subtype")
    row = _rate(stats["rates"]["ci_subtype"], subtype)

    parts = [f"The affected system had {recent} incident(s) in the last 30 days."]

    if row:
        parts.append(
            f"Historically, {row['rate'] * 100:.1f}% of {row['n']:,} changes on "
            f"'{subtype}' systems were followed by more incidents "
            f"(vs {base * 100:.1f}% across all changes)."
        )
    else:
        parts.append(f"Too little history for '{subtype}' systems to compare.")

    return {
        "system_type": subtype,
        "incidents_30d": recent,
        "historical_rate": row["rate"] if row else None,
        "base_rate": base,
        "note": " ".join(parts),
    }


def check_schedule_conflict(ticket: dict) -> dict:
    """Are changes started at this day/hour historically riskier?"""

    stats = load_stats()
    base = stats["base_rate"]
    day = ticket.get("weekday")
    hour = ticket.get("hour")

    day_row = _rate(stats["rates"]["weekday"], day)
    hour_row = _rate(stats["rates"]["hour"], hour)

    parts, risky = [], False

    if day_row and day is not None:
        parts.append(
            f"Changes starting on {WEEKDAYS[int(day)]} raised incidents "
            f"{day_row['rate'] * 100:.1f}% of the time."
        )
        risky |= day_row["rate"] > 1.5 * base

    if hour_row and hour is not None:
        parts.append(
            f"Changes starting at {int(hour):02d}:00 raised incidents "
            f"{hour_row['rate'] * 100:.1f}% of the time."
        )
        risky |= hour_row["rate"] > 1.5 * base

    if not parts:
        parts.append("Not enough history for this start time.")

    parts.append(f"Average across all changes: {base * 100:.1f}%.")

    if risky:
        parts.append("This is a historically high-risk window.")

    return {
        "weekday": day,
        "hour": hour,
        "high_risk_window": risky,
        "note": " ".join(parts),
    }


def get_rollback_status(rollback_exists: str, rollback_tested: str) -> dict:
    """Assess the safety net for this change."""

    if rollback_exists != "Yes":
        level = "HIGH CONCERN"
        note = "No rollback plan exists - if this change fails, recovery is hard."
    elif rollback_tested == "Yes":
        level = "GOOD"
        note = "A tested rollback plan exists - recovery is well-prepared."
    else:
        level = "MODERATE CONCERN"
        note = "A rollback plan exists but has not been tested."

    return {
        "rollback_exists": rollback_exists,
        "rollback_tested": rollback_tested,
        "safety_level": level,
        "note": note,
    }


def describe_code_change(analysis: dict, metrics: dict) -> dict:
    """Summarise what a real code diff touches."""

    parts = [
        f"{metrics['nf']} file(s) across {metrics['nd']} director(ies) and "
        f"{metrics['ns']} top-level module(s): +{metrics['la']:,}/-{metrics['ld']:,} lines."
    ]

    kind = analysis.get("change_type")
    if kind == "Database-Schema-Change":
        parts.append("Touches database migrations or schema files.")
    elif kind == "Infrastructure-Change":
        parts.append("Touches infrastructure / deployment configuration.")
    elif kind == "Security-Patch":
        parts.append("Security-related change.")

    parts.append(
        "Test files were updated." if analysis.get("touches_tests")
        else "No test files were changed."
    )

    return {"note": " ".join(parts), "change_type": kind}
