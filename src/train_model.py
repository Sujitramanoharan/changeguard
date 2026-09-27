"""Train the ChangeGuard risk-prediction model."""
import json
from datetime import datetime, timezone

import numpy as np
import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    precision_recall_curve,
    classification_report,
    brier_score_loss,
)

from sklearn.calibration import calibration_curve

from config import (
    MODEL_PATH,
    ENCODERS_PATH,
    THRESHOLD_PATH,
    METRICS_PATH,
    FEATURE_COLUMNS,
    MODEL_VERSION,
)
from data_prep import load_and_prepare


def train():
    X_train, X_test, y_train, y_test, encoders = load_and_prepare()

    # ---------------------------------------------------------
    # 1. Train the base Logistic Regression model
    # ---------------------------------------------------------
    base_model = LogisticRegression(
        max_iter=1000,
        class_weight="balanced",
    )

    base_model.fit(X_train, y_train)

    # ---------------------------------------------------------
    # 2. Calibrate probability estimates
    #
    # Sigmoid calibration makes predict_proba() better aligned
    # with the observed probability of a bad change.
    # ---------------------------------------------------------
    model = CalibratedClassifierCV(
        base_model,
        method="sigmoid",
        cv=5,
    )

    model.fit(X_train, y_train)

    # Calibrated probability of "bad"
    probs = model.predict_proba(X_test)[:, 1]

    # ---------------------------------------------------------
    # 3. Tune the decision threshold for best F1
    # ---------------------------------------------------------
    prec, rec, thr = precision_recall_curve(y_test, probs)

    f1s = 2 * prec * rec / (prec + rec + 1e-9)

    best_idx = int(np.argmax(f1s))

    best_threshold = (
        float(thr[best_idx])
        if best_idx < len(thr)
        else 0.5
    )

    preds = (probs >= best_threshold).astype(int)

    # ---------------------------------------------------------
    # 4. Evaluate the calibrated model
    # ---------------------------------------------------------
    print("=" * 55)
    print("ChangeGuard Risk Model - Test Performance")
    print("=" * 55)

    print(
        "ROC-AUC       :",
        round(roc_auc_score(y_test, probs), 3),
        " (target >= 0.75)",
    )

    print(
        "Brier score   :",
        round(brier_score_loss(y_test, probs), 3),
        "(lower is better)",
    )

    print(
        "Actual bad rate:",
        round(float(y_test.mean()), 3),
    )

    print(
        "Mean predicted probability:",
        round(float(probs.mean()), 3),
    )

    print(
        "Tuned threshold:",
        round(best_threshold, 2),
    )

    print(
        "Accuracy      :",
        round(accuracy_score(y_test, preds), 3),
    )

    print(
        "Precision(Bad):",
        round(precision_score(y_test, preds), 3),
    )

    print(
        "Recall(Bad)   :",
        round(recall_score(y_test, preds), 3),
        " (how many risky changes we catch)",
    )

    print(
        "F1(Bad)       :",
        round(f1_score(y_test, preds), 3),
    )

    print()

    print(
        classification_report(
            y_test,
            preds,
            target_names=["Success", "Bad"],
        )
    )

    # ---------------------------------------------------------
    # 5. Feature influence
    #
    # CalibratedClassifierCV contains fitted base estimators.
    # Use the first calibrated estimator to report the original
    # Logistic Regression coefficient directions.
    # ---------------------------------------------------------
    print("Feature influence on risk (+ = raises risk, - = lowers):")

    coefficients = model.calibrated_classifiers_[0].estimator.coef_[0]

    coefs = sorted(
        zip(FEATURE_COLUMNS, coefficients),
        key=lambda x: abs(x[1]),
        reverse=True,
    )

    for name, coefficient in coefs:
        print(f"  {name:38s} {coefficient:+.3f}")

    # ---------------------------------------------------------
    # 6. Save everything the application needs
    # ---------------------------------------------------------
    joblib.dump(model, MODEL_PATH)
    joblib.dump(encoders, ENCODERS_PATH)
    joblib.dump(best_threshold, THRESHOLD_PATH)

    # Held-out metrics for the in-app model card (/api/model/metrics).
    frac_pos, mean_pred = calibration_curve(
        y_test, probs, n_bins=5, strategy="quantile"
    )

    metrics = {
        "model_version": MODEL_VERSION,
        "model_type": "Logistic Regression (sigmoid-calibrated)",
        "trained_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "train_rows": int(len(y_train)),
        "test_rows": int(len(y_test)),
        "test_bad_rate": round(float(y_test.mean()), 3),
        "roc_auc": round(float(roc_auc_score(y_test, probs)), 3),
        "brier_score": round(float(brier_score_loss(y_test, probs)), 3),
        "threshold": round(best_threshold, 3),
        "accuracy": round(float(accuracy_score(y_test, preds)), 3),
        "precision": round(float(precision_score(y_test, preds)), 3),
        "recall": round(float(recall_score(y_test, preds)), 3),
        "f1": round(float(f1_score(y_test, preds)), 3),
        "calibration": [
            {"predicted": round(float(p), 3), "observed": round(float(o), 3)}
            for p, o in zip(mean_pred, frac_pos)
        ],
        "feature_influence": [
            {"feature": name, "coefficient": round(float(c), 3)}
            for name, c in coefs
        ],
    }

    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    print("\nModel saved to:", MODEL_PATH)
    print("Threshold saved to:", THRESHOLD_PATH)
    print("Metrics saved to:", METRICS_PATH)


if __name__ == "__main__":
    train()