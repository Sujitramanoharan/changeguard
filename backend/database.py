"""SQLite database for storing ChangeGuard assessments."""
import sqlite3
import json
from pathlib import Path
from datetime import datetime
import sys
sys.path.append(str(Path(__file__).parent.parent / "src"))

from config import MODEL_VERSION, POLICY_VERSION

DB_PATH = Path(__file__).parent.parent / "changeguard.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            system TEXT,
            change_type TEXT,
            change_size TEXT,
            requester_team TEXT,
            requested_window TEXT,
            rollback_plan_exists TEXT,
            risk_probability REAL,
            risk_level TEXT,
            recommendation TEXT,
            justification TEXT,
            details_json TEXT
        )
    """)
    # Backward-compatible database migrations.
    # Existing assessment records are preserved.
    migrations = [
        ("rollback_plan_tested", "TEXT"),
        ("schedule_conflict", "TEXT"),
        ("mode", "TEXT"),
        ("model_version", "TEXT"),
        ("policy_version", "TEXT"),
    ]

    for column_name, column_type in migrations:
        try:
            conn.execute(
                f"ALTER TABLE assessments "
                f"ADD COLUMN {column_name} {column_type}"
            )
        except sqlite3.OperationalError:
            pass

def save_assessment(
    change,
    ml,
    recommendation,
    risk_level,
    justification,
    details=None,
):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    details_str = json.dumps(details) if details else None

    cur.execute(
        """
        INSERT INTO assessments
        (
            created_at,
            system,
            change_type,
            change_size,
            requester_team,
            requested_window,
            rollback_plan_exists,
            rollback_plan_tested,
            schedule_conflict,
            risk_probability,
            risk_level,
            recommendation,
            justification,
            details_json,
            mode,
            model_version,
            policy_version
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            change.get("system", "Unknown"),
            change.get("change_type", "Unknown"),
            change.get("change_size", "Medium"),
            change.get("requester_team", "Engineering"),
            change.get("requested_window", "Business-Hours-Weekday"),
            change.get("rollback_plan_exists", "Yes"),
            change.get("rollback_plan_tested", "None"),
            change.get("schedule_conflict", "No"),
            ml.get("risk_probability", 0.0) if ml else 0.0,
            risk_level,
            recommendation,
            justification,
            details_str,
            details.get("mode", "controlled") if details else "controlled",
            MODEL_VERSION,
            POLICY_VERSION,
        ),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()

    return new_id


def get_all_assessments():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM assessments ORDER BY id DESC"
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        item = dict(r)
        if item.get("details_json"):
            try:
                item["details"] = json.loads(item["details_json"])
            except Exception:
                item["details"] = None
        else:
            item["details"] = None
        result.append(item)
    return result


def get_assessment_by_id(assessment_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM assessments WHERE id = ?", (assessment_id,)).fetchone()
    conn.close()
    if not row:
        return None
    item = dict(row)
    if item.get("details_json"):
        try:
            item["details"] = json.loads(item["details_json"])
        except Exception:
            item["details"] = None
    return item


def get_stats():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT risk_level, recommendation, created_at FROM assessments").fetchall()
    conn.close()
    total = len(rows)
    high = sum(1 for r in rows if r["risk_level"] == "High")
    medium = sum(1 for r in rows if r["risk_level"] == "Medium")
    low = sum(1 for r in rows if r["risk_level"] == "Low")
    rejected = sum(1 for r in rows if r["recommendation"] == "REJECT")
    approved = sum(1 for r in rows if r["recommendation"] == "APPROVE")
    review = sum(1 for r in rows if r["recommendation"] == "REVIEW")
    
    return {
        "total": total,
        "high_risk": high,
        "medium_risk": medium,
        "low_risk": low,
        "rejected": rejected,
        "approved": approved,
        "review": review,
    }