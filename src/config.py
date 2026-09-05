"""Central configuration for ChangeGuard."""
from pathlib import Path

# Project paths
ROOT = Path(__file__).parent.parent
DATA_PATH = ROOT / "data" / "changeguard_dataset.csv"
MODELS_DIR = ROOT / "models"
MODELS_DIR.mkdir(exist_ok=True)

MODEL_PATH = MODELS_DIR / "risk_model.pkl"
ENCODERS_PATH = MODELS_DIR / "encoders.pkl"
THRESHOLD_PATH = MODELS_DIR / "threshold.pkl"

# The ONLY features allowed as model inputs (features 2-13).
# outcome / true_risk_probability / risk_level are TARGETS - never inputs (no leakage).
FEATURE_COLUMNS = [
    "system",
    "change_type",
    "change_size",
    "requester_team",
    "requested_window",
    "rollback_plan_exists",
    "rollback_plan_tested",
    "similar_past_changes_count",
    "similar_past_changes_failure_rate",
    "system_incidents_last_90_days",
    "schedule_conflict",
]

# Which columns are text/categorical (need encoding) vs numeric
CATEGORICAL_COLUMNS = [
    "system", "change_type", "change_size", "requester_team",
    "requested_window", "rollback_plan_exists", "rollback_plan_tested",
    "schedule_conflict",
]
NUMERIC_COLUMNS = [
    "similar_past_changes_count",
    "similar_past_changes_failure_rate",
    "system_incidents_last_90_days",
]

# Target: we predict whether a change will be "bad" (Failed or Caused-Incident)
TARGET_COLUMN = "outcome"

# FAISS retrieval paths
FAISS_INDEX_PATH = MODELS_DIR / "faiss.index"
FAISS_META_PATH = MODELS_DIR / "faiss_meta.pkl"
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"