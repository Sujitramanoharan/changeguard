"""Build backend-derived historical context for ChangeGuard."""

from retrieval import find_similar_changes
from tools import get_incident_history


def derive_change_context(change: dict, similar_changes: list | None = None) -> dict:
    """
    Derive historical context needed by the risk model.

    The current change request supplies the change-specific fields.
    Historical features are calculated by the backend from trusted
    evidence sources.
    """

    # ---------------------------------------------------------
    # 1. Similar historical changes
    # ---------------------------------------------------------

    if similar_changes is None:
        from build_index import change_to_text

        query = change_to_text(
            {
                **change,
                "description": change.get("description", ""),
            }
        )

        similar_changes = find_similar_changes(query, k=5)

    similar_count = len(similar_changes)

    if similar_count > 0:
        failed_count = sum(
            1
            for item in similar_changes
            if item.get("outcome") in ["Failed", "Caused-Incident"]
        )
        similar_failure_rate = failed_count / similar_count
    else:
        similar_failure_rate = 0.0

    # ---------------------------------------------------------
    # 2. System incident history
    # ---------------------------------------------------------

    incidents = get_incident_history(change["system"])

    if incidents.get("found"):
        system_incidents = float(incidents["avg_incidents_last_90_days"])
    else:
        system_incidents = 0

    # ---------------------------------------------------------
    # 3. Return backend-derived model context
    # ---------------------------------------------------------

    return {
        "similar_past_changes_count": similar_count,
        "similar_past_changes_failure_rate": round(
            float(similar_failure_rate), 3
        ),
        "system_incidents_last_90_days": system_incidents,
    }
