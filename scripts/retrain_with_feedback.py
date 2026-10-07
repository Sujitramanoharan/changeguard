"""Close the feedback loop: retrain on recorded real outcomes, behind a gate.

When a CAB-approved change is implemented, its real outcome (Success,
Failed, Caused-Incident) is recorded in ChangeGuard. This script turns
those outcomes into extra training rows and fits a candidate model:

    python scripts/retrain_with_feedback.py              # both models
    python scripts/retrain_with_feedback.py --model ticket --dry-run

Gate - the candidate replaces the shipped model only if:
  1. it learned from at least one real recorded outcome (demo-seeded
     outcomes are never used: they are made up), and
  2. its ROC-AUC on the same held-out test set - the newest 20% of the
     real public data, which feedback never enters - is not lower than
     the shipped model's.

The previous model is archived to models/archive/ (rollback = copy back),
and every run is appended to models/retrain_history.json, which the
Monitoring page shows. Runs offline where the raw datasets are; commit the
updated models/ to deploy.

Label mapping: Failed or Caused-Incident -> risky (1), Success -> 0. The
ticket model's training label is "incidents rose after the change"; a
recorded failure is the organisation's own, stronger version of that.
"""

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import average_precision_score, roc_auc_score  # noqa: E402

import code_risk as cr  # noqa: E402
import monitoring  # noqa: E402
import ticket_risk as tr  # noqa: E402
import train_code_model  # noqa: E402
import train_ticket_model  # noqa: E402
from agent import prepare_ticket  # noqa: E402
from backend.database import describe_database, get_all_assessments  # noqa: E402
from config import CODE_MODEL_PATH, METRICS_PATH, MODELS_DIR, TICKET_MODEL_PATH  # noqa: E402

ARCHIVE_DIR = MODELS_DIR / "archive"


def feedback_items(kind: str) -> tuple[list, int]:
    """Real recorded outcomes for one model; also how many demo ones were skipped."""

    items = [
        i for i in get_all_assessments()
        if i.get("actual_outcome") and (i.get("assessment_type") or "ticket") == kind
    ]
    real = [i for i in items if i.get("outcome_recorded_by") != monitoring.DEMO_USER]
    return real, len(items) - len(real)


def label(item: dict) -> int:
    return int(item["actual_outcome"] in monitoring.BAD_OUTCOMES)


# -------------------------------------------------------------------
# Per-model data: (train X, train y, test X, test y, feedback X, feedback y)
# -------------------------------------------------------------------

def ticket_data(bundle: dict, items: list):
    df, cut, _, _ = train_ticket_model.prepare_table()
    train_df, test_df = df.iloc[:cut], df.iloc[cut:]

    rows, labels = [], []
    for item in items:
        change = (item.get("details") or {}).get("change")
        if change and change.get("planned_start"):
            rows.append(tr.to_frame(prepare_ticket(change), bundle))
            labels.append(label(item))
    fb_X = pd.concat(rows, ignore_index=True)[tr.FEATURES] if rows else train_df[tr.FEATURES].iloc[:0]
    fb_y = pd.Series(labels, dtype=int)

    return (train_df[tr.FEATURES], train_df.risky, test_df[tr.FEATURES], test_df.risky.values,
            fb_X, fb_y)


def code_data(bundle: dict, items: list):
    df = train_code_model.load_table()
    X = df[cr.FEATURES].astype(float)
    cut = int(len(df) * 0.8)

    metrics = [((i.get("details") or {}).get("code_metrics"), label(i)) for i in items]
    metrics = [(m, y) for m, y in metrics if m]
    fb_X = (pd.concat([cr.to_frame(m) for m, _ in metrics], ignore_index=True)
            if metrics else X.iloc[:0])
    fb_y = pd.Series([y for _, y in metrics], dtype=int)

    return X.iloc[:cut], df.y.iloc[:cut], X.iloc[cut:], df.y.iloc[cut:].values, fb_X, fb_y


MODELS = {
    "ticket": {"path": TICKET_MODEL_PATH, "data": ticket_data, "new": train_ticket_model.new_model},
    "code": {"path": CODE_MODEL_PATH, "data": code_data, "new": train_code_model.new_model},
}


# -------------------------------------------------------------------
# Retrain one model behind the gate
# -------------------------------------------------------------------

def retrain(kind: str, weight: float, dry_run: bool, force: bool) -> dict:
    spec = MODELS[kind]
    bundle = joblib.load(spec["path"])
    items, demo_skipped = feedback_items(kind)

    print(f"\n[{kind}] real recorded outcomes: {len(items)} (skipped {demo_skipped} demo-seeded)")

    entry = {
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "model": kind,
        "feedback_rows": len(items),
        "feedback_bad": sum(label(i) for i in items),
        "demo_skipped": demo_skipped,
        "weight": weight,
    }

    if not items and not force:
        entry.update(decision="skipped", reason="No real outcomes recorded since training - nothing new to learn.")
        print("  ", entry["reason"])
        return entry

    X_tr, y_tr, X_te, y_te, fb_X, fb_y = spec["data"](bundle, items)

    current = bundle["model"].predict_proba(X_te)[:, 1]

    X_fit = pd.concat([X_tr, fb_X], ignore_index=True)
    y_fit = pd.concat([pd.Series(np.asarray(y_tr)), fb_y], ignore_index=True)
    w_fit = np.concatenate([np.ones(len(X_tr)), np.full(len(fb_X), weight)])
    if kind == "ticket":
        for col in tr.CATEGORICAL:
            X_fit[col] = pd.Categorical(X_fit[col], categories=bundle["categories"][col])

    candidate = spec["new"]().fit(X_fit, y_fit, sample_weight=w_fit)
    cand = candidate.predict_proba(X_te)[:, 1]

    entry.update(
        test_rows=int(len(y_te)),
        current_roc_auc=round(float(roc_auc_score(y_te, current)), 4),
        candidate_roc_auc=round(float(roc_auc_score(y_te, cand)), 4),
        current_pr_auc=round(float(average_precision_score(y_te, current)), 4),
        candidate_pr_auc=round(float(average_precision_score(y_te, cand)), 4),
    )
    print(f"   held-out ROC-AUC  current {entry['current_roc_auc']}  candidate {entry['candidate_roc_auc']}"
          f"  ({entry['test_rows']} newest real rows)")

    if not items:
        entry.update(decision="kept", reason="Check run without feedback (--force): the candidate only "
                                             "reproduces the shipped model, so it is not promoted.")
    elif entry["candidate_roc_auc"] < entry["current_roc_auc"]:
        entry.update(decision="kept", reason="Candidate is worse on the held-out test set.")
    elif dry_run:
        entry.update(decision="would_promote", reason="Passed the gate (dry run - nothing saved).")
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        ARCHIVE_DIR.mkdir(exist_ok=True)
        archived = ARCHIVE_DIR / f"{stamp}-{spec['path'].name}"
        shutil.copy2(spec["path"], archived)

        bundle["model"] = candidate
        bundle["feedback"] = {"rows": len(items), "weight": weight, "retrained_at": entry["at"]}
        joblib.dump(bundle, spec["path"], compress=3)

        metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
        m = metrics["models"][kind]
        m.update(roc_auc=round(entry["candidate_roc_auc"], 3), pr_auc=round(entry["candidate_pr_auc"], 3),
                 retrained_at=entry["at"], feedback_rows=len(items))
        METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

        entry.update(decision="promoted", reason="Not worse on the held-out test set; previous model archived.",
                     archived=f"models/archive/{archived.name}")

    print(f"   decision: {entry['decision']} - {entry['reason']}")
    return entry


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", choices=["ticket", "code", "both"], default="both")
    parser.add_argument("--weight", type=float, default=5.0,
                        help="training weight of each recorded outcome relative to one historical row")
    parser.add_argument("--dry-run", action="store_true", help="evaluate the gate but never replace a model")
    parser.add_argument("--force", action="store_true",
                        help="run the comparison even with no real outcomes (a reproducibility check)")
    args = parser.parse_args()

    print("Feedback from:", describe_database())
    kinds = ["ticket", "code"] if args.model == "both" else [args.model]
    entries = [retrain(k, args.weight, args.dry_run, args.force) for k in kinds]

    if not args.dry_run:
        history = monitoring.load_retrain_history() + entries
        monitoring.RETRAIN_HISTORY_PATH.write_text(json.dumps(history, indent=2), encoding="utf-8")
        print("\nLogged to", monitoring.RETRAIN_HISTORY_PATH.relative_to(ROOT))


if __name__ == "__main__":
    main()
