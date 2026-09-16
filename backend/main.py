"""ChangeGuard FastAPI backend."""

import sys
import re
from pathlib import Path

# Let this file import from src/
sys.path.append(str(Path(__file__).parent.parent / "src"))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from agent_graph import assess_change_autonomous
from agent import assess_change
from predict import predict_risk

from backend.database import (
    init_db,
    save_assessment,
    get_all_assessments,
    get_stats,
    get_assessment_by_id,
)


app = FastAPI(
    title="ChangeGuard - AI Enterprise Change Risk Assessment"
)


# ---------------------------------------------------------
# CORS
# ---------------------------------------------------------

# Enable CORS for local development and frontend clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# Database initialization
# ---------------------------------------------------------

init_db()


# ---------------------------------------------------------
# Frontend paths
# ---------------------------------------------------------

DIST_DIR = Path(__file__).parent.parent / "frontend_dist"
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


# ---------------------------------------------------------
# Request model
# ---------------------------------------------------------

class ChangeRequest(BaseModel):
    system: str
    change_type: str
    change_size: str
    requester_team: str
    requested_window: str

    rollback_plan_exists: str
    rollback_plan_tested: str = "None"

    similar_past_changes_count: int = 10
    similar_past_changes_failure_rate: float = 0.2
    system_incidents_last_90_days: int = 1

    schedule_conflict: str = "No"

    description: str = ""


# ---------------------------------------------------------
# Assessment parser
# ---------------------------------------------------------

def parse_assessment(text):
    """Pull recommendation / risk level / justification out of LLM text."""

    rec = re.search(
        r"RECOMMENDATION:\s*(\w+)",
        text
    )

    lvl = re.search(
        r"RISK LEVEL:\s*(\w+)",
        text
    )

    jus = re.search(
        r"JUSTIFICATION:\s*(.+)",
        text,
        re.S
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

    # Convert validated request into dictionary
    change = req.dict()

    # Run controlled ChangeGuard pipeline
    result = assess_change(change)

    # Extract final recommendation
    rec, lvl, jus = parse_assessment(
        result["assessment"]
    )

    # Store complete evidence and assessment details
    details = {
        "mode": "controlled",
        "change": change,
        "ml_prediction": result["ml_prediction"],
        "similar_changes": result["similar_changes"],
        "evidence": result["evidence"],
        "recommendation": rec,
        "risk_level": lvl,
        "justification": jus,
    }

    # Save assessment to database
    new_id = save_assessment(
        change,
        result["ml_prediction"],
        rec,
        lvl,
        jus,
        details=details,
    )

    # Return result to frontend
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

    # Convert validated request into dictionary
    change = req.dict()

    # Run autonomous LangGraph agent
    result = assess_change_autonomous(change)

    # Parse the agent's final response
    rec, lvl, jus = parse_assessment(
        result["final_answer"]
    )

    # IMPORTANT:
    # Get the REAL ML model prediction.
    #
    # Previously this endpoint created a fake "ml_dummy"
    # probability based only on the final risk level.
    #
    # Now both Controlled and Autonomous modes use the
    # actual trained ML model.
    ml_prediction = predict_risk(change)

    # Store complete autonomous assessment details
    details = {
        "mode": "autonomous",
        "change": change,
        "ml_prediction": ml_prediction,
        "recommendation": rec,
        "risk_level": lvl,
        "justification": jus,
        "tools_called": result["tools_called"],
        "num_tool_calls": result["num_tool_calls"],
    }

    # Save assessment to database
    new_id = save_assessment(
        change,
        ml_prediction,
        rec,
        lvl,
        jus,
        details=details,
    )

    # Return result to frontend
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
    return get_all_assessments()


# =========================================================
# SINGLE ASSESSMENT
# =========================================================

@app.get("/api/assessments/{assessment_id}")
def get_assessment(assessment_id: int):

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
    return get_stats()


# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/health")
def health():

    return {
        "status": "ok",
        "app": "ChangeGuard",
        "version": "1.0.0",
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
    methods=["GET", "HEAD"]
)
def serve_spa(full_path: str):

    if DIST_DIR.exists():

        target = DIST_DIR / full_path

        if target.is_file():
            return FileResponse(target)

        return FileResponse(
            DIST_DIR / "index.html"
        )

    else:

        # Fallback to vanilla HTML frontend
        # if dist has not been compiled.
        target = FRONTEND_DIR / full_path

        if target.is_file():
            return FileResponse(target)

        return FileResponse(
            FRONTEND_DIR / "index.html"
        )