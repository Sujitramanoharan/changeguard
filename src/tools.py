"""
ChangeGuard evidence tools.

Each function gathers one kind of real evidence about a change from the
historical dataset. The agent calls these to build its risk assessment.
These are deterministic lookups (no AI) - fast and reliable.
"""
import pandas as pd
from config import DATA_PATH

# Load the historical data once
_df = pd.read_csv(DATA_PATH)
_df["rollback_plan_tested"] = _df["rollback_plan_tested"].fillna("None")


def get_incident_history(system: str) -> dict:
    """How stable has this system been recently?"""
    rows = _df[_df["system"] == system]
    if len(rows) == 0:
        return {"system": system, "found": False,
                "note": "No historical data for this system."}
    avg_incidents = round(rows["system_incidents_last_90_days"].mean(), 2)
    bad = rows["outcome"].isin(["Failed", "Caused-Incident"]).mean()
    return {
        "system": system,
        "found": True,
        "avg_incidents_last_90_days": avg_incidents,
        "historical_failure_rate": round(float(bad), 3),
        "note": (f"{system} averages {avg_incidents} incidents/90 days; "
                 f"{round(bad*100)}% of its past changes went badly."),
    }


def check_schedule_conflict(requested_window: str) -> dict:
    """Are changes in this time window historically riskier?"""
    rows = _df[_df["requested_window"] == requested_window]
    if len(rows) == 0:
        return {"window": requested_window, "found": False,
                "note": "No historical data for this window."}
    bad = rows["outcome"].isin(["Failed", "Caused-Incident"]).mean()
    conflict_rate = (rows["schedule_conflict"] == "Yes").mean()
    return {
        "window": requested_window,
        "found": True,
        "historical_failure_rate": round(float(bad), 3),
        "conflict_frequency": round(float(conflict_rate), 3),
        "note": (f"Changes during {requested_window} fail {round(bad*100)}% of "
                 f"the time; {round(conflict_rate*100)}% had scheduling conflicts."),
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


if __name__ == "__main__":
    # quick test
    print(get_incident_history("Payments-Service"))
    print(check_schedule_conflict("Peak-Hours"))
    print(get_rollback_status("No", "None"))