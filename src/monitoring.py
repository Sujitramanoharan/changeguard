"""Model monitoring and the feedback loop.

A model that is never checked after deployment silently goes stale. This
module answers, from the audit trail alone:

  * Are people using it?           verdict mix per day, by kind and mode
  * Do people trust it?            how often the CAB overrides the AI
  * Was it right?                  recorded real outcomes vs the recommendation
  * Has the input changed?         drift of live inputs against the training data
  * Is anyone attacking it?        RedTeamGPT prompt-screening results
  * Has it been retrained?         the gated retraining history

Drift uses the Population Stability Index (PSI) per feature against a
reference profile of the training data (models/reference_profile.json,
written by scripts/build_reference_profile.py). Rule of thumb used in
credit-risk model monitoring: PSI < 0.1 stable, 0.1-0.25 moderate shift,
> 0.25 significant shift.
"""

import json
import math
from collections import Counter
from datetime import datetime, timedelta

import numpy as np

from config import METRICS_PATH, MODELS_DIR

REFERENCE_PATH = MODELS_DIR / "reference_profile.json"
RETRAIN_HISTORY_PATH = MODELS_DIR / "retrain_history.json"

# Outcomes and CAB decisions written by the demo seeder (src/demo_data.py).
# They are shown, but labelled, and never used for retraining.
DEMO_USER = "demo-cab"

BAD_OUTCOMES = {"Failed", "Caused-Incident"}
VERDICTS = ("APPROVE", "REVIEW", "REJECT")

MIN_DRIFT_SAMPLE = 20
PSI_MODERATE = 0.1
PSI_SIGNIFICANT = 0.25

DRIFT_FEATURES = {
    "ticket": {
        "numeric": ["incidents_30d", "planned_hours", "systems_affected", "hour", "weekday"],
        "categorical": ["ci_type", "change_family"],
    },
    "code": {
        "numeric": ["la", "ld", "nf", "nd", "ns", "ent"],
        "categorical": [],
    },
}

FEATURE_LABELS = {
    "incidents_30d": "Incidents on the system (30 days)",
    "planned_hours": "Planned duration (hours)",
    "systems_affected": "Systems affected",
    "hour": "Start hour",
    "weekday": "Start day",
    "ci_type": "System type",
    "change_family": "Change type",
    "la": "Lines added",
    "ld": "Lines deleted",
    "nf": "Files changed",
    "nd": "Directories touched",
    "ns": "Top-level modules touched",
    "ent": "Change spread (entropy)",
}


# -------------------------------------------------------------------
# Reference profile (built from the training data)
# -------------------------------------------------------------------

def _numeric_profile(values) -> dict:
    values = np.asarray(values, dtype=float)
    values = values[~np.isnan(values)]
    edges = sorted(set(float(round(q, 6)) for q in np.quantile(values, np.linspace(0.1, 0.9, 9))))
    counts = np.bincount(np.searchsorted(edges, values, side="right"), minlength=len(edges) + 1)
    return {"type": "numeric", "edges": edges, "proportions": (counts / counts.sum()).round(6).tolist()}


def _categorical_profile(values, top: int = 8) -> dict:
    counts = Counter(str(v) for v in values)
    total = sum(counts.values())
    keep = [k for k, _ in counts.most_common(top)]
    props = {k: round(counts[k] / total, 6) for k in keep}
    props["__other__"] = max(0.0, round(1 - sum(props.values()), 6))
    return {"type": "categorical", "proportions": props}


def build_reference(frame, numeric: list, categorical: list, source: str) -> dict:
    """Distribution of each input feature in the training data."""

    features = {f: _numeric_profile(frame[f]) for f in numeric}
    features.update({f: _categorical_profile(frame[f]) for f in categorical})
    return {"source": source, "rows": int(len(frame)), "features": features}


def save_reference(kind: str, profile: dict) -> None:
    data = json.loads(REFERENCE_PATH.read_text(encoding="utf-8")) if REFERENCE_PATH.exists() else {}
    data[kind] = profile
    REFERENCE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_reference() -> dict:
    if not REFERENCE_PATH.exists():
        return {}
    return json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))


# -------------------------------------------------------------------
# Drift
# -------------------------------------------------------------------

def psi(expected: list, actual: list) -> float:
    """Population Stability Index between two binned distributions."""

    eps = 1e-4
    total = 0.0
    for e, a in zip(expected, actual):
        e, a = max(e, eps), max(a, eps)
        total += (a - e) * math.log(a / e)
    return round(total, 4)


def _live_proportions(spec: dict, values: list) -> list:
    if spec["type"] == "numeric":
        vals = np.asarray([float(v) for v in values], dtype=float)
        counts = np.bincount(np.searchsorted(spec["edges"], vals, side="right"),
                             minlength=len(spec["edges"]) + 1)
        return (counts / counts.sum()).tolist()

    keys = list(spec["proportions"])
    counts = Counter(str(v) if str(v) in keys else "__other__" for v in values)
    return [counts[k] / len(values) for k in keys]


def _expected(spec: dict) -> list:
    if spec["type"] == "numeric":
        return spec["proportions"]
    return list(spec["proportions"].values())


def drift_status(value: float) -> str:
    if value >= PSI_SIGNIFICANT:
        return "significant"
    if value >= PSI_MODERATE:
        return "moderate"
    return "stable"


def live_features(item: dict) -> tuple[str, dict] | None:
    """The model inputs recorded with one assessment."""

    details = item.get("details") or {}
    kind = details.get("kind") or item.get("assessment_type")

    if kind == "code":
        metrics = details.get("code_metrics")
        return ("code", metrics) if metrics else None

    change = details.get("change") or {}
    start = change.get("planned_start")
    if not start:
        return None
    try:
        when = datetime.fromisoformat(str(start))
    except ValueError:
        return None
    return ("ticket", {**change, "weekday": when.weekday(), "hour": when.hour})


def drift_report(items: list, reference: dict) -> dict:
    rows = {"ticket": [], "code": []}
    for item in items:
        found = live_features(item)
        if found:
            rows[found[0]].append(found[1])

    report = {}
    for kind, spec in DRIFT_FEATURES.items():
        ref = reference.get(kind)
        n = len(rows[kind])

        if not ref:
            report[kind] = {"status": "no_reference", "n": n, "features": []}
            continue
        if n < MIN_DRIFT_SAMPLE:
            report[kind] = {"status": "insufficient", "n": n, "min": MIN_DRIFT_SAMPLE, "features": []}
            continue

        features = []
        for feature in spec["numeric"] + spec["categorical"]:
            fspec = ref["features"].get(feature)
            values = [r.get(feature) for r in rows[kind] if r.get(feature) is not None]
            if not fspec or not values:
                continue
            value = psi(_expected(fspec), _live_proportions(fspec, values))
            features.append({
                "feature": feature,
                "label": FEATURE_LABELS.get(feature, feature),
                "psi": value,
                "status": drift_status(value),
            })

        features.sort(key=lambda f: -f["psi"])
        worst = features[0]["status"] if features else "stable"
        report[kind] = {"status": worst, "n": n, "reference_rows": ref["rows"], "features": features}

    return report


# -------------------------------------------------------------------
# Usage, trust, outcomes, screening
# -------------------------------------------------------------------

def volume_report(items: list, days: int = 30, today: datetime | None = None) -> dict:
    today = (today or datetime.now()).date()
    start = today - timedelta(days=days - 1)
    per_day = {start + timedelta(days=i): Counter() for i in range(days)}

    for item in items:
        try:
            day = datetime.fromisoformat(str(item.get("created_at"))[:16]).date()
        except ValueError:
            continue
        if day in per_day:
            per_day[day][item.get("recommendation")] += 1

    details = [(i.get("details") or {}) for i in items]
    return {
        "total": len(items),
        "last_days": days,
        "in_window": sum(sum(c.values()) for c in per_day.values()),
        "by_day": [{"date": d.isoformat(), **{v: c[v] for v in VERDICTS}} for d, c in per_day.items()],
        "by_verdict": {v: sum(1 for i in items if i.get("recommendation") == v) for v in VERDICTS},
        "by_kind": dict(Counter(d.get("kind") or "ticket" for d in details)),
        "by_mode": dict(Counter(d.get("mode") or "controlled" for d in details)),
    }


def cab_report(items: list) -> dict:
    decided = [i for i in items if i.get("cab_decision")]
    matrix = {v: {"APPROVE": 0, "REJECT": 0} for v in VERDICTS}
    for i in decided:
        if i.get("recommendation") in matrix:
            matrix[i["recommendation"]][i["cab_decision"]] += 1

    firm = [i for i in decided if i.get("recommendation") in ("APPROVE", "REJECT")]
    overrides = [i for i in firm if i["cab_decision"] != i["recommendation"]]

    return {
        "decided": len(decided),
        "pending": len(items) - len(decided),
        "demo_decisions": sum(1 for i in decided if i.get("cab_decided_by") == DEMO_USER),
        "firm_recommendations_decided": len(firm),
        "overrides": len(overrides),
        "override_rate": round(len(overrides) / len(firm), 3) if firm else None,
        "matrix": matrix,
    }


def outcome_report(items: list) -> dict:
    """Recorded real outcomes against what ChangeGuard recommended."""

    recorded = [i for i in items if i.get("actual_outcome")]

    def summary(group):
        bad = sum(1 for i in group if i["actual_outcome"] in BAD_OUTCOMES)
        return {"n": len(group), "bad": bad, "bad_rate": round(bad / len(group), 3) if group else None}

    approved = [i for i in recorded if i.get("recommendation") == "APPROVE"]
    flagged = [i for i in recorded if i.get("recommendation") in ("REVIEW", "REJECT")]

    return {
        "recorded": len(recorded),
        "real": sum(1 for i in recorded if i.get("outcome_recorded_by") != DEMO_USER),
        "demo": sum(1 for i in recorded if i.get("outcome_recorded_by") == DEMO_USER),
        "ai_approved": summary(approved),
        "ai_flagged": summary(flagged),
        "by_recommendation": {
            v: dict(Counter(i["actual_outcome"] for i in recorded if i.get("recommendation") == v))
            for v in VERDICTS
        },
    }


def screening_report(items: list) -> dict:
    statuses = Counter(
        ((i.get("details") or {}).get("prompt_guard") or {}).get("status", "not_recorded")
        for i in items
    )
    return {
        "screened": statuses["clean"] + statuses["flagged"],
        "clean": statuses["clean"],
        "flagged": statuses["flagged"],
        "unavailable": statuses["unavailable"],
        "not_screened": statuses["not_configured"] + statuses["not_recorded"],
    }


def load_retrain_history() -> list:
    if not RETRAIN_HISTORY_PATH.exists():
        return []
    return json.loads(RETRAIN_HISTORY_PATH.read_text(encoding="utf-8"))


def model_summary() -> dict:
    if not METRICS_PATH.exists():
        return {}
    models = json.loads(METRICS_PATH.read_text(encoding="utf-8")).get("models", {})
    return {
        k: {"name": m.get("name"), "trained_at": m.get("trained_at"), "roc_auc": m.get("roc_auc"),
            "feedback_rows": m.get("feedback_rows", 0)}
        for k, m in models.items()
    }


def monitoring_report(items: list) -> dict:
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "volume": volume_report(items),
        "cab": cab_report(items),
        "outcomes": outcome_report(items),
        "drift": drift_report(items, load_reference()),
        "screening": screening_report(items),
        "models": model_summary(),
        "retraining": list(reversed(load_retrain_history()))[:10],
    }
