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
from backend.database import (
    init_db, save_assessment, get_all_assessments, get_stats, get_assessment_by_id
)

app = FastAPI(title="ChangeGuard - AI Enterprise Change Risk Assessment")

# Enable CORS for local dev and frontend clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

DIST_DIR = Path(__file__).parent.parent / "frontend_dist"
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


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


def parse_assessment(text):
    """Pull recommendation / risk level / justification out of LLM text."""
    rec = re.search(r"RECOMMENDATION:\s*(\w+)", text)
    lvl = re.search(r"RISK LEVEL:\s*(\w+)", text)
    jus = re.search(r"JUSTIFICATION:\s*(.+)", text, re.S)
    return (
        rec.group(1) if rec else "REVIEW",
        lvl.group(1) if lvl else "Medium",
        jus.group(1).strip() if jus else text,
    )


@app.post("/api/assess")
def assess(req: ChangeRequest):
    change = req.dict()
    result = assess_change(change)
    rec, lvl, jus = parse_assessment(result["assessment"])
    
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
    
    new_id = save_assessment(change, result["ml_prediction"], rec, lvl, jus, details=details)
    return {
        "id": new_id,
        "ml_prediction": result["ml_prediction"],
        "similar_changes": result["similar_changes"],
        "evidence": result["evidence"],
        "recommendation": rec,
        "risk_level": lvl,
        "justification": jus,
    }


@app.post("/api/assess-autonomous")
def assess_autonomous(req: ChangeRequest):
    change = req.dict()
    result = assess_change_autonomous(change)
    rec, lvl, jus = parse_assessment(result["final_answer"])
    
    ml_dummy = {"risk_probability": 0.35 if lvl == "Medium" else (0.75 if lvl == "High" else 0.1), "risk_level": lvl}
    
    details = {
        "mode": "autonomous",
        "change": change,
        "recommendation": rec,
        "risk_level": lvl,
        "justification": jus,
        "tools_called": result["tools_called"],
        "num_tool_calls": result["num_tool_calls"],
    }
    
    new_id = save_assessment(change, ml_dummy, rec, lvl, jus, details=details)
    return {
        "id": new_id,
        "recommendation": rec,
        "risk_level": lvl,
        "justification": jus,
        "tools_called": result["tools_called"],
        "num_tool_calls": result["num_tool_calls"],
    }


@app.get("/api/history")
def history():
    return get_all_assessments()


@app.get("/api/assessments/{assessment_id}")
def get_assessment(assessment_id: int):
    data = get_assessment_by_id(assessment_id)
    if not data:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return data


@app.get("/api/stats")
def stats():
    return get_stats()


@app.get("/health")
def health():
    return {"status": "ok", "app": "ChangeGuard", "version": "1.0.0"}


# --- Static files & SPA Routing ---
if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

@app.api_route("/{full_path:path}", methods=["GET", "HEAD"])
def serve_spa(full_path: str):
    if DIST_DIR.exists():
        target = DIST_DIR / full_path
        if target.is_file():
            return FileResponse(target)
        return FileResponse(DIST_DIR / "index.html")
    else:
        # Fallback to vanilla HTML frontend if dist not compiled
        target = FRONTEND_DIR / full_path
        if target.is_file():
            return FileResponse(target)
        return FileResponse(FRONTEND_DIR / "index.html")