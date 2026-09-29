"""Reset (or create) a user's password in the local database.

    python scripts/reset_password.py

Useful when the local database has accounts whose passwords you no
longer remember. Only affects the database this machine uses
(CHANGEGUARD_DB_PATH, or changeguard.db in the project root).
"""

import sqlite3
import sys
from getpass import getpass
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from backend.database import DB_PATH, create_user, get_user_by_username, init_db, password_hash  # noqa: E402


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

    if get_user_by_username(username):
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (password_hash.hash(password), username),
        )
        conn.commit()
        conn.close()
        print(f"Password updated for '{username}' in {DB_PATH}.")
    else:
        role = input("User does not exist - role to create (admin/reviewer): ").strip() or "reviewer"
        create_user(username=username, password=password, role=role)
        print(f"Created {role} '{username}' in {DB_PATH}.")


if __name__ == "__main__":
    main()
