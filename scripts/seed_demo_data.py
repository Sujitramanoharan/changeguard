"""CLI entry point to seed a realistic assessment history for demos.

See src/demo_data.py for the scenarios and seeding logic - shared with
the POST /api/admin/seed-demo-data endpoint for hosts with no shell
access (e.g. free-tier PaaS with ephemeral storage).

Usage:
    python scripts/seed_demo_data.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from demo_data import seed_demo_assessments


if __name__ == "__main__":
    count = seed_demo_assessments()
    print(f"Seeded {count} assessments.")
