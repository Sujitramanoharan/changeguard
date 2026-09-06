"""ChangeGuard FastAPI backend."""
import sys
import re
from pathlib import Path

# Let this file import from src/
sys.path.append(str(Path(__file__).parent.parent / "src"))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from agent import assess_change
from backend.database import init_db, save_assessment, get_all_assessments, get_stats

app = FastAPI(title="ChangeGuard")
init_db()

FRONTEND = Path(__file__).parent.parent / "frontend"


# --- the shape of an incoming change request ---
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
    """Pull recommendation / risk level / justification out of the LLM text."""
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
    save_assessment(change, result["ml_prediction"], rec, lvl, jus)
    return {
        "ml_prediction": result["ml_prediction"],
        "similar_changes": result["similar_changes"],
        "evidence": result["evidence"],
        "recommendation": rec,
        "risk_level": lvl,
        "justification": jus,
    }


@app.get("/api/history")
def history():
    return get_all_assessments()


@app.get("/api/stats")
def stats():
    return get_stats()


# --- serve the frontend pages ---
@app.get("/")
def home():
    return FileResponse(FRONTEND / "index.html")


app.mount("/", StaticFiles(directory=FRONTEND), name="static")