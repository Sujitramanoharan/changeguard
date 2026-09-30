"""ChangeGuard storage: users, assessments and document verifications.

PostgreSQL when DATABASE_URL is set (production: data survives restarts
and redeploys), otherwise a local SQLite file (development and tests).
SQLAlchemy Core keeps one code path for both.
"""

import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

from pwdlib import PasswordHash
from sqlalchemy import (
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    func,
    inspect,
    insert,
    select,
    text,
    update,
)

sys.path.append(str(Path(__file__).parent.parent / "src"))

from config import MODEL_VERSION, POLICY_VERSION


# -------------------------------------------------------------------
# Connection
# -------------------------------------------------------------------

DEFAULT_DB_PATH = Path(__file__).parent.parent / "changeguard.db"

DB_PATH = Path(os.getenv("CHANGEGUARD_DB_PATH", str(DEFAULT_DB_PATH)))


def database_url() -> str:
    """DATABASE_URL (PostgreSQL) if set, else the SQLite file."""

    url = os.getenv("DATABASE_URL", "").strip()

    if url:
        # Hosts such as Render hand out postgres:// URLs; SQLAlchemy
        # needs the dialect and driver spelled out.
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DB_PATH}"


DATABASE_URL = database_url()
IS_POSTGRES = DATABASE_URL.startswith("postgresql")

engine = create_engine(
    DATABASE_URL,
    # Re-check pooled connections: hosted Postgres closes idle ones.
    pool_pre_ping=True,
    connect_args={} if IS_POSTGRES else {"check_same_thread": False},
)


def describe_database() -> str:
    """Human-readable target, without credentials."""

    return "PostgreSQL" if IS_POSTGRES else f"SQLite ({DB_PATH})"


# -------------------------------------------------------------------
# Schema
# -------------------------------------------------------------------

metadata = MetaData()

assessments = Table(
    "assessments",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("created_at", Text),
    Column("system", Text),
    Column("change_type", Text),
    Column("change_size", Text),
    Column("requester_team", Text),
    Column("requested_window", Text),
    Column("rollback_plan_exists", Text),
    Column("risk_probability", Float),
    Column("risk_level", Text),
    Column("recommendation", Text),
    Column("justification", Text),
    Column("details_json", Text),
    Column("rollback_plan_tested", Text),
    Column("schedule_conflict", Text),
    Column("mode", Text),
    Column("model_version", Text),
    Column("policy_version", Text),
    # Human CAB decision on top of the AI recommendation.
    Column("cab_decision", Text),
    Column("cab_comment", Text),
    Column("cab_decided_by", Text),
    Column("cab_decided_at", Text),
    # What actually happened after the change was implemented.
    Column("actual_outcome", Text),
    Column("outcome_recorded_by", Text),
    Column("outcome_recorded_at", Text),
    # "ticket" (ITIL change) or "code" (GitHub commit / PR).
    Column("assessment_type", Text),
)

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(100), unique=True, nullable=False),
    Column("password_hash", Text, nullable=False),
    Column("role", String(20), nullable=False),
    Column("created_at", Text, nullable=False),
)

# Server-side record of rollback document verifications. An assessment
# references one by ID, so a client can never assert the result itself.
document_verifications = Table(
    "document_verifications",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("username", String(100), nullable=False),
    Column("filename", Text, nullable=False),
    Column("verified", Integer, nullable=False),
    Column("result_json", Text, nullable=False),
    Column("created_at", Text, nullable=False),
)


password_hash = PasswordHash.recommended()


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def init_db():
    """Create tables, and add columns older databases are missing."""

    metadata.create_all(engine)

    # Databases created by earlier versions keep their data; any column
    # added since then is appended.
    existing = {c["name"] for c in inspect(engine).get_columns("assessments")}

    with engine.begin() as conn:
        for column in assessments.columns:
            if column.name not in existing:
                conn.execute(text(
                    f"ALTER TABLE assessments ADD COLUMN {column.name} "
                    f"{column.type.compile(engine.dialect)}"
                ))


def _row(mapping) -> dict | None:
    return dict(mapping) if mapping is not None else None


def _with_details(item: dict | None) -> dict | None:
    if item is None:
        return None

    try:
        item["details"] = json.loads(item["details_json"]) if item.get("details_json") else None
    except (TypeError, ValueError):
        item["details"] = None

    return item


# -------------------------------------------------------------------
# User management
# -------------------------------------------------------------------

def create_user(username: str, password: str, role: str = "reviewer"):
    """Create a new authenticated ChangeGuard user."""

    if role not in {"admin", "reviewer"}:
        raise ValueError("Invalid role. Role must be 'admin' or 'reviewer'.")

    with engine.begin() as conn:
        conn.execute(insert(users).values(
            username=username,
            password_hash=password_hash.hash(password),
            role=role,
            created_at=now(),
        ))


def get_user_by_username(username: str):
    """Return a user by username."""

    with engine.connect() as conn:
        return _row(conn.execute(
            select(users).where(users.c.username == username)
        ).mappings().first())


def set_password(username: str, password: str) -> bool:
    """Replace a user's password. Returns True if the user exists."""

    with engine.begin() as conn:
        result = conn.execute(
            update(users)
            .where(users.c.username == username)
            .values(password_hash=password_hash.hash(password))
        )
        return result.rowcount > 0


def list_users():
    """Return all users without password hashes."""

    with engine.connect() as conn:
        rows = conn.execute(
            select(users.c.id, users.c.username, users.c.role, users.c.created_at)
            .order_by(users.c.id)
        ).mappings().all()

    return [dict(r) for r in rows]


def delete_user(username: str) -> bool:
    """Delete a user by username. Returns True if a user was removed."""

    with engine.begin() as conn:
        return conn.execute(delete(users).where(users.c.username == username)).rowcount > 0


# -------------------------------------------------------------------
# Rollback document verifications
# -------------------------------------------------------------------

def save_document_verification(username: str, filename: str, result: dict) -> str:
    """Store a verification result and return its ID."""

    verification_id = uuid.uuid4().hex

    with engine.begin() as conn:
        conn.execute(insert(document_verifications).values(
            id=verification_id,
            username=username,
            filename=filename,
            verified=1 if result.get("verified") else 0,
            result_json=json.dumps(result),
            created_at=now(),
        ))

    return verification_id


def get_document_verification(verification_id: str):
    """Return a stored verification by ID, or None."""

    with engine.connect() as conn:
        item = _row(conn.execute(
            select(document_verifications)
            .where(document_verifications.c.id == verification_id)
        ).mappings().first())

    if not item:
        return None

    item["verified"] = bool(item["verified"])
    item["result"] = json.loads(item.pop("result_json"))

    return item


# -------------------------------------------------------------------
# Assessment storage
# -------------------------------------------------------------------

def save_assessment(change, ml, recommendation, risk_level, justification, details=None):
    """Insert an assessment and return its ID."""

    with engine.begin() as conn:
        result = conn.execute(insert(assessments).values(
            created_at=now(),
            system=change.get("system", "Unknown"),
            change_type=change.get("change_type", "Unknown"),
            change_size=change.get("change_size", "Medium"),
            requester_team=change.get("requester_team", "Engineering"),
            requested_window=change.get("requested_window", "Business-Hours-Weekday"),
            rollback_plan_exists=change.get("rollback_plan_exists", "Yes"),
            rollback_plan_tested=change.get("rollback_plan_tested", "None"),
            schedule_conflict=change.get("schedule_conflict", "No"),
            risk_probability=ml.get("risk_probability", 0.0) if ml else 0.0,
            risk_level=risk_level,
            recommendation=recommendation,
            justification=justification,
            details_json=json.dumps(details) if details else None,
            mode=details.get("mode", "controlled") if details else "controlled",
            model_version=MODEL_VERSION,
            policy_version=POLICY_VERSION,
            assessment_type=details.get("kind", "ticket") if details else "ticket",
        ).returning(assessments.c.id))

        return result.scalar_one()


def get_all_assessments():
    with engine.connect() as conn:
        rows = conn.execute(
            select(assessments).order_by(assessments.c.id.desc())
        ).mappings().all()

    return [_with_details(dict(r)) for r in rows]


def get_assessment_by_id(assessment_id: int):
    with engine.connect() as conn:
        item = _row(conn.execute(
            select(assessments).where(assessments.c.id == assessment_id)
        ).mappings().first())

    return _with_details(item)


def count_assessments() -> int:
    """Return the number of stored assessments."""

    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(assessments)).scalar_one()


def clear_assessments() -> None:
    """Delete every assessment (used by demo seeding)."""

    with engine.begin() as conn:
        conn.execute(delete(assessments))


def set_created_at(assessment_id: int, created_at: str) -> None:
    """Backdate an assessment (used by demo seeding)."""

    with engine.begin() as conn:
        conn.execute(
            update(assessments)
            .where(assessments.c.id == assessment_id)
            .values(created_at=created_at)
        )


# -------------------------------------------------------------------
# Human CAB decision and actual outcome
# -------------------------------------------------------------------

def record_cab_decision(assessment_id: int, decision: str, comment: str, decided_by: str) -> bool:
    """Record the human CAB decision for an assessment."""

    with engine.begin() as conn:
        return conn.execute(
            update(assessments)
            .where(assessments.c.id == assessment_id)
            .values(
                cab_decision=decision,
                cab_comment=comment,
                cab_decided_by=decided_by,
                cab_decided_at=now(),
            )
        ).rowcount > 0


def record_actual_outcome(assessment_id: int, outcome: str, recorded_by: str) -> bool:
    """Record what actually happened after the change was implemented."""

    with engine.begin() as conn:
        return conn.execute(
            update(assessments)
            .where(assessments.c.id == assessment_id)
            .values(
                actual_outcome=outcome,
                outcome_recorded_by=recorded_by,
                outcome_recorded_at=now(),
            )
        ).rowcount > 0


# -------------------------------------------------------------------
# Statistics
# -------------------------------------------------------------------

def get_stats():
    with engine.connect() as conn:
        rows = conn.execute(select(
            assessments.c.risk_level,
            assessments.c.recommendation,
            assessments.c.cab_decision,
            assessments.c.actual_outcome,
        )).mappings().all()

    def count(key, value):
        return sum(1 for r in rows if r[key] == value)

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
    bad_outcomes = [r for r in with_outcome if r["actual_outcome"] in ("Failed", "Caused-Incident")]

    return {
        "total": len(rows),
        "pending_decision": len(rows) - len(decided),
        "cab_decided": len(decided),
        "cab_overrides": overrides,
        "outcomes_recorded": len(with_outcome),
        "bad_outcomes": len(bad_outcomes),
        "bad_outcomes_flagged": sum(1 for r in bad_outcomes if r["recommendation"] != "APPROVE"),
        "high_risk": count("risk_level", "High"),
        "medium_risk": count("risk_level", "Medium"),
        "low_risk": count("risk_level", "Low"),
        "rejected": count("recommendation", "REJECT"),
        "approved": count("recommendation", "APPROVE"),
        "review": count("recommendation", "REVIEW"),
    }
