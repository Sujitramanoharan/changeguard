"""Load and prepare the ChangeGuard dataset for training."""
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

from config import DATA_PATH, FEATURE_COLUMNS, CATEGORICAL_COLUMNS, TARGET_COLUMN


def load_and_prepare():
    df = pd.read_csv(DATA_PATH)

    # Fill blank rollback_plan_tested (blank = no plan exists) with "None"
    df["rollback_plan_tested"] = df["rollback_plan_tested"].fillna("None")

    # Build the target: 1 = bad outcome (Failed/Caused-Incident), 0 = Success
    df["target"] = df[TARGET_COLUMN].apply(
        lambda x: 0 if x == "Success" else 1
    )

    # Inputs = only the allowed feature columns (no leakage)
    X = df[FEATURE_COLUMNS].copy()
    y = df["target"]

    # Split before fitting encoders.
    # This prevents preprocessing from learning categories from the test set.
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )

    # Fit encoders ONLY on training data.
    # Then use the same encoders to transform the test data.
    encoders = {}

    for col in CATEGORICAL_COLUMNS:
        le = LabelEncoder()

        X_train[col] = le.fit_transform(X_train[col].astype(str))

        # Handle a category that appears in the test set but not in training.
        known_classes = set(le.classes_)

        X_test[col] = X_test[col].astype(str).apply(
            lambda value: value if value in known_classes else le.classes_[0]
        )

        X_test[col] = le.transform(X_test[col])

        encoders[col] = le

    return X_train, X_test, y_train, y_test, encoders


if __name__ == "__main__":
    X_train, X_test, y_train, y_test, encoders = load_and_prepare()

    print("Data prepared successfully.")
    print("Training rows:", len(X_train), "| Test rows:", len(X_test))
    print("Features used:", list(X_train.columns))
    print("Bad-outcome rate (train):", round(y_train.mean(), 3))