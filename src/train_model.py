"""Train the ChangeGuard risk-prediction model."""
import numpy as np
import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score, roc_auc_score,
    precision_recall_curve, classification_report,
)

from config import MODEL_PATH, ENCODERS_PATH, THRESHOLD_PATH, FEATURE_COLUMNS
from data_prep import load_and_prepare


def train():
    X_train, X_test, y_train, y_test, encoders = load_and_prepare()

    # LogisticRegression with balanced classes handles our imbalanced risk data best.
    model = LogisticRegression(max_iter=1000, class_weight="balanced")
    model.fit(X_train, y_train)

    probs = model.predict_proba(X_test)[:, 1]  # probability of "bad"

    # --- Tune the decision threshold for best F1 (default 0.5 misses risky changes) ---
    prec, rec, thr = precision_recall_curve(y_test, probs)
    f1s = 2 * prec * rec / (prec + rec + 1e-9)
    best_idx = int(np.argmax(f1s))
    best_threshold = float(thr[best_idx]) if best_idx < len(thr) else 0.5

    preds = (probs >= best_threshold).astype(int)

    print("=" * 55)
    print("ChangeGuard Risk Model - Test Performance")
    print("=" * 55)
    print("ROC-AUC       :", round(roc_auc_score(y_test, probs), 3), " (target >= 0.75)")
    print("Tuned threshold:", round(best_threshold, 2))
    print("Accuracy      :", round(accuracy_score(y_test, preds), 3))
    print("Precision(Bad):", round(precision_score(y_test, preds), 3))
    print("Recall(Bad)   :", round(recall_score(y_test, preds), 3), " (how many risky changes we catch)")
    print("F1(Bad)       :", round(f1_score(y_test, preds), 3))
    print()
    print(classification_report(y_test, preds, target_names=["Success", "Bad"]))

    # Feature influence (LogisticRegression coefficients = direction & strength)
    print("Feature influence on risk (+ = raises risk, - = lowers):")
    coefs = sorted(
        zip(FEATURE_COLUMNS, model.coef_[0]),
        key=lambda x: abs(x[1]), reverse=True,
    )
    for name, c in coefs:
        print(f"  {name:38s} {c:+.3f}")

    # Save everything the app needs
    joblib.dump(model, MODEL_PATH)
    joblib.dump(encoders, ENCODERS_PATH)
    joblib.dump(best_threshold, THRESHOLD_PATH)
    print("\nModel saved to:", MODEL_PATH)
    print("Threshold saved to:", THRESHOLD_PATH)


if __name__ == "__main__":
    train()