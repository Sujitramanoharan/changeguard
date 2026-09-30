"""ChangeGuard FastAPI backend."""

import json
import logging
import os
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Literal

sys.path.append(str(Path(__file__).parent.parent / "src"))

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from agent_graph import assess_change_autonomous
from agent import assess_code, assess_ticket
from ticket_risk import load_stats
from config import CORS_ORIGINS, APP_VERSION, METRICS_PATH
from document_verification import verify_rollback_document
from repo_change_analysis import RepoChangeError, analyze_github_url

from backend.records import record_assessment

from backend.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    decode_access_token,
    verify_password,
)

from backend.database import (
    init_db,
    create_user,
    delete_user,
    list_users,
    get_all_assessments,
    get_stats,
    get_assessment_by_id,
    get_user_by_username,
    save_document_verification,
    get_document_verification,
    record_cab_decision,
    record_actual_outcome,
    count_assessments,
    describe_database,
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


limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


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

    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred while processing the request.",
        },
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=[
        "Content-Type",
        "Authorization",
    ],
)


init_db()
logger.info("Database: %s", describe_database())


def bootstrap_user_from_env(
    role: str,
    username_var: str,
    password_var: str,
):
    """Create a user with the given role from env vars if none exists yet.

    Lets a fresh deployment (no shell/exec access on most free hosting
    tiers) get usable logins without a manual provisioning step.
    No-op if the vars are unset or the username already exists.
    """

    username = os.getenv(username_var)
    password = os.getenv(password_var)

    if not username or not password:
        return

    if get_user_by_username(username):
        return

    create_user(username=username, password=password, role=role)

    logger.info(
        "Bootstrapped %s user '%s' from %s/%s",
        role,
        username,
        username_var,
        password_var,
    )


bootstrap_user_from_env("admin", "ADMIN_USERNAME", "ADMIN_PASSWORD")
bootstrap_user_from_env("reviewer", "REVIEWER_USERNAME", "REVIEWER_PASSWORD")


def seed_demo_data_if_empty():
    """Seed the demo history in the background when the DB is empty.

    Free hosting tiers (e.g. Render free) wipe the disk on every
    restart. With SEED_DEMO_ON_EMPTY=true the dashboard repopulates
    itself instead of showing an empty audit trail. Runs in a thread so
    the server starts accepting requests (and passes health checks)
    immediately.
    """

    if os.getenv("SEED_DEMO_ON_EMPTY", "").lower() not in ("1", "true", "yes"):
        return

    if count_assessments() > 0:
        return

    def run():
        try:
            from demo_data import seed_demo_assessments

            count = seed_demo_assessments()
            logger.info("Auto-seeded %s demo assessments", count)

        except Exception:
            logger.exception("Auto-seeding demo data failed")

    threading.Thread(target=run, daemon=True).start()


seed_demo_data_if_empty()


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
@limiter.limit("5/minute")
def login(request: Request, req: LoginRequest):
    """Authenticate a user and return a JWT access token.

    Rate-limited per client IP to slow down credential-stuffing/brute
    -force attempts against this endpoint specifically.
    """

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
        "expires_in_minutes": ACCESS_TOKEN_EXPIRE_MINUTES,
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


YesNo = Literal["Yes", "No"]


class TicketRequest(BaseModel):
    """An ITIL change ticket, using the fields of the real Rabobank
    change records the ticket model was trained on."""

    title: str = Field(min_length=1, max_length=150)

    ci_type: str = Field(min_length=1, max_length=60)

    ci_subtype: str = Field(min_length=1, max_length=80)

    change_family: str = Field(min_length=1, max_length=60)

    risk_classification: Literal[
        "Minor Change",
        "Business Change",
        "Major Business Change",
    ]

    origin: Literal["Problem", "Incident"] = "Problem"

    incidents_30d: int = Field(ge=0, le=10000)

    planned_start: datetime

    planned_hours: float = Field(gt=0, le=2160)

    systems_affected: int = Field(ge=1, le=1000)

    downtime: bool = False

    emergency: bool = False

    cab_required: bool = False

    rollback_plan_exists: YesNo

    rollback_plan_tested: Literal["Yes", "No", "None"] = "None"

    schedule_conflict: YesNo = "No"

    description: str = Field(default="", max_length=2000)

    # ID returned by /api/documents/verify-rollback. The verification
    # result itself is looked up server-side - the client cannot claim
    # a document was verified.
    rollback_document_id: str | None = Field(default=None, max_length=64)


def validate_ticket_options(ticket: dict) -> None:
    """Reject categories the model has never seen in real data."""

    options = load_stats()["options"]

    if ticket["ci_type"] not in options["ci_type"]:
        raise HTTPException(status_code=422, detail=f"Unknown system type: {ticket['ci_type']}")

    if ticket["ci_subtype"] not in options["ci_subtype_by_type"].get(ticket["ci_type"], []):
        raise HTTPException(
            status_code=422,
            detail=f"'{ticket['ci_subtype']}' is not a subtype of '{ticket['ci_type']}'.",
        )

    if ticket["change_family"] not in options["change_family"]:
        raise HTTPException(status_code=422, detail=f"Unknown change type: {ticket['change_family']}")


class CodeAssessRequest(BaseModel):
    """A GitHub commit / pull request to assess, plus deployment context."""

    url: str = Field(min_length=1, max_length=500)

    schedule_conflict: YesNo = "No"

    rollback_document_id: str | None = Field(default=None, max_length=64)


def attach_document_evidence(
    change: dict,
    current_user: dict,
) -> dict:
    """Replace the client's document reference with the stored result."""

    document_id = change.pop("rollback_document_id", None)

    if not document_id:
        change["rollback_document_provided"] = False
        change["rollback_document_verified"] = False
        return change

    record = get_document_verification(document_id)

    if not record or record["username"] != current_user["username"]:
        raise HTTPException(
            status_code=400,
            detail=(
                "Rollback document verification not found. "
                "Upload the document again."
            ),
        )

    change["rollback_document_provided"] = True
    change["rollback_document_verified"] = record["verified"]
    change["rollback_document_filename"] = record["filename"]

    return change


MAX_DOCUMENT_BYTES = 5 * 1024 * 1024  # 5MB


def extract_document_text(
    filename: str,
    data: bytes,
) -> str:
    """Extract plain text from an uploaded .txt, .md, or .pdf document."""

    if filename.lower().endswith(".pdf"):
        from io import BytesIO

        from pypdf import PdfReader

        reader = PdfReader(BytesIO(data))

        return "\n".join(
            page.extract_text() or ""
            for page in reader.pages
        )

    return data.decode("utf-8", errors="ignore")


@app.post("/api/documents/verify-rollback")
def verify_rollback_document_upload(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Verify an uploaded rollback plan document is a real procedure.

    Deterministic heuristic (src/document_verification.py) - not an
    LLM judgment call - so this stays consistent with the rest of the
    evidence-gathering layer: the LLM never decides anything, it only
    ever explains a result that's already been computed.
    """

    if not file.filename or not file.filename.lower().endswith(
        (".txt", ".md", ".pdf")
    ):
        raise HTTPException(
            status_code=400,
            detail="Only .txt, .md, or .pdf files are supported.",
        )

    data = file.file.read()

    if len(data) > MAX_DOCUMENT_BYTES:
        raise HTTPException(
            status_code=400,
            detail="Document is too large (max 5MB).",
        )

    try:
        text = extract_document_text(file.filename, data)

    except Exception:
        raise HTTPException(
            status_code=400,
            detail=(
                "Could not read this document. Try a .txt, .md, "
                "or .pdf file."
            ),
        )

    result = verify_rollback_document(text)

    result["verification_id"] = save_document_verification(
        username=current_user["username"],
        filename=file.filename,
        result=result,
    )

    logger.info(
        "Rollback document verified | user=%s | filename=%s | verified=%s",
        current_user["username"],
        file.filename,
        result["verified"],
    )

    return result


class RepoChangeRequest(BaseModel):
    """A GitHub commit or pull request URL to analyze."""

    url: str = Field(
        min_length=1,
        max_length=500,
    )


def fetch_github_analysis(url: str, current_user: dict) -> dict:
    """Fetch and analyse a GitHub commit/PR, mapping failures to HTTP errors."""

    logger.info("Analyzing GitHub change | user=%s | url=%s", current_user["username"], url)

    try:
        return analyze_github_url(url)

    except RepoChangeError as err:
        raise HTTPException(status_code=400, detail=str(err))

    except Exception:
        logger.exception("Failed to analyze GitHub change | url=%s", url)

        raise HTTPException(
            status_code=502,
            detail="Could not reach GitHub or parse this change. Check the URL and try again.",
        )


@app.post("/api/analyze-repo-change")
def analyze_repo_change(
    req: RepoChangeRequest,
    current_user: dict = Depends(get_current_user),
):
    """Preview what ChangeGuard reads from a real GitHub commit/PR.

    Deterministic analysis of file paths, commit text and diff stats
    (src/repo_change_analysis.py), including the change metrics the
    code-risk model uses. Nothing is scored or saved here.
    """

    return fetch_github_analysis(req.url, current_user)


@app.get("/api/form-options")
def form_options(
    current_user: dict = Depends(get_current_user),
):
    """Real categories from the training data, for the ticket form."""

    return load_stats()["options"]


@app.post("/api/assess")
def assess(
    req: TicketRequest,
    current_user: dict = Depends(get_current_user),
):
    """Assess a change ticket with the controlled pipeline."""

    ticket = req.model_dump(mode="json")
    validate_ticket_options(ticket)
    ticket = attach_document_evidence(ticket, current_user)

    result = assess_ticket(ticket)

    return record_assessment("ticket", "controlled", ticket, result, result["assessment"], current_user)


@app.post("/api/assess-autonomous")
def assess_autonomous(
    req: TicketRequest,
    current_user: dict = Depends(require_admin),
):
    """Assess a change ticket with the autonomous LangGraph agent."""

    ticket = req.model_dump(mode="json")
    validate_ticket_options(ticket)
    ticket = attach_document_evidence(ticket, current_user)

    result = assess_change_autonomous(ticket)

    return record_assessment(
        "ticket",
        "autonomous",
        ticket,
        result,
        result["final_answer"],
        current_user,
        extra={"tools_called": result["tools_called"], "num_tool_calls": result["num_tool_calls"]},
    )


@app.post("/api/assess-code")
def assess_code_change(
    req: CodeAssessRequest,
    current_user: dict = Depends(get_current_user),
):
    """Assess a real GitHub commit / pull request with the code-risk model.

    The diff is re-fetched server-side, so the metrics that are scored
    and audited always come from GitHub, never from the client.
    """

    analysis = fetch_github_analysis(req.url, current_user)

    context = attach_document_evidence(
        {"rollback_document_id": req.rollback_document_id, "schedule_conflict": req.schedule_conflict},
        current_user,
    )

    result = assess_code(analysis, context)

    change = {**result["change"], "url": req.url}

    return record_assessment(
        "code",
        "controlled",
        change,
        result,
        result["assessment"],
        current_user,
        extra={"code_metrics": result["code_metrics"], "analysis": result["analysis"]},
    )


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


class CabDecisionRequest(BaseModel):
    """The human Change Advisory Board's final call on a change."""

    decision: Literal["APPROVE", "REJECT"]

    comment: str = Field(
        default="",
        max_length=1000,
    )


@app.post("/api/assessments/{assessment_id}/decision")
def cab_decision(
    assessment_id: int,
    req: CabDecisionRequest,
    current_user: dict = Depends(get_current_user),
):
    """Record the human CAB decision on top of the AI recommendation.

    ChangeGuard advises; a person decides. Overriding the AI requires a
    written reason so the audit trail explains every disagreement.
    """

    item = get_assessment_by_id(assessment_id)

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Assessment not found",
        )

    overrides_ai = (
        item["recommendation"] in ("APPROVE", "REJECT")
        and req.decision != item["recommendation"]
    )

    if overrides_ai and not req.comment.strip():
        raise HTTPException(
            status_code=400,
            detail=(
                "A comment is required when overriding the AI "
                "recommendation."
            ),
        )

    record_cab_decision(
        assessment_id,
        req.decision,
        req.comment.strip(),
        current_user["username"],
    )

    logger.info(
        "CAB decision recorded | assessment_id=%s | user=%s | "
        "decision=%s | ai_recommendation=%s | override=%s",
        assessment_id,
        current_user["username"],
        req.decision,
        item["recommendation"],
        overrides_ai,
    )

    return get_assessment_by_id(assessment_id)


class OutcomeRequest(BaseModel):
    """What actually happened after the change was implemented."""

    outcome: Literal["Success", "Failed", "Caused-Incident"]


@app.post("/api/assessments/{assessment_id}/outcome")
def actual_outcome(
    assessment_id: int,
    req: OutcomeRequest,
    current_user: dict = Depends(get_current_user),
):
    """Record the real outcome, closing the loop on the AI's prediction."""

    item = get_assessment_by_id(assessment_id)

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Assessment not found",
        )

    if item.get("cab_decision") != "APPROVE":
        raise HTTPException(
            status_code=400,
            detail=(
                "An outcome can only be recorded for a change the CAB "
                "approved."
            ),
        )

    record_actual_outcome(
        assessment_id,
        req.outcome,
        current_user["username"],
    )

    logger.info(
        "Actual outcome recorded | assessment_id=%s | user=%s | outcome=%s",
        assessment_id,
        current_user["username"],
        req.outcome,
    )

    return get_assessment_by_id(assessment_id)


@app.get("/api/model/metrics")
def model_metrics(
    current_user: dict = Depends(get_current_user),
):
    """Return the held-out test metrics saved when the model was trained."""

    if not METRICS_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="Model metrics not available. Retrain the model.",
        )

    return json.loads(METRICS_PATH.read_text(encoding="utf-8"))


class CreateUserRequest(BaseModel):
    """A new ChangeGuard account created by an administrator."""

    username: str = Field(
        min_length=3,
        max_length=100,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )

    password: str = Field(
        min_length=8,
        max_length=200,
    )

    role: Literal["admin", "reviewer"] = "reviewer"


@app.get("/api/admin/users")
def admin_list_users(
    current_user: dict = Depends(require_admin),
):
    """List all user accounts (no password hashes)."""

    return list_users()


@app.post("/api/admin/users", status_code=201)
def admin_create_user(
    req: CreateUserRequest,
    current_user: dict = Depends(require_admin),
):
    """Create a reviewer or admin account."""

    if get_user_by_username(req.username):
        raise HTTPException(
            status_code=409,
            detail="Username already exists.",
        )

    create_user(
        username=req.username,
        password=req.password,
        role=req.role,
    )

    logger.info(
        "User created | by=%s | username=%s | role=%s",
        current_user["username"],
        req.username,
        req.role,
    )

    user = get_user_by_username(req.username)

    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "created_at": user["created_at"],
    }


@app.delete("/api/admin/users/{username}")
def admin_delete_user(
    username: str,
    current_user: dict = Depends(require_admin),
):
    """Delete a user account. Admins cannot delete themselves."""

    if username == current_user["username"]:
        raise HTTPException(
            status_code=400,
            detail="You cannot delete your own account.",
        )

    if not delete_user(username):
        raise HTTPException(
            status_code=404,
            detail="User not found.",
        )

    logger.info(
        "User deleted | by=%s | username=%s",
        current_user["username"],
        username,
    )

    return {"deleted": username}


@app.post("/api/admin/seed-demo-data")
def seed_demo_data(
    current_user: dict = Depends(require_admin),
):
    """Replace all assessments with a realistic demo history.

    Runs real scenarios through the actual pipeline (not fabricated
    data). Intended for hosts with no shell access and ephemeral
    storage, where the audit database can reset unexpectedly.
    """

    from demo_data import seed_demo_assessments

    logger.info(
        "Seeding demo data | user=%s",
        current_user["username"],
    )

    count = seed_demo_assessments()

    logger.info(
        "Demo data seeded | user=%s | count=%s",
        current_user["username"],
        count,
    )

    return {"seeded": count}


@app.get("/health")
def health():
    """Basic application health check."""

    return {
        "status": "ok",
        "app": "ChangeGuard",
        "version": APP_VERSION,
    }


DIST_DIR = Path(__file__).parent.parent / "frontend_dist"


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
    """Serve the built React single-page application."""

    if not DIST_DIR.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                "Frontend build not found. Run `npm run build` "
                "in web/ or build the Docker image."
            ),
        )

    dist_root = DIST_DIR.resolve()
    target = (dist_root / full_path).resolve()

    # Only serve files that really live inside the build directory -
    # "../" segments in the URL must never escape it.
    if target.is_relative_to(dist_root) and target.is_file():
        return FileResponse(target)

    return FileResponse(
        DIST_DIR / "index.html"
    )