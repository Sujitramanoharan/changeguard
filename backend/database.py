"""SQLite database for storing ChangeGuard assessments."""

import sqlite3
import json
import uuid
from pathlib import Path
from datetime import datetime
from pwdlib import PasswordHash
import sys
import os

sys.path.append(str(Path(__file__).parent.parent / "src"))

from config import MODEL_VERSION, POLICY_VERSION


DEFAULT_DB_PATH = Path(__file__).parent.parent / "changeguard.db"

DB_PATH = Path(
    os.getenv(
        "CHANGEGUARD_DB_PATH",
        str(DEFAULT_DB_PATH),
    )
)

DB_PATH.parent.mkdir(
    parents=True,
    exist_ok=True,
)


# -------------------------------------------------------------------
# Password hashing
# -------------------------------------------------------------------

password_hash = PasswordHash.recommended()


# -------------------------------------------------------------------
# Database initialization
# -------------------------------------------------------------------

def init_db():
    """Create database tables and apply backward-compatible migrations."""

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
        # Human CAB decision on top of the AI recommendation.
        ("cab_decision", "TEXT"),
        ("cab_comment", "TEXT"),
        ("cab_decided_by", "TEXT"),
        ("cab_decided_at", "TEXT"),
        # What actually happened after the change was implemented.
        ("actual_outcome", "TEXT"),
        ("outcome_recorded_by", "TEXT"),
        ("outcome_recorded_at", "TEXT"),
        # "ticket" (ITIL change) or "code" (GitHub commit / PR).
        ("assessment_type", "TEXT"),
    ]

    for column_name, column_type in migrations:
        try:
            conn.execute(
                f"ALTER TABLE assessments "
                f"ADD COLUMN {column_name} {column_type}"
            )
        except sqlite3.OperationalError:
            pass

    # Authentication users table.
    # This does not modify or delete existing assessments.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # Server-side record of rollback document verifications.
    # An assessment references one of these by ID, so the verification
    # result can never be asserted by the client on its own.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS document_verifications (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            filename TEXT NOT NULL,
            verified INTEGER NOT NULL,
            result_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# -------------------------------------------------------------------
# User management
# -------------------------------------------------------------------

def create_user(
    username: str,
    password: str,
    role: str = "reviewer",
):
    """Create a new authenticated ChangeGuard user."""

    if role not in {"admin", "reviewer"}:
        raise ValueError(
            "Invalid role. Role must be 'admin' or 'reviewer'."
        )

    conn = sqlite3.connect(DB_PATH)

    try:
        conn.execute(
            """
            INSERT INTO users
            (
                username,
                password_hash,
                role,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                username,
                password_hash.hash(password),
                role,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
            ),
        )

        conn.commit()

    finally:
        conn.close()


def get_user_by_username(username: str):
    """Return a user by username."""

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        row = conn.execute(
            """
            SELECT
                id,
                username,
                password_hash,
                role,
                created_at
            FROM users
            WHERE username = ?
            """,
            (username,),
        ).fetchone()

        return dict(row) if row else None

    finally:
        conn.close()


def list_users():
    """Return all users without password hashes."""

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        rows = conn.execute(
            "SELECT id, username, role, created_at FROM users ORDER BY id"
        ).fetchall()

        return [dict(r) for r in rows]

    finally:
        conn.close()


def delete_user(username: str) -> bool:
    """Delete a user by username. Returns True if a user was removed."""

    conn = sqlite3.connect(DB_PATH)

    try:
        cur = conn.execute(
            "DELETE FROM users WHERE username = ?",
            (username,),
        )
        conn.commit()

        return cur.rowcount > 0

    finally:
        conn.close()


# -------------------------------------------------------------------
# Rollback document verifications
# -------------------------------------------------------------------

def save_document_verification(
    username: str,
    filename: str,
    result: dict,
) -> str:
    """Store a verification result and return its ID."""

    verification_id = uuid.uuid4().hex

    conn = sqlite3.connect(DB_PATH)

    try:
        conn.execute(
            """
            INSERT INTO document_verifications
            (id, username, filename, verified, result_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                verification_id,
                username,
                filename,
                1 if result.get("verified") else 0,
                json.dumps(result),
                datetime.now().strftime("%Y-%m-%d %H:%M"),
            ),
        )
        conn.commit()

    finally:
        conn.close()

    return verification_id


def get_document_verification(verification_id: str):
    """Return a stored verification by ID, or None."""

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        row = conn.execute(
            "SELECT * FROM document_verifications WHERE id = ?",
            (verification_id,),
        ).fetchone()

    finally:
        conn.close()

    if not row:
        return None

    item = dict(row)
    item["verified"] = bool(item["verified"])
    item["result"] = json.loads(item.pop("result_json"))

    return item


# -------------------------------------------------------------------
# Assessment storage
# -------------------------------------------------------------------

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
            policy_version,
            assessment_type
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            change.get("system", "Unknown"),
            change.get("change_type", "Unknown"),
            change.get("change_size", "Medium"),
            change.get("requester_team", "Engineering"),
            change.get(
                "requested_window",
                "Business-Hours-Weekday",
            ),
            change.get("rollback_plan_exists", "Yes"),
            change.get("rollback_plan_tested", "None"),
            change.get("schedule_conflict", "No"),
            ml.get("risk_probability", 0.0) if ml else 0.0,
            risk_level,
            recommendation,
            justification,
            details_str,
            details.get("mode", "controlled")
            if details
            else "controlled",
            MODEL_VERSION,
            POLICY_VERSION,
            details.get("kind", "ticket") if details else "ticket",
        ),
    )

    new_id = cur.lastrowid

    conn.commit()
    conn.close()

    return new_id


# -------------------------------------------------------------------
# Assessment retrieval
# -------------------------------------------------------------------

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
                item["details"] = json.loads(
                    item["details_json"]
                )
            except Exception:
                item["details"] = None
        else:
            item["details"] = None

        result.append(item)

    return result


def get_assessment_by_id(assessment_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    row = conn.execute(
        "SELECT * FROM assessments WHERE id = ?",
        (assessment_id,),
    ).fetchone()

    conn.close()

    if not row:
        return None

    item = dict(row)

    if item.get("details_json"):
        try:
            item["details"] = json.loads(
                item["details_json"]
            )
        except Exception:
            item["details"] = None

    return item


# -------------------------------------------------------------------
# Human CAB decision and actual outcome
# -------------------------------------------------------------------

def record_cab_decision(
    assessment_id: int,
    decision: str,
    comment: str,
    decided_by: str,
) -> bool:
    """Record the human CAB decision for an assessment."""

    conn = sqlite3.connect(DB_PATH)

    try:
        cur = conn.execute(
            """
            UPDATE assessments
            SET cab_decision = ?, cab_comment = ?,
                cab_decided_by = ?, cab_decided_at = ?
            WHERE id = ?
            """,
            (
                decision,
                comment,
                decided_by,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                assessment_id,
            ),
        )
        conn.commit()

        return cur.rowcount > 0

    finally:
        conn.close()


def record_actual_outcome(
    assessment_id: int,
    outcome: str,
    recorded_by: str,
) -> bool:
    """Record what actually happened after the change was implemented."""

    conn = sqlite3.connect(DB_PATH)

    try:
        cur = conn.execute(
            """
            UPDATE assessments
            SET actual_outcome = ?, outcome_recorded_by = ?,
                outcome_recorded_at = ?
            WHERE id = ?
            """,
            (
                outcome,
                recorded_by,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                assessment_id,
            ),
        )
        conn.commit()

        return cur.rowcount > 0

    finally:
        conn.close()


def count_assessments() -> int:
    """Return the number of stored assessments."""

    conn = sqlite3.connect(DB_PATH)

    try:
        return conn.execute(
            "SELECT COUNT(*) FROM assessments"
        ).fetchone()[0]

    finally:
        conn.close()


# -------------------------------------------------------------------
# Statistics
# -------------------------------------------------------------------

def get_stats():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT
            risk_level,
            recommendation,
            created_at,
            cab_decision,
            actual_outcome
        FROM assessments
        """
    ).fetchall()

    conn.close()

    total = len(rows)

    high = sum(
        1
        for r in rows
        if r["risk_level"] == "High"
    )

    medium = sum(
        1
        for r in rows
        if r["risk_level"] == "Medium"
    )

    low = sum(
        1
        for r in rows
        if r["risk_level"] == "Low"
    )

    rejected = sum(
        1
        for r in rows
        if r["recommendation"] == "REJECT"
    )

    approved = sum(
        1
        for r in rows
        if r["recommendation"] == "APPROVE"
    )

    review = sum(
        1
        for r in rows
        if r["recommendation"] == "REVIEW"
    )

    decided = [r for r in rows if r["cab_decision"]]

    # A human override is a CAB decision that disagrees with a firm
    # AI recommendation (REVIEW leaves the call to the board).
    overrides = sum(
        1
        for r in decided
        if r["recommendation"] in ("APPROVE", "REJECT")
        and r["cab_decision"] != r["recommendation"]
    )

    with_outcome = [r for r in rows if r["actual_outcome"]]

    # Of the changes that went badly, how many had the AI flagged
    # (REVIEW or REJECT) beforehand?
    bad_outcomes = [
        r
        for r in with_outcome
        if r["actual_outcome"] in ("Failed", "Caused-Incident")
    ]
    bad_flagged = sum(
        1 for r in bad_outcomes if r["recommendation"] != "APPROVE"
    )

    return {
        "total": total,
        "pending_decision": total - len(decided),
        "cab_decided": len(decided),
        "cab_overrides": overrides,
        "outcomes_recorded": len(with_outcome),
        "bad_outcomes": len(bad_outcomes),
        "bad_outcomes_flagged": bad_flagged,
        "high_risk": high,
        "medium_risk": medium,
        "low_risk": low,
        "rejected": rejected,
        "approved": approved,
        "review": review,
    }