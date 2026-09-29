"""Shared demo-data scenarios and seeding logic.

Used by both scripts/seed_demo_data.py (CLI) and the admin-only
POST /api/admin/seed-demo-data endpoint (for hosts with no shell
access, e.g. free-tier PaaS with ephemeral storage).

Every scenario runs through the real pipeline and real models:
  * change tickets use realistic ITIL values for the real Rabobank
    system types the ticket model was trained on;
  * code changes are real public GitHub commits, analysed once and
    stored in data/demo_code_changes.json so seeding needs no network.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from agent import assess_code, assess_ticket

from backend.database import (
    DB_PATH,
    get_assessment_by_id,
    init_db,
    record_actual_outcome,
    record_cab_decision,
)
from backend.records import record_assessment


CODE_CHANGES_PATH = Path(__file__).parent.parent / "data" / "demo_code_changes.json"

DEMO_USER = {"username": "admin", "role": "admin"}


def ticket(title, ci_type, ci_subtype, family, risk, incidents, day, hour, hours,
           systems=1, origin="Problem", downtime=False, emergency=False, cab=False,
           rollback="Yes", tested="Yes", conflict="No", description=""):
    return dict(
        title=title, ci_type=ci_type, ci_subtype=ci_subtype, change_family=family,
        risk_classification=risk, origin=origin, incidents_30d=incidents,
        _day=day, _hour=hour, planned_hours=hours, systems_affected=systems,
        downtime=downtime, emergency=emergency, cab_required=cab,
        rollback_plan_exists=rollback, rollback_plan_tested=tested,
        schedule_conflict=conflict, description=description,
    )


TICKETS = [
    ticket("Patch Windows servers - monthly security update", "computer", "Windows Server",
           "Standard Change Type", "Minor Change", 0, 1, 10, 2, systems=4,
           description="Monthly OS security patches on the internal file-server cluster."),
    ticket("Online banking web release 24.3", "application", "Web Based Application",
           "Release Type", "Major Business Change", 18, 5, 20, 6, systems=6, origin="Incident",
           downtime=True, cab=True, tested="No",
           description="Quarterly release of the customer online-banking portal."),
    ticket("Firewall rule change for partner VPN", "networkcomponents", "Firewall",
           "Standard Activity Type", "Minor Change", 1, 2, 14, 1,
           description="Open port 443 for the new payments partner VPN endpoint."),
    ticket("Core DB instance parameter tuning", "database", "Instance",
           "Standard Change Type", "Business Change", 3, 3, 22, 3, downtime=True, tested="No",
           description="Increase buffer cache on the core accounts database instance."),
    ticket("Emergency fix - card authorisation service", "application", "Server Based Application",
           "Standard Change Type", "Business Change", 26, 6, 1, 2, origin="Incident",
           emergency=True, cab=True, rollback="No", tested="None",
           description="Hotfix for card authorisation timeouts reported by customers."),
    ticket("Linux kernel update - batch servers", "computer", "Linux Server",
           "Standard Change Type", "Minor Change", 0, 0, 9, 3, systems=8,
           description="Kernel update on the nightly batch-processing servers."),
    ticket("SharePoint farm cumulative update", "application", "SharePoint Farm",
           "Standard Activity Type", "Minor Change", 4, 4, 18, 4, downtime=True,
           description="Apply the vendor cumulative update to the intranet SharePoint farm."),
    ticket("Core switch firmware upgrade", "networkcomponents", "Switch",
           "Standard Change Type", "Business Change", 2, 5, 23, 4, downtime=True, cab=True,
           conflict="Yes", tested="No",
           description="Firmware upgrade on data-centre core switches; overlaps a DR test."),
    ticket("Desktop app rollout - new expense tool", "application", "Desktop Application",
           "Release Type", "Minor Change", 1, 2, 11, 2, systems=2,
           description="Roll out version 2.1 of the expense-claims desktop client."),
    ticket("SAN storage expansion", "storage", "SAN",
           "Standard Activity Type", "Minor Change", 0, 1, 13, 3,
           description="Add two disk shelves to the primary SAN."),
    ticket("Mortgage portal release 7.0", "subapplication", "Web Based Application",
           "Release Type", "Business Change", 9, 4, 17, 5, systems=3, cab=True, tested="No",
           description="New mortgage application flow on the customer portal."),
    ticket("MQ queue manager config change", "applicationcomponent", "MQ Queue Manager",
           "Standard Change Type", "Minor Change", 0, 3, 10, 1,
           description="Raise max queue depth for the payments message queue."),
    ticket("Citrix farm image refresh", "application", "Citrix",
           "Standard Activity Type", "Business Change", 7, 6, 21, 6, systems=5, downtime=True,
           description="Refresh the Citrix golden image for branch-office desktops."),
    ticket("Oracle RAC service relocation", "database", "RAC Service",
           "Standard Change Type", "Minor Change", 0, 2, 15, 1,
           description="Relocate reporting service to the second RAC node."),
]


def load_code_changes() -> list:
    return json.loads(CODE_CHANGES_PATH.read_text(encoding="utf-8"))


def seed_demo_assessments():
    """Clear existing assessments and seed realistic ones via the real
    pipeline. Returns the number of assessments created."""

    init_db()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM assessments")
    conn.commit()
    conn.close()

    now = datetime.now()
    new_ids = []

    # Interleave: two tickets, then one code change.
    tickets = [("ticket", t) for t in TICKETS]
    code = [("code", c) for c in load_code_changes()]
    runs = []
    while tickets or code:
        runs += tickets[:2] + code[:1]
        tickets, code = tickets[2:], code[1:]

    # Monday two weeks ago; each ticket's weekday/hour is placed in that week.
    monday = (now - timedelta(days=now.weekday() + 14)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    for i, (kind, item) in enumerate(runs):
        if kind == "ticket":
            planned = monday + timedelta(days=item["_day"], hours=item["_hour"])

            change = {k: v for k, v in item.items() if not k.startswith("_")}
            change["planned_start"] = planned.isoformat(timespec="minutes")
            change["rollback_document_provided"] = False
            change["rollback_document_verified"] = False

            result = assess_ticket(change)
            saved = record_assessment("ticket", "controlled", change, result,
                                      result["assessment"], DEMO_USER)
        else:
            result = assess_code(item)
            change = {**result["change"], "url": item["url"]}
            saved = record_assessment(
                "code", "controlled", change, result, result["assessment"], DEMO_USER,
                extra={"code_metrics": result["code_metrics"], "analysis": result["analysis"]},
            )

        new_ids.append(saved["id"])

    # Backdate timestamps to look like activity over the last ~12 days.
    conn = sqlite3.connect(DB_PATH)
    base = now - timedelta(days=12)

    for i, assessment_id in enumerate(new_ids):
        ts = (base + timedelta(days=i // 2)).replace(
            hour=10 if i % 2 == 0 else 15, minute=(i * 7) % 60, second=0, microsecond=0
        )
        conn.execute(
            "UPDATE assessments SET created_at = ? WHERE id = ?",
            (ts.strftime("%Y-%m-%d %H:%M"), assessment_id),
        )

    conn.commit()
    conn.close()

    # Give the older half a (clearly labelled) demo CAB decision - and,
    # for approved changes, a recorded outcome - so the feedback-loop
    # metrics have data. The newest stay pending for a live demo.
    for i, assessment_id in enumerate(new_ids[: len(new_ids) // 2]):
        rec = get_assessment_by_id(assessment_id)["recommendation"]
        decision = "REJECT" if rec == "REJECT" else "APPROVE"

        record_cab_decision(
            assessment_id,
            decision,
            "Demo seed: CAB accepted the ChangeGuard recommendation."
            if rec != "REVIEW"
            else "Demo seed: reviewed evidence with the requester; approved.",
            "demo-cab",
        )

        if decision == "APPROVE":
            outcome = "Failed" if rec == "REVIEW" and i % 2 == 0 else "Success"
            record_actual_outcome(assessment_id, outcome, "demo-cab")

    return len(new_ids)
