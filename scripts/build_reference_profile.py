"""Build models/reference_profile.json: the training-data distribution of
each model input, which the Monitoring page compares live assessments
against to detect drift.

    python scripts/download_datasets.py      # once
    python scripts/build_reference_profile.py

Uses the same training rows the shipped models were fitted on (the oldest
80% by date of each dataset), without retraining anything.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

import monitoring  # noqa: E402
import ticket_risk as tr  # noqa: E402
from config import APACHEJIT_CSV, BPIC_CHANGE_CSV, BPIC_INCIDENT_CSV  # noqa: E402


def main():
    print("Ticket model: building the BPIC 2014 training table ...")
    tickets = tr.build_training_table(BPIC_CHANGE_CSV, BPIC_INCIDENT_CSV)
    tickets = tickets.iloc[: int(len(tickets) * 0.8)]
    spec = monitoring.DRIFT_FEATURES["ticket"]
    monitoring.save_reference("ticket", monitoring.build_reference(
        tickets, spec["numeric"], spec["categorical"],
        "BPI Challenge 2014 (Rabobank) - training rows, oldest 80%",
    ))
    print(f"  {len(tickets)} rows")

    print("Code model: reading ApacheJIT ...")
    commits = pd.read_csv(APACHEJIT_CSV).sort_values("author_date").reset_index(drop=True)
    commits = commits.iloc[: int(len(commits) * 0.8)]
    spec = monitoring.DRIFT_FEATURES["code"]
    monitoring.save_reference("code", monitoring.build_reference(
        commits, spec["numeric"], spec["categorical"],
        "ApacheJIT - training rows, oldest 80%",
    ))
    print(f"  {len(commits)} rows")

    print("Saved", monitoring.REFERENCE_PATH)


if __name__ == "__main__":
    main()
