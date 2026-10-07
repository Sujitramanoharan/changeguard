"""Train the code-change risk model on real ApacheJIT commits.

    python scripts/download_datasets.py
    python src/train_code_model.py

Two honest evaluations are reported:
  * time-based: train on the oldest 80% of commits, test on the newest 20%
  * unseen projects: train without 4 projects, test only on them - the
    situation when a user connects a repository the model never saw.
"""

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

import code_risk as cr
import similarity
from config import APACHEJIT_CSV, CODE_INDEX_PATH, CODE_MODEL_PATH
from train_ticket_model import update_metrics


HELD_OUT_PROJECTS = ["apache/kafka", "apache/spark", "apache/zookeeper", "apache/zeppelin"]

# ApacheJIT merged sub-repositories that live inside apache/hadoop today.
REPO_OF = {"apache/hadoop-hdfs": "apache/hadoop", "apache/hadoop-mapreduce": "apache/hadoop"}


def new_model():
    return lgb.LGBMClassifier(
        n_estimators=400,
        learning_rate=0.05,
        num_leaves=31,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        random_state=42,
        verbose=-1,
    )


def load_table():
    """ApacheJIT sorted by date, with the label column (shared with retraining)."""

    df = pd.read_csv(APACHEJIT_CSV).sort_values("author_date").reset_index(drop=True)
    df["y"] = df["buggy"].astype(int)
    return df


def train():
    df = load_table()
    X = df[cr.FEATURES].astype(float)

    # ---- Unseen-project evaluation ----
    held = df["project"].isin(HELD_OUT_PROJECTS)
    m_proj = new_model().fit(X[~held], df.y[~held])
    p_proj = m_proj.predict_proba(X[held])[:, 1]
    unseen_auc = roc_auc_score(df.y[held], p_proj)

    # ---- Time-based evaluation (this is the shipped model) ----
    cut = int(len(df) * 0.8)
    tr_idx, te_idx = df.index[:cut], df.index[cut:]

    model = new_model().fit(X.loc[tr_idx], df.y[tr_idx])
    probs = model.predict_proba(X.loc[te_idx])[:, 1]
    y = df.y[te_idx].values
    base_rate = float(df.y[tr_idx].mean())

    cutoff = float(np.quantile(probs, 0.8))
    flags = (probs >= cutoff).astype(int)

    size_only = roc_auc_score(y, df.loc[te_idx, "la"] + df.loc[te_idx, "ld"])

    metrics = {
        "name": "Code-change risk model",
        "dataset": "ApacheJIT - 106,674 real commits from 15 Apache projects (CC-BY-4.0)",
        "label": "Commit later identified as bug-inducing (SZZ over real Jira bug reports)",
        "model_type": "LightGBM (gradient-boosted trees)",
        "trained_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "split": "time-based: oldest 80% train, newest 20% test",
        "train_rows": int(len(tr_idx)),
        "test_rows": int(len(te_idx)),
        "test_period": f"{df.loc[te_idx, 'year'].min()} to {df.loc[te_idx, 'year'].max()}",
        "test_positive_rate": round(float(y.mean()), 3),
        "roc_auc": round(float(roc_auc_score(y, probs)), 3),
        "pr_auc": round(float(average_precision_score(y, probs)), 3),
        "brier_score": round(float(brier_score_loss(y, probs)), 4),
        "top20_precision": round(float(precision_score(y, flags)), 3),
        "top20_recall": round(float(recall_score(y, flags)), 3),
        "unseen_projects_roc_auc": round(float(unseen_auc), 3),
        "unseen_projects": HELD_OUT_PROJECTS,
        "baselines": {"Change size alone (lines added + deleted)": round(float(size_only), 3)},
        "mean_predicted": round(float(probs.mean()), 4),
    }

    imp = pd.Series(model.booster_.feature_importance("gain"), index=cr.FEATURES)
    metrics["feature_importance"] = [
        {"feature": cr.FEATURE_LABELS[f], "share": round(float(v), 3)}
        for f, v in (imp / imp.sum()).sort_values(ascending=False).items()
    ]

    for k in ["roc_auc", "pr_auc", "unseen_projects_roc_auc", "top20_precision", "top20_recall",
              "test_positive_rate", "mean_predicted"]:
        print(f"{k:26s} {metrics[k]}")
    print("baseline size-only AUC    ", metrics["baselines"])

    # ---- Similar-commit index over all real commits ----
    encoder = similarity.make_encoder([], cr.FEATURES)
    encoder.fit(X)
    similarity.build_index(encoder, X, CODE_INDEX_PATH)

    meta = [
        {
            "change_id": r.commit_id[:10],
            "system": r.project,
            "change_type": f"+{r.la}/-{r.ld} lines, {r.nf} files",
            "date": str(r.year),
            "url": f"https://github.com/{REPO_OF.get(r.project, r.project)}/commit/{r.commit_id}",
            "outcome": "Introduced a bug" if r.buggy else "Clean",
            "bad": bool(r.buggy),
        }
        for r in df.itertuples()
    ]

    joblib.dump(
        {
            "model": model,
            "base_rate": round(base_rate, 4),
            "encoder": encoder,
            "meta": meta,
        },
        CODE_MODEL_PATH,
        compress=3,
    )

    update_metrics("code", metrics)
    print("Saved:", CODE_MODEL_PATH.name, CODE_INDEX_PATH.name)


if __name__ == "__main__":
    train()
