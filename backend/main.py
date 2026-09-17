"""ChangeGuard FastAPI backend."""

import logging
import re
import sys
from pathlib import Path
from typing import Literal

sys.path.append(str(Path(__file__).parent.parent / "src"))

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent_graph import assess_change_autonomous
from agent import assess_change
from config import CORS_ORIGINS, APP_VERSION

from backend.auth import (
    create_access_token,
    decode_access_token,
    verify_password,
)

from backend.database import (
    init_db,
    save_assessment,
    get_all_assessments,
    get_stats,
    get_assessment_by_id,
    get_user_by_username,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("changeguard")


app = FastAPI(
    title="ChangeGuard - AI Enterprise Change Risk Assessment",
    version=APP_VERSION,
)


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


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=[
        "Content-Type",
        "Authorization",
    ],
)


init_db()


security = HTTPBearer(
    auto_error=False,
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    """Validate JWT access token and return the authenticated user."""

    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication scheme",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    token = credentials.credentials

    try:
        payload = decode_access_token(token)

    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    username = payload.get("sub")
    role = payload.get("role")

    if not username or not role:
        raise HTTPException(
            status_code=401,
            detail="Invalid access token",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    user = get_user_by_username(username)

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User account not found",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
    }


def require_admin(
    current_user: dict = Depends(get_current_user),
):
    """Require an authenticated administrator."""

    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=403,
            detail="Administrator access required",
        )

    return current_user


class LoginRequest(BaseModel):
    """Login credentials."""

    username: str = Field(
        min_length=1,
        max_length=100,
    )

    password: str = Field(
        min_length=1,
        max_length=200,
    )


@app.post("/api/auth/login")
def login(req: LoginRequest):
    """Authenticate a user and return a JWT access token."""

    user = get_user_by_username(
        req.username
    )

    if not user:
        logger.warning(
            "Failed login attempt | username=%s | reason=user_not_found",
            req.username,
        )

        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )

    if not verify_password(
        req.password,
        user["password_hash"],
    ):
        logger.warning(
            "Failed login attempt | username=%s | reason=invalid_password",
            req.username,
        )

        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )

    token = create_access_token(
        username=user["username"],
        role=user["role"],
    )

    logger.info(
        "Successful login | username=%s | role=%s",
        user["username"],
        user["role"],
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in_minutes": 60,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
        },
    }


@app.get("/api/auth/me")
def current_user(
    current_user: dict = Depends(get_current_user),
):
    """Return the currently authenticated user."""

    return current_user


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


def parse_assessment(text: str):
    """Extract generated recommendation, risk level and justification."""

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


@app.post("/api/assess")
def assess(
    req: ChangeRequest,
    current_user: dict = Depends(get_current_user),
):
    """Run the controlled ChangeGuard assessment pipeline."""

    change = req.model_dump()

    logger.info(
        "Starting controlled assessment | user=%s | system=%s | change_type=%s",
        current_user["username"],
        change["system"],
        change["change_type"],
    )

    result = assess_change(change)

    policy = result["policy"]

    rec = policy["recommendation"]
    lvl = policy["risk_level"]

    logger.info(
        "Controlled assessment decision | user=%s | recommendation=%s | risk_level=%s",
        current_user["username"],
        rec,
        lvl,
    )

    _, _, jus = parse_assessment(
        result["assessment"]
    )

    details = {
        "mode": "controlled",
        "user": {
            "username": current_user["username"],
            "role": current_user["role"],
        },
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

    new_id = save_assessment(
        change,
        result["ml_prediction"],
        rec,
        lvl,
        jus,
        details=details,
    )

    logger.info(
        "Controlled assessment saved | assessment_id=%s | user=%s",
        new_id,
        current_user["username"],
    )

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
def assess_autonomous(
    req: ChangeRequest,
    current_user: dict = Depends(require_admin),
):
    """Run the autonomous LangGraph ChangeGuard assessment."""

    change = req.model_dump()

    logger.info(
        "Starting autonomous assessment | user=%s | system=%s | change_type=%s",
        current_user["username"],
        change["system"],
        change["change_type"],
    )

    result = assess_change_autonomous(change)

    policy = result["policy"]

    rec = policy["recommendation"]
    lvl = policy["risk_level"]

    logger.info(
        "Autonomous assessment decision | user=%s | recommendation=%s | risk_level=%s | tool_calls=%s",
        current_user["username"],
        rec,
        lvl,
        result["num_tool_calls"],
    )

    _, _, jus = parse_assessment(
        result["final_answer"]
    )

    ml_prediction = result["ml_prediction"]

    details = {
        "mode": "autonomous",
        "user": {
            "username": current_user["username"],
            "role": current_user["role"],
        },
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

    new_id = save_assessment(
        change,
        ml_prediction,
        rec,
        lvl,
        jus,
        details=details,
    )

    logger.info(
        "Autonomous assessment saved | assessment_id=%s | user=%s",
        new_id,
        current_user["username"],
    )

    return {
        "id": new_id,
        "ml_prediction": ml_prediction,
        "recommendation": rec,
        "risk_level": lvl,
        "justification": jus,
        "tools_called": result["tools_called"],
        "num_tool_calls": result["num_tool_calls"],
    }


@app.get("/api/history")
def history(
    current_user: dict = Depends(get_current_user),
):
    """Return all saved assessments."""

    return get_all_assessments()


@app.get("/api/assessments/{assessment_id}")
def get_assessment(
    assessment_id: int,
    current_user: dict = Depends(get_current_user),
):
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


@app.get("/api/stats")
def stats(
    current_user: dict = Depends(get_current_user),
):
    """Return assessment statistics."""

    return get_stats()


@app.get("/health")
def health():
    """Basic application health check."""

    return {
        "status": "ok",
        "app": "ChangeGuard",
        "version": APP_VERSION,
    }


DIST_DIR = Path(__file__).parent.parent / "frontend_dist"
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


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

    target = FRONTEND_DIR / full_path

    if target.is_file():
        return FileResponse(target)

    return FileResponse(
        FRONTEND_DIR / "index.html"
    )