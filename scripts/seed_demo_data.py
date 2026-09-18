"""Seed a realistic, diverse assessment history for demos.

Runs each scenario through the real controlled pipeline (ML + FAISS + tools
+ deterministic policy + LLM justification) - nothing here is fabricated,
it is genuine model/agent output. Only the resulting created_at timestamps
are backdated afterward so the history reads like real CAB activity spread
over time rather than a burst of requests from one session.

Useful to re-run after a Space/container restart on ephemeral storage
wipes the SQLite database.

Usage:
    python scripts/seed_demo_data.py
"""

import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from backend.database import init_db, save_assessment, DB_PATH
from agent import assess_change


SCENARIOS = [
    dict(system="Website-Frontend", change_type="Security-Patch", change_size="Small",
         requester_team="Security", requested_window="Off-Hours-Weekday",
         rollback_plan_exists="Yes", rollback_plan_tested="Yes", schedule_conflict="No",
         description="Patch a reflected XSS vulnerability in the marketing site's search form."),

    dict(system="Payments-Service", change_type="Database-Schema-Change", change_size="Large",
         requester_team="Backend", requested_window="Peak-Hours",
         rollback_plan_exists="No", rollback_plan_tested="None", schedule_conflict="Yes",
         description="Add a new nullable column to the transactions table for split payments."),

    dict(system="Auth-Service", change_type="Infrastructure-Change", change_size="Medium",
         requester_team="SRE", requested_window="Weekend",
         rollback_plan_exists="Yes", rollback_plan_tested="No", schedule_conflict="No",
         description="Migrate session store from Redis single-node to a Redis Cluster."),

    dict(system="Billing-DB", change_type="Database-Schema-Change", change_size="Medium",
         requester_team="Data-Engineering", requested_window="Business-Hours-Weekday",
         rollback_plan_exists="Yes", rollback_plan_tested="Yes", schedule_conflict="No",
         description="Add an index on invoice_date to speed up quarterly billing reports."),

    dict(system="Inventory-API", change_type="Deployment", change_size="Small",
         requester_team="DevOps", requested_window="Off-Hours-Weekday",
         rollback_plan_exists="Yes", rollback_plan_tested="Yes", schedule_conflict="No",
         description="Deploy v2.14.0 with a minor dependency bump and no schema changes."),

    dict(system="Notification-Service", change_type="Config-Update", change_size="Small",
         requester_team="Platform", requested_window="Business-Hours-Weekday",
         rollback_plan_exists="Yes", rollback_plan_tested="Yes", schedule_conflict="No",
         description="Raise the email queue batch size from 50 to 100."),

    dict(system="Reporting-DB", change_type="Database-Schema-Change", change_size="Large",
         requester_team="Data-Engineering", requested_window="Peak-Hours",
         rollback_plan_exists="No", rollback_plan_tested="None", schedule_conflict="Yes",
         description="Repartition the fact_sales table by month; no tested rollback path."),

    dict(system="Search-Service", change_type="Deployment", change_size="Medium",
         requester_team="Backend", requested_window="Off-Hours-Weekday",
         rollback_plan_exists="Yes", rollback_plan_tested="No", schedule_conflict="No",
         description="Roll out a new ranking model behind a feature flag."),

    dict(system="Payments-Service", change_type="Security-Patch", change_size="Small",
         requester_team="Security", requested_window="Weekend",
         rollback_plan_exists="Yes", rollback_plan_tested="Yes", schedule_conflict="No",
         description="Rotate the webhook signing secret ahead of scheduled expiry."),

    dict(system="Website-Frontend", change_type="Infrastructure-Change", change_size="Large",
         requester_team="SRE", requested_window="Peak-Hours",
         rollback_plan_exists="No", rollback_plan_tested="None", schedule_conflict="Yes",
         description="Switch CDN provider for static assets during a promotional traffic spike."),

    dict(system="Auth-Service", change_type="Security-Patch", change_size="Medium",
         requester_team="Security", requested_window="Off-Hours-Weekday",
         rollback_plan_exists="Yes", rollback_plan_tested="Yes", schedule_conflict="No",
         description="Patch a JWT library CVE affecting token signature verification."),

    dict(system="Billing-DB", change_type="Config-Update", change_size="Small",
         requester_team="Platform", requested_window="Business-Hours-Weekday",
         rollback_plan_exists="Yes", rollback_plan_tested="No", schedule_conflict="No",
         description="Increase connection pool size to handle month-end billing load."),

    dict(system="Inventory-API", change_type="Database-Schema-Change", change_size="Medium",
         requester_team="Backend", requested_window="Weekend",
         rollback_plan_exists="Yes", rollback_plan_tested="Yes", schedule_conflict="No",
         description="Add a composite index for warehouse_id and sku lookups."),

    dict(system="Notification-Service", change_type="Deployment", change_size="Large",
         requester_team="DevOps", requested_window="Peak-Hours",
         rollback_plan_exists="No", rollback_plan_tested="None", schedule_conflict="Yes",
         description="Cut over to the new push-notification provider mid-campaign."),

    dict(system="Reporting-DB", change_type="Patch", change_size="Small",
         requester_team="Data-Engineering", requested_window="Off-Hours-Weekday",
         rollback_plan_exists="Yes", rollback_plan_tested="Yes", schedule_conflict="No",
         description="Apply a minor Postgres point release for a security fix."),

    dict(system="Search-Service", change_type="Infrastructure-Change", change_size="Large",
         requester_team="SRE", requested_window="Business-Hours-Weekday",
         rollback_plan_exists="Yes", rollback_plan_tested="No", schedule_conflict="No",
         description="Resize the search cluster from 6 to 9 nodes ahead of holiday traffic."),

    dict(system="Payments-Service", change_type="Config-Update", change_size="Medium",
         requester_team="Backend", requested_window="Weekend",
         rollback_plan_exists="Yes", rollback_plan_tested="Yes", schedule_conflict="No",
         description="Adjust retry backoff configuration for the card-network integration."),

    dict(system="Website-Frontend", change_type="Patch", change_size="Small",
         requester_team="DevOps", requested_window="Off-Hours-Weekday",
         rollback_plan_exists="Yes", rollback_plan_tested="Yes", schedule_conflict="No",
         description="Bump the checkout page's payment SDK to the latest patch version."),

    dict(system="Auth-Service", change_type="Deployment", change_size="Medium",
         requester_team="SRE", requested_window="Peak-Hours",
         rollback_plan_exists="Yes", rollback_plan_tested="No", schedule_conflict="Yes",
         description="Deploy the new MFA enrollment flow during a live product launch window."),

    dict(system="Billing-DB", change_type="Security-Patch", change_size="Large",
         requester_team="Security", requested_window="Weekend",
         rollback_plan_exists="No", rollback_plan_tested="None", schedule_conflict="No",
         description="Emergency patch for a privilege-escalation CVE in the DB proxy layer."),
]


def main():
    init_db()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM assessments")
    conn.commit()
    conn.close()

    now = datetime.now()
    new_ids = []

    for i, change in enumerate(SCENARIOS):
        print(f"[{i + 1}/{len(SCENARIOS)}] {change['system']} / {change['change_type']}...")

        result = assess_change(change)
        policy = result["policy"]

        text = result["assessment"]
        jus = text.split("JUSTIFICATION:", 1)[-1].strip() if "JUSTIFICATION:" in text else text

        details = {
            "mode": "controlled",
            "user": {"username": "admin", "role": "admin"},
            "change": change,
            "ml_prediction": result["ml_prediction"],
            "similar_changes": result["similar_changes"],
            "historical_context": result.get("historical_context"),
            "evidence": result["evidence"],
            "policy": policy,
            "recommendation": policy["recommendation"],
            "risk_level": policy["risk_level"],
            "justification": jus,
        }

        new_id = save_assessment(
            change,
            result["ml_prediction"],
            policy["recommendation"],
            policy["risk_level"],
            jus,
            details=details,
        )
        new_ids.append(new_id)
        print(f"    -> {policy['recommendation']} / {policy['risk_level']}")

    # Backdate timestamps to look like activity spread over the last ~12 days,
    # oldest scenario first, a couple of business-hour-ish times per day.
    conn = sqlite3.connect(DB_PATH)
    base = now - timedelta(days=12)

    for i, assessment_id in enumerate(new_ids):
        day_offset = i // 2
        hour = 10 if i % 2 == 0 else 15
        ts = (base + timedelta(days=day_offset)).replace(
            hour=hour, minute=(i * 7) % 60, second=0, microsecond=0
        )
        conn.execute(
            "UPDATE assessments SET created_at = ? WHERE id = ?",
            (ts.strftime("%Y-%m-%d %H:%M"), assessment_id),
        )

    conn.commit()
    conn.close()

    print(f"\nSeeded {len(new_ids)} assessments.")


if __name__ == "__main__":
    main()
