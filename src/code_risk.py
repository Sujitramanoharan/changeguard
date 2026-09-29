"""Code-change risk model (trained on real ApacheJIT commits).

Dataset: ApacheJIT (Keshavarz & Nagappan, MSR 2022) - 106,674 commits
from 15 Apache projects, each labelled bug-inducing or clean using the
SZZ algorithm over real Jira bug reports. CC-BY-4.0.

Features are the standard just-in-time defect prediction change
metrics (Kamei et al.) that can be computed from a single commit's diff,
so the live app computes them from the GitHub API exactly as the
dataset defines them (see metrics_from_files).

ApacheJIT's "fix" flag is deliberately NOT used: in the dataset it means
"linked to a Jira bug report", which a live GitHub commit cannot
reproduce (guessing it from words like "Fixed #123" fires on almost
every Django commit, features included). Using it would raise offline
AUC from 0.80 to 0.86 while making live predictions wrong.
"""

import math
import posixpath

import joblib
import numpy as np
import pandas as pd

from config import CODE_MODEL_PATH
from ticket_risk import risk_summary


FEATURES = ["la", "ld", "nf", "nd", "ns", "ent"]

FEATURE_LABELS = {
    "la": "Lines added",
    "ld": "Lines deleted",
    "nf": "Files changed",
    "nd": "Directories touched",
    "ns": "Top-level modules touched",
    "ent": "Change spread (entropy)",
}


def metrics_from_files(files: list) -> dict:
    """Compute the ApacheJIT change metrics from a GitHub file list.

    files: GitHub API entries with filename / additions / deletions.
    """

    paths = [f["filename"] for f in files]
    added = [int(f.get("additions", 0) or 0) for f in files]
    deleted = [int(f.get("deletions", 0) or 0) for f in files]

    touched = [a + d for a, d in zip(added, deleted)]
    total = sum(touched)

    # Entropy: how evenly the modified lines are spread across files.
    ent = 0.0
    if total > 0:
        for t in touched:
            if t > 0:
                p = t / total
                ent -= p * math.log2(p)

    return {
        "la": sum(added),
        "ld": sum(deleted),
        "nf": len(paths),
        "nd": len({posixpath.dirname(p) for p in paths}),
        "ns": len({p.split("/")[0] if "/" in p else "" for p in paths}),
        "ent": round(ent, 4),
    }


_bundle = None


def load():
    global _bundle

    if _bundle is None:
        _bundle = joblib.load(CODE_MODEL_PATH)

    return _bundle


def to_frame(metrics: dict) -> pd.DataFrame:
    return pd.DataFrame([{f: float(metrics.get(f, 0) or 0) for f in FEATURES}])


def describe_value(feature: str, value) -> str:
    if feature == "ent":
        return f"{float(value):.2f}"
    return f"{int(value):,}"


def predict(metrics: dict) -> dict:
    """Bug-introduction probability and top contributing factors."""

    b = load()
    X = to_frame(metrics)

    prob = float(b["model"].predict_proba(X)[0, 1])
    contrib = b["model"].booster_.predict(X, pred_contrib=True)[0][:-1]

    order = np.argsort(-np.abs(contrib))[:5]

    return {
        "model": "code",
        **risk_summary(prob, b["base_rate"]),
        "factors": [
            {
                "feature": FEATURES[k],
                "label": FEATURE_LABELS[FEATURES[k]],
                "value": describe_value(FEATURES[k], metrics.get(FEATURES[k], 0)),
                "impact": round(float(contrib[k]), 3),
                "direction": "raises risk" if contrib[k] > 0 else "lowers risk",
            }
            for k in order
        ],
    }
