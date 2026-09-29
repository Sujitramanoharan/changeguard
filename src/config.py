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

MODELS_DIR = ROOT / "models"
MODELS_DIR.mkdir(exist_ok=True)


# -------------------------------------------------------------------
# Public datasets (downloaded by scripts/download_datasets.py)
# -------------------------------------------------------------------

RAW_DATA_DIR = ROOT / "data" / "raw"

APACHEJIT_CSV = RAW_DATA_DIR / "apachejit_total.csv"
BPIC_CHANGE_CSV = RAW_DATA_DIR / "bpic2014_change.csv"
BPIC_INCIDENT_CSV = RAW_DATA_DIR / "bpic2014_incident.csv"


# -------------------------------------------------------------------
# Trained model artifacts
# -------------------------------------------------------------------

# Change-ticket model (Rabobank BPIC 2014 ITIL records).
TICKET_MODEL_PATH = MODELS_DIR / "ticket_model.pkl"
TICKET_STATS_PATH = MODELS_DIR / "ticket_stats.json"
TICKET_INDEX_PATH = MODELS_DIR / "ticket_similar.index"

# Code-change model (ApacheJIT commits).
CODE_MODEL_PATH = MODELS_DIR / "code_model.pkl"
CODE_INDEX_PATH = MODELS_DIR / "code_similar.index"

# Held-out evaluation of both models, shown in the in-app model card.
METRICS_PATH = MODELS_DIR / "metrics.json"


# -------------------------------------------------------------------
# Audit / version metadata
# -------------------------------------------------------------------

MODEL_VERSION = "risk-models-v3-real-data"
POLICY_VERSION = "risk-policy-v2"
APP_VERSION = "2.0.0"


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