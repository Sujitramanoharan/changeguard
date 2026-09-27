"""Central configuration for ChangeGuard."""

import os
import socket
from pathlib import Path

from dotenv import load_dotenv


# -------------------------------------------------------------------
# Project paths
# -------------------------------------------------------------------

ROOT = Path(__file__).parent.parent

# Every module imports config first, so load .env here once.
load_dotenv(dotenv_path=ROOT / ".env")


# -------------------------------------------------------------------
# Network: optionally prefer IPv4
# -------------------------------------------------------------------
# Some corporate networks advertise IPv6 DNS records but do not route
# IPv6, so every outbound HTTPS call (Groq, GitHub) stalls ~40s before
# falling back to IPv4. CHANGEGUARD_PREFER_IPV4=true tries IPv4 first
# while keeping IPv6 as a fallback. Not needed on normal hosting.

if os.getenv("CHANGEGUARD_PREFER_IPV4", "").lower() in ("1", "true", "yes"):
    _original_getaddrinfo = socket.getaddrinfo

    def _ipv4_first_getaddrinfo(*args, **kwargs):
        results = _original_getaddrinfo(*args, **kwargs)
        return sorted(results, key=lambda r: r[0] != socket.AF_INET)

    socket.getaddrinfo = _ipv4_first_getaddrinfo

DATA_PATH = ROOT / "data" / "changeguard_dataset.csv"

MODELS_DIR = ROOT / "models"
MODELS_DIR.mkdir(exist_ok=True)


# -------------------------------------------------------------------
# Trained ML model artifacts
# -------------------------------------------------------------------

MODEL_PATH = MODELS_DIR / "risk_model.pkl"
ENCODERS_PATH = MODELS_DIR / "encoders.pkl"
THRESHOLD_PATH = MODELS_DIR / "threshold.pkl"
METRICS_PATH = MODELS_DIR / "metrics.json"


# -------------------------------------------------------------------
# Model features
# -------------------------------------------------------------------

# The ONLY features allowed as model inputs.
#
# outcome / true_risk_probability / risk_level are targets.
# They must never be used as model inputs because that would cause
# target leakage.

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


# Text/categorical features that require encoding.
CATEGORICAL_COLUMNS = [
    "system",
    "change_type",
    "change_size",
    "requester_team",
    "requested_window",
    "rollback_plan_exists",
    "rollback_plan_tested",
    "schedule_conflict",
]


# Numeric features.
NUMERIC_COLUMNS = [
    "similar_past_changes_count",
    "similar_past_changes_failure_rate",
    "system_incidents_last_90_days",
]


# Target: predict whether a change will be bad
# (Failed or Caused-Incident).
TARGET_COLUMN = "outcome"


# -------------------------------------------------------------------
# FAISS retrieval artifacts
# -------------------------------------------------------------------

FAISS_INDEX_PATH = MODELS_DIR / "faiss.index"
FAISS_META_PATH = MODELS_DIR / "faiss_meta.pkl"


# -------------------------------------------------------------------
# Embedding model
# -------------------------------------------------------------------

# Model name used when downloading/building the embedding model.
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"

# Local copy of the embedding model.
#
# This directory is packaged into the production Docker image so
# ChangeGuard does not need to download the model from Hugging Face
# during deployment or startup.
EMBED_MODEL_PATH = MODELS_DIR / EMBED_MODEL_NAME


# -------------------------------------------------------------------
# Audit / version metadata
# -------------------------------------------------------------------

MODEL_VERSION = "risk-model-v2"
POLICY_VERSION = "risk-policy-v1"
APP_VERSION = "1.0.0"


# -------------------------------------------------------------------
# API / frontend configuration
# -------------------------------------------------------------------

CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173",
    ).split(",")
    if origin.strip()
]