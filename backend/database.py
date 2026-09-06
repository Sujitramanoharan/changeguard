"""SQLite database for storing ChangeGuard assessments."""
import sqlite3
from pathlib import Path
from datetime import datetime

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
            justification TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_assessment(change, ml, recommendation, risk_level, justification):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO assessments
        (created_at, system, change_type, change_size, requester_team,
         requested_window, rollback_plan_exists, risk_probability,
         risk_level, recommendation, justification)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        change["system"], change["change_type"], change["change_size"],
        change["requester_team"], change["requested_window"],
        change["rollback_plan_exists"], ml["risk_probability"],
        risk_level, recommendation, justification,
    ))
    conn.commit()
    conn.close()


def get_all_assessments():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM assessments ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT risk_level, recommendation FROM assessments").fetchall()
    conn.close()
    total = len(rows)
    high = sum(1 for r in rows if r["risk_level"] == "High")
    rejected = sum(1 for r in rows if r["recommendation"] == "REJECT")
    return {"total": total, "high_risk": high, "rejected": rejected}