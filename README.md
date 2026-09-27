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
   Its three history features (similar-change count and failure rate,
   system incident average) are computed by the *same* code at training
   and inference time (`src/context.py`, `src/data_prep.py`), using
   leave-one-out FAISS retrieval during training.
2. **Retrieval (RAG)** — a FAISS index over `all-MiniLM-L6-v2` embeddings
   finds the most similar historical changes and their real outcomes
   (`src/retrieval.py`, `src/build_index.py`).
3. **Evidence tools** — deterministic lookups for incident history, schedule
   conflicts, and rollback safety (`src/tools.py`).
   Optionally, a rollback plan document (`.txt`/`.md`/`.pdf`) can be uploaded
   and is checked for a real, numbered procedure
   (`src/document_verification.py`) — a claimed rollback plan that isn't
   backed by a credible document raises the risk score instead of being
   trusted at face value. The verification result is stored server-side
   and referenced by ID, so a client cannot claim a document was verified.
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
8. **Human CAB decision** — ChangeGuard advises, a person decides. A
   reviewer records APPROVE/REJECT on each assessment; overriding a firm
   AI recommendation requires a written reason.
9. **Feedback loop** — for approved changes, the real outcome (Success /
   Failed / Caused-Incident) is recorded afterwards. The dashboard shows
   how many changes that went badly the AI had flagged beforehand.
10. **Model card** — held-out metrics saved at training time
    (`models/metrics.json`) are shown on the Architecture page.

## Model performance

Held-out test set (120 changes, 21.7% bad outcomes), `risk-model-v2`:

| Metric | Value |
|---|---|
| ROC-AUC | 0.836 |
| Recall (bad changes caught) | 0.615 |
| Precision | 0.571 |
| Brier score | 0.131 |
| Mean predicted vs. actual bad rate | 0.209 vs. 0.217 |

`risk-model-v1` was trained on the raw synthetic history columns (e.g.
similar-change counts up to ~60), which the live app can never produce
(it derives at most 5 FAISS matches). On runtime-derived inputs v1
over-estimated risk (mean 0.278 vs. 0.217 actual); v2 is trained on
exactly what it sees in production.

**Limitations:** the dataset is synthetic, so absolute numbers will differ
on real CAB data; document verification is a structural heuristic, not a
semantic review. Recorded real outcomes are the path to retraining.

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

Roles: **admin** (full access, including the autonomous agent and user
management) and **reviewer** (controlled assessment pipeline, history,
CAB decisions and outcomes; no autonomous mode).

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

Covers the deterministic risk policy, auth, document verification, GitHub
change analysis, rate limiting, and the API layer (authorization, path
traversal protection, server-side document verification, CAB decisions,
user management). Tests use a throwaway database, never `changeguard.db`.

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

## Deploying to Render

`render.yaml` is a Render Blueprint. In the Render dashboard choose
**New → Blueprint**, select this repository, and fill in the prompted
secrets (`GROQ_API_KEY`, `ADMIN_USERNAME`/`ADMIN_PASSWORD`, optionally
`REVIEWER_USERNAME`/`REVIEWER_PASSWORD` and `GITHUB_TOKEN`).
`CHANGEGUARD_JWT_SECRET` is generated automatically.

Notes for the free plan:

- The disk is wiped on every restart/deploy. `SEED_DEMO_ON_EMPTY=true`
  re-creates the demo history in the background on startup (about 20 LLM
  calls, 1–2 minutes), and the env-var users are re-created too.
- The service sleeps after ~15 minutes idle; the first request after that
  takes about a minute. Open the app a few minutes before a demo.
- The container listens on `$PORT` and runs uvicorn with
  `--proxy-headers`, so the login rate limit applies per real client IP.

## Local network note

On networks that publish IPv6 DNS records but do not route IPv6, every
outbound call (Groq, GitHub) stalls ~40s before falling back to IPv4.
Set `CHANGEGUARD_PREFER_IPV4=true` in `.env` to try IPv4 first.

## Seeding demo data

```bash
python scripts/seed_demo_data.py
```

Runs 20 varied change scenarios through the real assessment pipeline (not
fabricated data) and backdates their timestamps to look like organic CAB
activity. The older half also gets a CAB decision and, where approved, an
outcome — recorded by the user `demo-cab` and labelled "Demo seed" so they
are never mistaken for real board decisions. Useful for demos, and for restoring a clean history after a
restart on any deployment with ephemeral storage.

## Regenerating the model artifacts

The dataset, trained model, and FAISS index are already committed under
`data/` and `models/`. To regenerate them from scratch:

```bash
python generate_dataset.py   # synthesize the CAB dataset (move it into data/)
python src/build_index.py    # build the FAISS retrieval index
python src/train_model.py    # train + calibrate the model, write metrics.json
```

The index must be built before training: training derives its history
features from FAISS retrieval, exactly as the live app does.
