"""Download the public datasets ChangeGuard's models are trained on.

    python scripts/download_datasets.py
    python src/train_ticket_model.py
    python src/train_code_model.py

Sources:
  * ApacheJIT (Keshavarz & Nagappan, MSR 2022), CC-BY-4.0
    https://zenodo.org/records/5907002
  * BPI Challenge 2014 - Rabobank Group ICT, 4TU.ResearchData
    https://data.4tu.nl/collections/BPI_Challenge_2014/5065469
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

import config  # noqa: E402,F401  (IPv4 preference on networks that need it)
import httpx  # noqa: E402
import truststore  # noqa: E402

from config import APACHEJIT_CSV, BPIC_CHANGE_CSV, BPIC_INCIDENT_CSV, RAW_DATA_DIR  # noqa: E402

truststore.inject_into_ssl()

DATASETS = [
    (
        APACHEJIT_CSV,
        "https://zenodo.org/api/records/5907002/files/apachejit_total.csv/content",
    ),
    (
        BPIC_CHANGE_CSV,
        "https://data.4tu.nl/file/e9c00fe9-c87a-450e-8bd6-d5e06a6b309a/"
        "9d7cd406-9826-4adf-8418-c751b475f556",
    ),
    (
        BPIC_INCIDENT_CSV,
        "https://data.4tu.nl/file/a752c1b5-9732-4bbc-8949-bf24581f9034/"
        "740deeae-5014-48bf-8c86-4a4c3e0355a9",
    ),
]


def main():
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=300, follow_redirects=True) as client:
        for path, url in DATASETS:
            if path.exists() and path.stat().st_size > 0:
                print(f"{path.name}: already downloaded")
                continue

            print(f"{path.name}: downloading ...")
            resp = client.get(url)
            resp.raise_for_status()
            path.write_bytes(resp.content)
            print(f"{path.name}: {len(resp.content) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
