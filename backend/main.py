"""ChangeGuard FastAPI backend."""

import logging
import re
import sys
from pathlib import Path
from typing import Literal

# Let this file import from src/
sys.path.append(str(Path(__file__).parent.parent / "src"))

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent_graph import assess_change_autonomous
from agent import assess_change
from config import CORS_ORIGINS, APP_VERSION

from backend.database import (
    init_db,
    save_assessment,
    get_all_assessments,
    get_stats,
    get_assessment_by_id,
)


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("changeguard")


# =========================================================
# APPLICATION
# =========================================================

app = FastAPI(
    title="ChangeGuard - AI Enterprise Change Risk Assessment"
)


# =========================================================
# ERROR HANDLING
# =========================================================

@app.exception_handler(Exception)
async def global_exception_handler(
    request: Request,
    exc: Exception,
):
    """Return a safe response for unexpected server errors."""

    logger.exception(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
    )

    return {
        "error": "Internal server error",
        "message": "An unexpected error occurred while processing the request.",
    }


# =========================================================
# CORS
# =========================================================

# Allowed frontend origins are configured through CORS_ORIGINS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

init_db()


# =========================================================
# FRONTEND PATHS
# =========================================================

DIST_DIR = Path(__file__).parent.parent / "frontend_dist"
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


# =========================================================
# REQUEST MODEL
# =========================================================

class ChangeRequest(BaseModel):
    """Validated change request received from the frontend."""

    system: str = Field(
        min_length=1,
        max_length=100,
    )

    change_type: Literal[
        "Config-Update",
        "Database-Schema-Change",
        "Deployment",
        "Infrastructure-Change",
        "Patch",
        "Security-Patch",
    ]

    change_size: Literal[
        "Small",
        "Medium",
        "Large",
    ]

    requester_team: str = Field(
        min_length=1,
        max_length=100,
    )

    requested_window: Literal[
        "Business-Hours-Weekday",
        "Off-Hours-Weekday",
        "Peak-Hours",
        "Weekend",
    ]

    rollback_plan_exists: Literal[
        "Yes",
        "No",
    ]

    rollback_plan_tested: Literal[
        "Yes",
        "No",
        "None",
    ] = "None"

    schedule_conflict: Literal[
        "Yes",
        "No",
    ]

    description: str = Field(
        default="",
        max_length=2000,
    )


# =========================================================
# ASSESSMENT PARSER
# =========================================================

def parse_assessment(text: str):
    """
    Extract recommendation, risk level, and justification
    from an assessment text.

    The recommendation and risk level are NOT authoritative.
    The deterministic risk policy is authoritative.
    This parser is retained primarily for extracting the
    generated justification.
    """

    rec = re.search(
        r"RECOMMENDATION:\s*(\w+)",
        text,
    )

    lvl = re.search(
        r"RISK LEVEL:\s*(\w+)",
        text,
    )

    jus = re.search(
        r"JUSTIFICATION:\s*(.+)",
        text,
        re.S,
    )

    return (
        rec.group(1) if rec else "REVIEW",
        lvl.group(1) if lvl else "Medium",
        jus.group(1).strip() if jus else text,
    )


# =========================================================
# CONTROLLED ASSESSMENT
# =========================================================

@app.post("/api/assess")
def assess(req: ChangeRequest):
    """
    Run the controlled ChangeGuard assessment pipeline.

    The deterministic risk policy is the authoritative source
    for recommendation and risk level.
    """

    change = req.model_dump()

    logger.info(
        "Starting controlled assessment | system=%s | change_type=%s",
        change["system"],
        change["change_type"],
    )

    result = assess_change(change)

    # The deterministic policy is authoritative.
    policy = result["policy"]

    rec = policy["recommendation"]
    lvl = policy["risk_level"]

    logger.info(
        "Controlled assessment decision | recommendation=%s | risk_level=%s",
        rec,
        lvl,
    )

    # Extract only the generated justification text.
    _, _, jus = parse_assessment(
        result["assessment"]
    )

    # Store complete evidence and assessment details.
    details = {
        "mode": "controlled",
        "change": change,
        "ml_prediction": result["ml_prediction"],
        "similar_changes": result["similar_changes"],
        "historical_context": result.get(
            "historical_context"
        ),
        "evidence": result["evidence"],
        "policy": policy,
        "recommendation": rec,
        "risk_level": lvl,
        "justification": jus,
    }

    # Save assessment to database.
    new_id = save_assessment(
        change,
        result["ml_prediction"],
        rec,
        lvl,
        jus,
        details=details,
    )

    logger.info(
        "Controlled assessment saved | assessment_id=%s",
        new_id,
    )

    # Return result to frontend.
    return {
        "id": new_id,
        "ml_prediction": result["ml_prediction"],
        "similar_changes": result["similar_changes"],
        "evidence": result["evidence"],
        "recommendation": rec,
        "risk_level": lvl,
        "justification": jus,
    }


# =========================================================
# AUTONOMOUS ASSESSMENT
# =========================================================

@app.post("/api/assess-autonomous")
def assess_autonomous(req: ChangeRequest):
    """
    Run the autonomous LangGraph ChangeGuard assessment.

    The deterministic risk policy remains authoritative even
    when the autonomous agent chooses which evidence tools to use.
    """

    # Convert validated request into a dictionary.
    change = req.model_dump()

    logger.info(
        "Starting autonomous assessment | system=%s | change_type=%s",
        change["system"],
        change["change_type"],
    )

    # Run autonomous LangGraph agent.
    result = assess_change_autonomous(change)

    # The autonomous pipeline already calculates the
    # authoritative deterministic policy.
    policy = result["policy"]

    rec = policy["recommendation"]
    lvl = policy["risk_level"]

    logger.info(
        "Autonomous assessment decision | recommendation=%s | risk_level=%s | tool_calls=%s",
        rec,
        lvl,
        result["num_tool_calls"],
    )

    # Extract only the generated justification.
    _, _, jus = parse_assessment(
        result["final_answer"]
    )

    # Use the ML prediction already produced by the
    # autonomous pipeline instead of running the model twice.
    ml_prediction = result["ml_prediction"]

    # Store complete autonomous assessment details.
    details = {
        "mode": "autonomous",
        "change": change,
        "ml_prediction": ml_prediction,
        "historical_context": result.get(
            "historical_context"
        ),
        "similar_changes": result.get(
            "similar_changes"
        ),
        "schedule": result.get(
            "schedule"
        ),
        "policy": policy,
        "recommendation": rec,
        "risk_level": lvl,
        "justification": jus,
        "tools_called": result["tools_called"],
        "num_tool_calls": result["num_tool_calls"],
    }

    # Save assessment to database.
    new_id = save_assessment(
        change,
        ml_prediction,
        rec,
        lvl,
        jus,
        details=details,
    )

    logger.info(
        "Autonomous assessment saved | assessment_id=%s",
        new_id,
    )

    # Return result to frontend.
    return {
        "id": new_id,
        "ml_prediction": ml_prediction,
        "recommendation": rec,
        "risk_level": lvl,
        "justification": jus,
        "tools_called": result["tools_called"],
        "num_tool_calls": result["num_tool_calls"],
    }


# =========================================================
# HISTORY
# =========================================================

@app.get("/api/history")
def history():
    """Return all saved assessments."""

    return get_all_assessments()


# =========================================================
# SINGLE ASSESSMENT
# =========================================================

@app.get("/api/assessments/{assessment_id}")
def get_assessment(assessment_id: int):
    """Return one assessment by ID."""

    data = get_assessment_by_id(
        assessment_id
    )

    if not data:
        raise HTTPException(
            status_code=404,
            detail="Assessment not found",
        )

    return data


# =========================================================
# STATISTICS
# =========================================================

@app.get("/api/stats")
def stats():
    """Return assessment statistics."""

    return get_stats()


# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/health")
def health():
    """Basic application health check."""

    return {
        "status": "ok",
        "app": "ChangeGuard",
        "version": APP_VERSION,
    }


# =========================================================
# STATIC FILES & SPA ROUTING
# =========================================================

if DIST_DIR.exists():
    app.mount(
        "/assets",
        StaticFiles(
            directory=DIST_DIR / "assets"
        ),
        name="assets",
    )


@app.api_route(
    "/{full_path:path}",
    methods=["GET", "HEAD"],
)
def serve_spa(full_path: str):
    """Serve the React frontend or fallback frontend."""

    if DIST_DIR.exists():
        target = DIST_DIR / full_path

        if target.is_file():
            return FileResponse(target)

        return FileResponse(
            DIST_DIR / "index.html"
        )

    # Fallback to the vanilla frontend if the
    # production frontend has not been built.
    target = FRONTEND_DIR / full_path

    if target.is_file():
        return FileResponse(target)

    return FileResponse(
        FRONTEND_DIR / "index.html"
    )
