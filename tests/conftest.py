import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

# Tests must never touch the real audit database. Set before any
# backend module is imported, since DB_PATH is read at import time.
os.environ["CHANGEGUARD_DB_PATH"] = str(
    Path(tempfile.mkdtemp(prefix="changeguard-tests-")) / "test.db"
)

# Run the suite against PostgreSQL by setting TEST_DATABASE_URL to a
# throwaway database; otherwise the temporary SQLite file above is used.
if os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
else:
    os.environ.pop("DATABASE_URL", None)
os.environ.setdefault("CHANGEGUARD_JWT_SECRET", "test-secret")
