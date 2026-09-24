# ChangeGuard

[![CI](https://github.com/Sujitramanoharan/changeguard/actions/workflows/ci.yml/badge.svg)](https://github.com/Sujitramanoharan/changeguard/actions/workflows/ci.yml)

AI-assisted change risk assessment for enterprise change advisory boards (CAB).
Given a proposed infrastructure/deployment change, ChangeGuard combines a
calibrated ML model, retrieval over historical changes, and deterministic
evidence checks into a single **APPROVE / REVIEW / REJECT** recommendation
with a grounded, human-readable justification.

## How it works

1. **ML prediction** — a calibrated Logistic Regression model, trained on a
   synthetic ~600-record CAB dataset, predicts the probability that a change
   results in failure or an incident (`src/train_model.py`, `src/predict.py`).
2. **Retrieval (RAG)** — a FAISS index over `all-MiniLM-L6-v2` embeddings
   finds the most similar historical changes and their real outcomes
   (`src/retrieval.py`, `src/build_index.py`).
3. **Evidence tools** — deterministic lookups for incident history, schedule
   conflicts, and rollback safety (`src/tools.py`).
   Optionally, a rollback plan document (`.txt`/`.md`/`.pdf`) can be uploaded
   and is checked for a real, numbered procedure
   (`src/document_verification.py`) — a claimed rollback plan that isn't
   backed by a credible document raises the risk score instead of being
   trusted at face value.
4. **Risk policy** — the ML probability and evidence signals are combined by
   a deterministic, auditable policy (`src/risk_policy.py`) that produces the
   final recommendation and risk level. The LLM never decides the outcome —
   it only explains a score that has already been fixed by policy.
5. **Explanation** — an LLM (via Groq) generates a grounded justification
   referencing the evidence above (`src/agent.py`).
6. **Autonomous mode** — a LangGraph agent (`src/agent_graph.py`) can instead
   decide for itself which evidence tools to call, for comparison against the
   fixed pipeline. Restricted to admin users.
7. **Real GitHub change analysis** — a public GitHub commit or pull request
   link can be pasted in instead of hand-filling the form. ChangeGuard
   fetches the real diff and derives change type, size, and rollback
   signals from it (`src/repo_change_analysis.py`), then pre-fills the same
   form for review before running the same pipeline above — nothing here
   is a separate, unaudited path. Uses GitHub's public API, which shares
   a 60-requests/hour rate limit across every caller on the same outbound
   IP; set an optional `GITHUB_TOKEN` (a personal access token, no
   special scopes needed) to raise that to 5,000/hour — important on a
   host with a shared outbound IP.

## Architecture

```
web/            React (Vite + Tailwind) SPA — dashboard, new assessment,
                history, auth
backend/        FastAPI app: JWT auth, role-based authorization, rate
                limiting on login, SQLite audit trail, static file
                serving for the built SPA
src/            ML training, FAISS retrieval, evidence tools, risk policy,
                LangGraph agent, shared config
models/         Trained model artifacts + FAISS index + bundled embedding
                model (checked into git so the Docker image is
                self-contained and reproducible from a clean clone)
data/           Synthetic CAB dataset
tests/          Pytest suite for the risk policy and auth logic
```

Roles: **admin** (full access, including the autonomous agent) and
**reviewer** (controlled assessment pipeline + history, no autonomous mode).

## Running locally

Backend:

```bash
python -m venv venv
source venv/Scripts/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# .env must define:
#   CHANGEGUARD_JWT_SECRET=<random secret>
#   GROQ_API_KEY=<your Groq API key>

uvicorn backend.main:app --reload --port 7860
```

Create the first admin user:

```bash
python create_admin.py
```

Frontend (dev server, proxies /api to the backend on :7860):

```bash
cd web
npm install
npm run dev
```

## Running the test suite

```bash
pytest tests/ -v
```

Covers the deterministic risk policy (approval/rejection thresholds, rollback
and schedule-conflict penalties) and the JWT/password-hashing auth logic.

## Running with Docker

```bash
docker compose up --build
```

This builds the React app, bundles it with the FastAPI backend and the
pre-trained model artifacts into a single image, and serves everything on
`http://localhost:8000`. Assessment data and the SQLite audit database
persist in the `changeguard-data` named volume across restarts.

Required environment variables (put them in a `.env` file next to
`docker-compose.yml`, which Compose reads automatically):

```
GROQ_API_KEY=...
CHANGEGUARD_JWT_SECRET=...
```

On a host with no shell/exec access (e.g. a free-tier PaaS), also set
`ADMIN_USERNAME` and `ADMIN_PASSWORD` (and optionally `REVIEWER_USERNAME`
/ `REVIEWER_PASSWORD`) to have the app create those users automatically
on startup, instead of running `create_admin.py` interactively.

## Seeding demo data

```bash
python scripts/seed_demo_data.py
```

Runs 20 varied change scenarios through the real assessment pipeline (not
fabricated data) and backdates their timestamps to look like organic CAB
activity. Useful for demos, and for restoring a clean history after a
restart on any deployment with ephemeral storage.

## Regenerating the model artifacts

The dataset, trained model, and FAISS index are already committed under
`data/` and `models/`. To regenerate them from scratch:

```bash
python generate_dataset.py   # synthesize the CAB dataset
python src/train_model.py    # train + calibrate the risk model
python src/build_index.py    # build the FAISS retrieval index
```
