"""Reset (or create) a user's password in the local database.

    python scripts/reset_password.py

Useful when a database has accounts whose passwords you no longer
remember. Affects the database this process is configured for:
DATABASE_URL (PostgreSQL) if set, otherwise the local SQLite file.
"""

import sys
from getpass import getpass
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from backend.database import create_user, describe_database, init_db, set_password  # noqa: E402


def main():
    init_db()

    username = input("Username: ").strip()
    if not username:
        raise SystemExit("Username cannot be empty.")

    password = getpass("New password: ")
    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters.")
    if password != getpass("Confirm password: "):
        raise SystemExit("Passwords do not match.")

    if set_password(username, password):
        print(f"Password updated for '{username}' in {describe_database()}.")
    else:
        role = input("User does not exist - role to create (admin/reviewer): ").strip() or "reviewer"
        create_user(username=username, password=password, role=role)
        print(f"Created {role} '{username}' in {describe_database()}.")


if __name__ == "__main__":
    main()
