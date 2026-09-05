"""Run the trained risk model on a single new change."""
import joblib
import pandas as pd
from config import (MODEL_PATH, ENCODERS_PATH, THRESHOLD_PATH,
                    FEATURE_COLUMNS, CATEGORICAL_COLUMNS)

_model = joblib.load(MODEL_PATH)
_encoders = joblib.load(ENCODERS_PATH)
_threshold = joblib.load(THRESHOLD_PATH)


def predict_risk(change: dict) -> dict:
    """Given a change (dict of feature values), return risk probability + label."""
    row = {col: change.get(col) for col in FEATURE_COLUMNS}
    X = pd.DataFrame([row])

    # Encode categoricals using the SAME encoders from training
    for col in CATEGORICAL_COLUMNS:
        le = _encoders[col]
        val = str(X.at[0, col])
        # handle unseen categories gracefully
        if val in le.classes_:
            X[col] = le.transform([val])
        else:
            X[col] = 0
    X = X[FEATURE_COLUMNS]

    prob = float(_model.predict_proba(X)[0, 1])
    is_risky = prob >= _threshold
    if prob < 0.33:
        level = "Low"
    elif prob < 0.66:
        level = "Medium"
    else:
        level = "High"
    return {
        "risk_probability": round(prob, 3),
        "risk_level": level,
        "model_flags_risky": bool(is_risky),
    }


if __name__ == "__main__":
    test = {
        "system": "Payments-Service", "change_type": "Database-Schema-Change",
        "change_size": "Large", "requester_team": "Backend",
        "requested_window": "Peak-Hours", "rollback_plan_exists": "No",
        "rollback_plan_tested": "None", "similar_past_changes_count": 5,
        "similar_past_changes_failure_rate": 0.4,
        "system_incidents_last_90_days": 3, "schedule_conflict": "Yes",
    }
    print(predict_risk(test))