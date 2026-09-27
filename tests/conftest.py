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
os.environ.setdefault("CHANGEGUARD_JWT_SECRET", "test-secret")
