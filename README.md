# ChangeGuard

[![CI](https://github.com/Sujitramanoharan/changeguard/actions/workflows/ci.yml/badge.svg)](https://github.com/Sujitramanoharan/changeguard/actions/workflows/ci.yml)

AI-assisted change risk assessment for enterprise Change Advisory Boards
(CAB), **trained on real change history**. ChangeGuard scores two kinds of
change:

- **Change tickets (ITIL)** — with a model trained on ~26,000 real change
  records from Rabobank Group ICT.
- **Code changes (GitHub commits / pull requests)** — with a model trained
  on 106,674 real commits from 15 Apache projects, using metrics computed
  from the live GitHub diff.

Each assessment combines the model with deterministic evidence into one
**APPROVE / REVIEW / REJECT** recommendation, shows *why* (per-change SHAP
factors and the most similar real historical changes), explains it in plain
language, and leaves the final decision to a human.

## How it works

1. **Real-data risk models** (LightGBM)
   - *Ticket model* (`src/ticket_risk.py`, `src/train_ticket_model.py`):
     BPI Challenge 2014 Rabobank records. Label: incidents on the affected
     system rose in the 7 days after the change vs. the 7 days before
     (after-vs-before controls for systems that always have incidents).
     Features: system type/subtype, change type, risk classification,
     origin, recent incidents, planned duration, start day/hour, scope,
     downtime, emergency and CAB flags.
   - *Code model* (`src/code_risk.py`, `src/train_code_model.py`):
     ApacheJIT commits labelled bug-inducing via SZZ. Features: lines
     added/deleted, files, directories, top-level modules and change
     entropy — computed from the real GitHub diff exactly as the dataset
     defines them (`metrics_from_files`).
2. **Explanations** — LightGBM's built-in TreeSHAP gives the factors that
   pushed each individual score up or down.
3. **Similar real changes** (`src/similarity.py`) — FAISS nearest-neighbour
   search over every historical change, showing what actually happened
   after the most similar ones (Apache commits link to GitHub).
4. **Evidence tools** (`src/tools.py`) — system incident history and
   start-time risk from the real data, rollback readiness, and a
   server-side check that an uploaded rollback document contains a real
   numbered procedure (`src/document_verification.py`). The result is
   stored server-side and referenced by ID, so it cannot be faked.
5. **Risk policy** (`src/risk_policy.py`) — combines the model (as risk
   relative to a typical change) and the evidence into a readable score.
   The policy decides; the LLM never does. A rollback claim contradicted
   by its own document is never auto-approved.
6. **Explanation** — an LLM (Groq) writes a justification from the
   evidence (`src/agent.py`), with a labelled rule-based fallback.
7. **Autonomous mode** (admins) — a LangGraph agent (`src/agent_graph.py`)
   chooses which evidence tools to call; the same policy still decides.
8. **Human CAB decision & feedback loop** — reviewers approve or reject
   (overriding the AI needs a written reason) and later record the real
   outcome — the data an organisation would retrain on.

## Model performance (held-out real data)

| | Ticket model (Rabobank) | Code model (ApacheJIT) |
|---|---|---|
| Evaluation | newest 20% of changes (time split) | newest 20% of commits (time split) |
| ROC-AUC | **0.918** | **0.798** |
| Unseen projects | – | **0.794** (4 repos never seen in training) |
| Baseline | Rabobank's own manual risk rating: 0.585 | Commit size alone: 0.777 |
| Operating point | riskiest 10% flagged → 75% of risky changes caught | riskiest 20% flagged → 52% of buggy commits caught |

Full metrics are written to `models/metrics.json` at training time and shown
on the in-app Architecture page.

Decisions made along the way, deliberately:

- ApacheJIT's `fix` flag is **not** used: it means "linked to a Jira bug"
  in the dataset, which a live commit cannot reproduce. It would raise
  offline AUC to 0.86 while making live predictions wrong.
- Change types are grouped into their 6 families (e.g. *Release Type*)
  instead of 240 opaque codes; AUC cost < 0.01.
- The ticket model uses **monotonic constraints**: emergency, CAB-required
  and downtime flags, recent incidents and risk classification can only
  raise risk. Unconstrained, the model learned from just 88 emergency
  changes that "emergency" *lowers* risk, contradicting the data (9.1% vs
  4.4%); with constraints AUC also improved (0.911 → 0.919).
- Change type is fed to the model as its historical risk rate (learned
  from the training period only) with the same constraint. As a plain
  category the model showed "Release Type" *lowering* risk, although
  releases raised incidents 9.3% of the time vs 4.6% for standard
  changes. Cost: AUC 0.919 → 0.918.

**Limitations:** the Rabobank label is inferred and partly reflects how
incident-prone a system is, from one bank in 2013–14; SZZ labels are
imperfect and commit size explains much of the code signal; recent
ApacheJIT commits are under-labelled. An organisation should retrain on
its own history.

## GitHub pull-request check

`.github/workflows/changeguard-pr-check.yml` runs ChangeGuard on every pull
request and posts (then keeps updating) one comment with the verdict, the
top risk factors, the most similar real commits and a link to record the
CAB decision. The PR also appears in History as a code assessment awaiting
a decision.

- The workflow sends the changed-file list with line counts and each
  file's diff, so ChangeGuard needs no access to the repository and
  private repositories work too. The model scores only the counts; the
  diff text is scanned for rollback / reverse-migration steps.
- Setup in the repository to check (Settings → Secrets and variables →
  Actions): secret `CHANGEGUARD_API_KEY` (must equal the server's
  `CHANGEGUARD_CI_API_KEY`) and variable `CHANGEGUARD_URL`.
- Set `FAIL_ON_REJECT: "true"` and make the check required in branch
  protection to block merging REJECTed changes until the CAB decides.

## Prompt-injection screening (RedTeamGPT)

The ticket title and description, and a commit or PR message, are the only
parts of an LLM prompt that whoever submits the change controls. When
`REDTEAMGPT_URL` (and `REDTEAMGPT_API_KEY`) are set, ChangeGuard sends that
text to [RedTeamGPT](https://github.com/Sujitramanoharan/redteamgpt), a
prompt-injection firewall, before any LLM reads it:

| Screening result | What ChangeGuard does |
|---|---|
| clean | The LLM sees the text as before. |
| flagged | The flagged text is withheld from the LLM, a red "Prompt security" evidence card explains why, and the change is never auto-approved (at least REVIEW). The risk score itself is unchanged: manipulative text is not technical risk. |
| unreachable | Fail closed: no unscreened text reaches the LLM; the explanation is rule-based. |

The deterministic policy already decides the verdict, so an injection could
never approve a change; screening also keeps it out of the explanation the
CAB reads, and records the attempt in the audit trail. `/health` reports
`prompt_screening: true` when it is configured.

## Database

PostgreSQL when `DATABASE_URL` is set (users, assessments and CAB
decisions survive restarts and redeploys), otherwise a local SQLite file.
Existing SQLite databases are upgraded in place. `docker compose up` runs
the app with a Postgres container; `render.yaml` provisions a Render
Postgres database. To run the test suite against Postgres:

```bash
TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/test pytest tests/
```

## Architecture

```
web/            React (Vite + Tailwind) SPA - dashboard, change ticket and
                code change assessment, history, users, architecture
backend/        FastAPI: JWT auth, roles, rate-limited login, SQLite audit
                trail, serves the built SPA
src/            Models, training scripts, similarity search, evidence
                tools, risk policy, pipeline and LangGraph agent
models/         Trained models, FAISS indexes, metrics and form options
                (committed, so the Docker image is self-contained)
data/raw/       Downloaded public datasets (not committed)
scripts/        Dataset download and demo seeding
tests/          Pytest suite
```

Roles: **admin** (everything, including the autonomous agent and user
management) and **reviewer** (assessments, history, CAB decisions and
outcomes).

## Running locally

```bash
python -m venv venv
venv\Scripts\activate            # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt

# .env must define:
#   CHANGEGUARD_JWT_SECRET=<random secret>
#   GROQ_API_KEY=<your Groq API key>

uvicorn backend.main:app --reload --port 7860
python create_admin.py           # first admin user
```

Frontend dev server (proxies /api to :7860):

```bash
cd web
npm install
npm run dev
```

## Retraining the models

The trained models are committed. To rebuild them from the public data:

```bash
python scripts/download_datasets.py   # ~37 MB into data/raw/
python src/train_ticket_model.py      # ~1 min
python src/train_code_model.py        # ~1 min
```

## Running the test suite

```bash
pytest tests/ -v
```

Covers the models and feature extraction (including the entropy formula),
the risk policy, auth, document verification, GitHub analysis, rate
limiting, and the API (authorization, path traversal, server-side document
verification, ticket validation, code assessment, CAB decisions, users).
Tests use a throwaway database.

## Running with Docker

```bash
docker compose up --build
```

Serves everything on `http://localhost:8000`, with the audit database in the
`changeguard-data` volume. Put `GROQ_API_KEY` and `CHANGEGUARD_JWT_SECRET` in
a `.env` next to `docker-compose.yml`. Set `ADMIN_USERNAME`/`ADMIN_PASSWORD`
(and optionally `REVIEWER_USERNAME`/`REVIEWER_PASSWORD`) to create users on
startup.

## Deploying to Render

`render.yaml` is a Render Blueprint (**New → Blueprint**). Fill in
`GROQ_API_KEY`, the admin/reviewer credentials and optionally `GITHUB_TOKEN`
(raises GitHub's API limit from 60 to 5,000 requests/hour).

Free-plan notes:

- Without `DATABASE_URL` the free plan's disk is wiped on every
  restart/deploy; attach a Postgres database to keep data.
  `SEED_DEMO_ON_EMPTY=true` seeds the demo history only when the database
  is empty (1–2 minutes).
- The service sleeps after ~15 minutes idle; the first request takes about
  a minute.
- The app uses ~330 MB of memory, within the 512 MB free tier.

## Local network note

On networks that publish IPv6 DNS records but do not route IPv6, outbound
calls (Groq, GitHub, dataset downloads) stall ~40 s. Set
`CHANGEGUARD_PREFER_IPV4=true` in `.env`.

## Seeding demo data

```bash
python scripts/seed_demo_data.py
```

Runs 14 realistic change tickets and 6 real public GitHub commits (analysed
once, stored in `data/demo_code_changes.json`) through the real pipeline.
The older half gets a CAB decision and outcome recorded by the user
`demo-cab`, labelled "Demo seed".

## Data sources & credits

- **ApacheJIT** — H. Keshavarz and M. Nagappan, *ApacheJIT: A Large Dataset
  for Just-In-Time Defect Prediction*, MSR 2022.
  [zenodo.org/records/5907002](https://zenodo.org/records/5907002), CC-BY-4.0.
- **BPI Challenge 2014** — Rabobank Group ICT, 4TU.ResearchData.
  [data.4tu.nl/collections/BPI_Challenge_2014/5065469](https://data.4tu.nl/collections/BPI_Challenge_2014/5065469).
