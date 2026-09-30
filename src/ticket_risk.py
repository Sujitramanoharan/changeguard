"""Change-ticket risk model (trained on real Rabobank ITIL records).

Dataset: BPI Challenge 2014 - Rabobank Group ICT change and incident
records exported from HP Service Manager (4TU.ResearchData).

Label: a change is "risky" when incidents on the affected configuration
item (CI) in the 7 days after the change exceed those in the 7 days
before it. Comparing after-vs-before controls for systems that always
have incidents.

This module is shared by training (src/train_ticket_model.py) and
inference, so the model always sees features computed the same way.
"""

import json
import re

import joblib
import numpy as np
import pandas as pd

from config import TICKET_MODEL_PATH, TICKET_STATS_PATH


# -------------------------------------------------------------------
# Feature definitions (the ONLY model inputs)
# -------------------------------------------------------------------

CATEGORICAL = [
    "ci_type",
    "ci_subtype",
    "origin",
]

NUMERIC = [
    # Change type as its historical risk rate (from the training period
    # only), so it can be constrained: an unconstrained categorical had
    # "Release Type" lowering risk, although releases were followed by
    # more incidents twice as often as standard changes.
    "change_family_rate",
    "risk_rank",
    "incidents_30d",
    "planned_hours",
    "downtime",
    "weekday",
    "hour",
    "systems_affected",
    "emergency",
    "cab_required",
]

FEATURES = CATEGORICAL + NUMERIC

RISK_RANK = {"Minor Change": 0, "Business Change": 1, "Major Business Change": 2}

# Domain knowledge the model must respect: these can only ever RAISE
# risk. In the real data each of them does (e.g. emergency changes were
# followed by more incidents 9.1% of the time vs 4.4%), but with only 88
# emergency changes an unconstrained model learned the opposite.
MONOTONE_INCREASING = {
    "change_family_rate", "risk_rank", "incidents_30d", "emergency", "cab_required", "downtime",
}
MONOTONE_CONSTRAINTS = [1 if f in MONOTONE_INCREASING else 0 for f in FEATURES]

FEATURE_LABELS = {
    "ci_type": "System type",
    "ci_subtype": "System subtype",
    "change_family_rate": "Change type",
    "risk_rank": "Risk classification",
    "origin": "Raised from",
    "incidents_30d": "Incidents on this system (last 30 days)",
    "planned_hours": "Planned duration (hours)",
    "downtime": "Scheduled downtime",
    "weekday": "Start day",
    "hour": "Start hour",
    "systems_affected": "Systems affected",
    "emergency": "Emergency change",
    "cab_required": "CAB approval required",
}

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def change_family(change_type: str) -> str:
    """'Standard Change Type 81' -> 'Standard Change Type'."""

    return re.sub(r"\s*\d+$", "", change_type or "")


# -------------------------------------------------------------------
# Training data (raw BPIC 2014 CSVs -> one row per change x CI)
# -------------------------------------------------------------------

def _dt(series):
    return pd.to_datetime(series, dayfirst=True, errors="coerce")


def build_training_table(change_csv, incident_csv) -> pd.DataFrame:
    """Join changes to incidents on the CI and derive features + label."""

    c = pd.read_csv(change_csv, sep=";", low_memory=False)
    i = pd.read_csv(incident_csv, sep=";", low_memory=False)
    i = i.loc[:, ~i.columns.str.startswith("Unnamed")]

    for col in ["Actual Start", "Actual End", "Planned Start", "Planned End",
                "Scheduled Downtime Start"]:
        c[col] = _dt(c[col])

    i["open"] = _dt(i["Open Time"])
    # The CI that caused the incident, falling back to the affected CI.
    i["ci"] = i["CI Name (CBy)"].fillna(i["CI Name (aff)"])
    by_ci = {ci: np.sort(g["open"].dropna().values) for ci, g in i.groupby("ci")}

    def count(ci, t0, t1):
        arr = by_ci.get(ci)
        if arr is None or pd.isna(t0) or pd.isna(t1):
            return 0
        return int(np.searchsorted(arr, np.datetime64(t1))
                   - np.searchsorted(arr, np.datetime64(t0)))

    # Keep changes whose 30-day history and 7-day follow-up both fall
    # inside the incident observation period.
    lo = i["open"].min() + pd.Timedelta(days=30)
    hi = i["open"].max() - pd.Timedelta(days=7)
    d = c[(c["Actual Start"] > lo) & (c["Actual End"] < hi)].copy()

    week = pd.Timedelta(days=7)
    ci = d["CI Name (aff)"]
    d["incidents_before_7d"] = [count(x, s - week, s) for x, s in zip(ci, d["Actual Start"])]
    d["incidents_after_7d"] = [count(x, e, e + week) for x, e in zip(ci, d["Actual End"])]
    d["risky"] = (d["incidents_after_7d"] > d["incidents_before_7d"]).astype(int)

    start = d["Planned Start"].fillna(d["Actual Start"])

    out = pd.DataFrame({
        "change_id": d["Change ID"],
        "ci_name": ci,
        "start": d["Actual Start"],
        "ci_type": d["CI Type (aff)"].fillna("no type"),
        "ci_subtype": d["CI Subtype (aff)"].fillna("Unknown"),
        "change_family": d["Change Type"].fillna("").str.replace(r"\s*\d+$", "", regex=True),
        "risk_classification": d["Risk Assessment"].fillna("Minor Change"),
        "risk_rank": d["Risk Assessment"].map(RISK_RANK).fillna(0).astype(int),
        "origin": d["Originated from"].fillna("Problem"),
        "incidents_30d": [count(x, s - pd.Timedelta(days=30), s)
                          for x, s in zip(ci, d["Actual Start"])],
        "planned_hours": ((d["Planned End"] - d["Planned Start"]).dt.total_seconds() / 3600)
        .clip(lower=0, upper=24 * 90),
        "downtime": d["Scheduled Downtime Start"].notna().astype(int),
        "weekday": start.dt.weekday,
        "hour": start.dt.hour,
        "systems_affected": d.groupby("Change ID")["CI Name (aff)"].transform("count"),
        "emergency": (d["Emergency Change"] == "Y").astype(int),
        "cab_required": (d["CAB-approval needed"] == "Y").astype(int),
        "incidents_before_7d": d["incidents_before_7d"],
        "incidents_after_7d": d["incidents_after_7d"],
        "risky": d["risky"],
    })

    return out.sort_values("start").reset_index(drop=True)


# -------------------------------------------------------------------
# Inference
# -------------------------------------------------------------------

_bundle = None


def load():
    """Load the trained model bundle once."""

    global _bundle

    if _bundle is None:
        _bundle = joblib.load(TICKET_MODEL_PATH)

    return _bundle


def load_stats() -> dict:
    """Form options and historical rates saved at training time."""

    return json.loads(TICKET_STATS_PATH.read_text(encoding="utf-8"))


def to_frame(ticket: dict, bundle: dict) -> pd.DataFrame:
    """Turn one ticket dict into a single-row model input."""

    row = {f: ticket.get(f) for f in FEATURES}
    row["risk_rank"] = RISK_RANK.get(ticket.get("risk_classification"), 0)
    row["change_family_rate"] = bundle["family_rates"].get(
        ticket.get("change_family"), bundle["base_rate"]
    )
    X = pd.DataFrame([row])

    for col in CATEGORICAL:
        X[col] = pd.Categorical(X[col], categories=bundle["categories"][col])

    for col in NUMERIC:
        X[col] = pd.to_numeric(X[col], errors="coerce").astype(float)

    return X


def predict(ticket: dict) -> dict:
    """Probability, relative risk and per-feature contributions for a ticket."""

    b = load()
    X = to_frame(ticket, b)

    prob = float(b["model"].predict_proba(X)[0, 1])

    # SHAP values from LightGBM's built-in TreeSHAP (log-odds space).
    contrib = b["model"].booster_.predict(X, pred_contrib=True)[0][:-1]

    return {
        "model": "ticket",
        **risk_summary(prob, b["base_rate"]),
        "factors": top_factors(ticket, contrib),
    }


def risk_summary(prob: float, base_rate: float) -> dict:
    """Express a probability relative to the average historical change.

    Real change outcomes are heavily skewed (most changes are safe), so
    "3x riskier than a typical change" is more meaningful to a reviewer
    than a raw probability. risk_index maps relative risk onto 0-1 for
    the risk policy: 0.5 means exactly average.
    """

    relative = prob / base_rate if base_rate else 0.0

    if relative >= 3:
        lvl = "High"
    elif relative >= 1:
        lvl = "Medium"
    else:
        lvl = "Low"

    return {
        "risk_probability": round(prob, 4),
        "base_rate": round(base_rate, 4),
        "relative_risk": round(relative, 2),
        "risk_index": round(relative / (relative + 1), 3),
        "risk_level": lvl,
    }


def describe_value(feature: str, value) -> str:
    if feature in ("risk_rank", "change_family_rate"):
        return str(value)
    if feature == "weekday" and value is not None:
        try:
            return WEEKDAYS[int(value)]
        except (ValueError, IndexError):
            return str(value)
    if feature == "hour" and value is not None:
        return f"{int(value):02d}:00"
    if feature in ("downtime", "emergency", "cab_required"):
        return "Yes" if int(value or 0) else "No"
    if feature == "planned_hours" and value is not None:
        return f"{float(value):g} h"
    return str(value)


def top_factors(ticket: dict, contrib, n: int = 5) -> list:
    """The features that pushed this prediction up or down the most."""

    order = np.argsort(-np.abs(contrib))[:n]

    return [
        {
            "feature": FEATURES[k],
            "label": FEATURE_LABELS[FEATURES[k]],
            "value": describe_value(
                FEATURES[k],
                {"risk_rank": ticket.get("risk_classification"),
                 "change_family_rate": ticket.get("change_family")}.get(
                    FEATURES[k], ticket.get(FEATURES[k])
                ),
            ),
            "impact": round(float(contrib[k]), 3),
            "direction": "raises risk" if contrib[k] > 0 else "lowers risk",
        }
        for k in order
    ]
