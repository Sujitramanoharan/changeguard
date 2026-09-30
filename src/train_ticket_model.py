"""Train the change-ticket risk model on real Rabobank ITIL records.

    python scripts/download_datasets.py
    python src/train_ticket_model.py

Time-based evaluation: the model is trained on the oldest 80% of changes
and evaluated on the newest 20%, the way it would be used in practice.
"""

import json
from datetime import datetime, timezone

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)

import similarity
import ticket_risk as tr
from config import (
    BPIC_CHANGE_CSV,
    BPIC_INCIDENT_CSV,
    METRICS_PATH,
    MODEL_VERSION,
    TICKET_INDEX_PATH,
    TICKET_MODEL_PATH,
    TICKET_STATS_PATH,
)


def update_metrics(key: str, metrics: dict) -> None:
    """Merge one model's metrics into models/metrics.json."""

    data = {}

    if METRICS_PATH.exists():
        try:
            data = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}

    if "models" not in data:
        data = {"models": {}}

    data["model_version"] = MODEL_VERSION
    data["models"][key] = metrics
    METRICS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def train():
    print("Building training table from BPIC 2014 ...")
    df = tr.build_training_table(BPIC_CHANGE_CSV, BPIC_INCIDENT_CSV)

    cut = int(len(df) * 0.8)

    # Change type -> its historical risk rate, learned from the training
    # period only (smoothed towards the base rate for rare types).
    train_part = df.iloc[:cut]
    prior = float(train_part.risky.mean())
    agg = train_part.groupby("change_family").risky.agg(["sum", "size"])
    family_rates = {
        str(k): round(float((v["sum"] + prior * 50) / (v["size"] + 50)), 4)
        for k, v in agg.iterrows()
    }
    df["change_family_rate"] = df.change_family.map(family_rates).fillna(prior)

    for col in tr.CATEGORICAL:
        df[col] = df[col].astype("category")

    categories = {col: list(df[col].cat.categories) for col in tr.CATEGORICAL}

    train_df, test_df = df.iloc[:cut], df.iloc[cut:]

    print(f"Rows: {len(df)} | train {len(train_df)} | test {len(test_df)}")
    print(f"Risky rate: train {train_df.risky.mean():.3f} | test {test_df.risky.mean():.3f}")

    model = lgb.LGBMClassifier(
        n_estimators=300,
        learning_rate=0.05,
        num_leaves=31,
        min_child_samples=40,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        monotone_constraints=tr.MONOTONE_CONSTRAINTS,
        monotone_constraints_method="advanced",
        random_state=42,
        verbose=-1,
    )
    model.fit(train_df[tr.FEATURES], train_df.risky)

    probs = model.predict_proba(test_df[tr.FEATURES])[:, 1]
    y = test_df.risky.values
    base_rate = float(train_df.risky.mean())

    # Operating point: flag the riskiest 10% of changes.
    cutoff = float(np.quantile(probs, 0.9))
    flags = (probs >= cutoff).astype(int)

    manual_rating = test_df.risk_classification.map(
        {"Minor Change": 0, "Business Change": 1, "Major Business Change": 2}
    ).astype(float)

    metrics = {
        "name": "Change-ticket risk model",
        "dataset": "BPI Challenge 2014 - Rabobank Group ICT (real ITIL change & incident records)",
        "label": "Incidents on the affected system rose in the 7 days after the change vs. the 7 days before",
        "model_type": "LightGBM (gradient-boosted trees, monotonic constraints)",
        "trained_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "split": "time-based: oldest 80% train, newest 20% test",
        "train_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
        "test_period": f"{test_df.start.min():%Y-%m-%d} to {test_df.start.max():%Y-%m-%d}",
        "test_positive_rate": round(float(y.mean()), 3),
        "roc_auc": round(float(roc_auc_score(y, probs)), 3),
        "pr_auc": round(float(average_precision_score(y, probs)), 3),
        "brier_score": round(float(brier_score_loss(y, probs)), 4),
        "top10_precision": round(float(precision_score(y, flags)), 3),
        "top10_recall": round(float(recall_score(y, flags)), 3),
        "baselines": {
            "Rabobank manual risk rating": round(float(roc_auc_score(y, manual_rating)), 3),
            "Recent incidents on the system only": round(
                float(roc_auc_score(y, test_df.incidents_30d)), 3),
        },
        "mean_predicted": round(float(probs.mean()), 4),
    }

    imp = pd.Series(model.booster_.feature_importance("gain"), index=tr.FEATURES)
    metrics["feature_importance"] = [
        {"feature": tr.FEATURE_LABELS[f], "share": round(float(v), 3)}
        for f, v in (imp / imp.sum()).sort_values(ascending=False).items()
    ]

    print(json.dumps({k: v for k, v in metrics.items() if k != "feature_importance"}, indent=2))

    # ---------------------------------------------------------------
    # Similar-change index over ALL real changes (their outcomes known)
    # ---------------------------------------------------------------
    encoder = similarity.make_encoder(tr.CATEGORICAL, tr.NUMERIC)
    encoder.fit(df[tr.FEATURES])
    similarity.build_index(encoder, df[tr.FEATURES], TICKET_INDEX_PATH)

    meta = [
        {
            "change_id": r.change_id,
            "system": f"{r.ci_subtype} ({r.ci_type})",
            "change_type": r.change_family,
            "risk_classification": r.risk_classification,
            "date": f"{r.start:%Y-%m-%d}",
            "incidents_before_7d": int(r.incidents_before_7d),
            "incidents_after_7d": int(r.incidents_after_7d),
            "outcome": "Incidents increased" if r.risky else "No increase",
            "bad": bool(r.risky),
        }
        for r in df.itertuples()
    ]

    joblib.dump(
        {
            "model": model,
            "categories": categories,
            "family_rates": family_rates,
            "base_rate": round(base_rate, 4),
            "encoder": encoder,
            "meta": meta,
        },
        TICKET_MODEL_PATH,
        compress=3,
    )

    # ---------------------------------------------------------------
    # Form options + historical rates for the evidence tools
    # ---------------------------------------------------------------
    # Plain strings, so value_counts() lists only subtypes that really
    # occur under each type (categoricals would list every category).
    plain = df[["ci_type", "ci_subtype"]].astype(str)
    subtypes = {
        ci_type: group["ci_subtype"].value_counts().index.tolist()
        for ci_type, group in plain.groupby("ci_type")
    }

    def rate_table(col):
        g = df.groupby(col, observed=True)["risky"].agg(["mean", "size"])
        return {str(k): {"rate": round(float(v["mean"]), 4), "n": int(v["size"])}
                for k, v in g.iterrows()}

    stats = {
        "base_rate": round(base_rate, 4),
        "options": {
            "ci_type": plain.ci_type.value_counts().index.tolist(),
            "ci_subtype_by_type": {str(k): [str(x) for x in v] for k, v in subtypes.items()},
            "change_family": df.change_family.astype(str).value_counts().index.tolist(),
            "risk_classification": ["Minor Change", "Business Change", "Major Business Change"],
            "origin": ["Problem", "Incident"],
        },
        "rates": {
            "weekday": rate_table("weekday"),
            "hour": rate_table("hour"),
            "ci_subtype": rate_table("ci_subtype"),
            "risk_classification": rate_table("risk_classification"),
        },
    }
    TICKET_STATS_PATH.write_text(json.dumps(stats, indent=2), encoding="utf-8")

    update_metrics("ticket", metrics)

    print("Saved:", TICKET_MODEL_PATH.name, TICKET_INDEX_PATH.name, TICKET_STATS_PATH.name)


if __name__ == "__main__":
    train()
