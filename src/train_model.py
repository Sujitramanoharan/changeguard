"""Train the ChangeGuard risk-prediction model."""
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

from config import MODEL_PATH, ENCODERS_PATH, THRESHOLD_PATH, FEATURE_COLUMNS
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

    print("\nModel saved to:", MODEL_PATH)
    print("Threshold saved to:", THRESHOLD_PATH)


if __name__ == "__main__":
    train()