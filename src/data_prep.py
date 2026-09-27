"""Load and prepare the ChangeGuard dataset for training."""
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

from config import DATA_PATH, FEATURE_COLUMNS, CATEGORICAL_COLUMNS, TARGET_COLUMN


def derive_history_features(df: pd.DataFrame) -> pd.DataFrame:
    """Recompute the three history features exactly as inference does.

    The raw CSV columns for these features are synthetic values on a
    different scale (e.g. similar-change counts up to ~60) than what the
    live app can derive (at most k FAISS matches). Training on the raw
    columns would feed the model out-of-distribution inputs at runtime.
    So each row gets the same features src/context.py computes for a new
    change - leave-one-out, so a row never sees its own outcome.
    """

    import faiss

    from build_index import change_to_text
    from context import summarize_similar_changes
    import retrieval

    meta_ids = [m["change_id"] for m in retrieval._meta]

    if meta_ids != df["change_id"].tolist():
        raise RuntimeError(
            "FAISS index is out of date with the dataset. "
            "Run src/build_index.py first."
        )

    texts = df.apply(change_to_text, axis=1).tolist()

    emb = retrieval._model.encode(
        texts,
        convert_to_numpy=True,
        batch_size=64,
    ).astype("float32")

    faiss.normalize_L2(emb)

    # One extra neighbour, because each row's nearest match is itself.
    scores, idxs = retrieval._index.search(emb, retrieval.DEFAULT_K + 1)

    df = df.copy()

    history = []

    for row_idx in range(len(df)):
        similar = [
            retrieval._meta[i]
            for score, i in zip(scores[row_idx], idxs[row_idx])
            if i != row_idx and score >= retrieval.MIN_SIMILARITY
        ][: retrieval.DEFAULT_K]

        history.append(summarize_similar_changes(similar))

    history_df = pd.DataFrame(history, index=df.index)

    df["similar_past_changes_count"] = history_df[
        "similar_past_changes_count"
    ]
    df["similar_past_changes_failure_rate"] = history_df[
        "similar_past_changes_failure_rate"
    ]

    # Inference uses the system's average incident count
    # (tools.get_incident_history); leave-one-out here.
    grp = df.groupby("system")["system_incidents_last_90_days"]
    sums = grp.transform("sum")
    counts = grp.transform("count")
    df["system_incidents_last_90_days"] = (
        (sums - df["system_incidents_last_90_days"]) / (counts - 1)
    ).round(2)

    return df


def load_and_prepare():
    df = pd.read_csv(DATA_PATH)

    # Fill blank rollback_plan_tested (blank = no plan exists) with "None"
    df["rollback_plan_tested"] = df["rollback_plan_tested"].fillna("None")

    df = derive_history_features(df)

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