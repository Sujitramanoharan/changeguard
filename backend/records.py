"""Save assessments to the audit trail (shared by the API and demo seeding)."""

import logging
import re
from datetime import datetime

from ticket_risk import WEEKDAYS

from backend.database import save_assessment


logger = logging.getLogger("changeguard")


def parse_assessment(text: str):
    """Extract generated recommendation, risk level and justification."""

    rec = re.search(r"RECOMMENDATION:\s*(\w+)", text)
    lvl = re.search(r"RISK LEVEL:\s*(\w+)", text)
    jus = re.search(r"JUSTIFICATION:\s*(.+)", text, re.S)

    return (
        rec.group(1) if rec else "REVIEW",
        lvl.group(1) if lvl else "Medium",
        jus.group(1).strip() if jus else text,
    )


def summary_columns(kind: str, change: dict, result: dict) -> dict:
    """The short columns shown in history tables and CSV exports."""

    if kind == "ticket":
        when = datetime.fromisoformat(str(change["planned_start"]))
        summary = {
            "system": change["title"],
            "change_type": change["change_family"],
            "change_size": change["risk_classification"],
            "requester_team": change["ci_subtype"],
            "requested_window": f"{WEEKDAYS[when.weekday()][:3]} {when:%H:%M}",
        }
    else:
        metrics = result["code_metrics"]
        summary = {
            "system": change["system"],
            "change_type": "Code change",
            "change_size": f"+{metrics['la']}/-{metrics['ld']} lines, {metrics['nf']} files",
            "requester_team": result.get("analysis", {}).get("author", ""),
            "requested_window": "",
        }

    summary.update(
        rollback_plan_exists=change.get("rollback_plan_exists"),
        rollback_plan_tested=change.get("rollback_plan_tested"),
        schedule_conflict=change.get("schedule_conflict", "No"),
    )

    return summary


def record_assessment(
    kind: str,
    mode: str,
    change: dict,
    result: dict,
    answer_text: str,
    user: dict,
    extra: dict | None = None,
) -> dict:
    """Save an assessment and return the API response for it."""

    policy = result["policy"]
    rec = policy["recommendation"]
    lvl = policy["risk_level"]
    _, _, jus = parse_assessment(answer_text)

    response = {
        "kind": kind,
        "mode": mode,
        "ml_prediction": result["ml_prediction"],
        "similar_changes": result["similar_changes"],
        "evidence": result["evidence"],
        "policy": policy,
        "explanation_source": result["explanation_source"],
        "prompt_guard": result.get("prompt_guard"),
        "recommendation": rec,
        "risk_level": lvl,
        "justification": jus,
        **(extra or {}),
    }

    details = {
        **response,
        "user": {"username": user["username"], "role": user["role"]},
        "change": change,
    }

    new_id = save_assessment(
        summary_columns(kind, change, result),
        result["ml_prediction"],
        rec,
        lvl,
        jus,
        details=details,
    )

    logger.info(
        "Assessment saved | id=%s | kind=%s | mode=%s | user=%s | recommendation=%s | risk=%s",
        new_id, kind, mode, user["username"], rec, lvl,
    )

    return {"id": new_id, **response}
