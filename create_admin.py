from getpass import getpass

from backend.database import init_db, create_user, get_user_by_username


init_db()

username = input("Admin username: ").strip()
password = getpass("Admin password: ")
confirm = getpass("Confirm password: ")

if password != confirm:
    raise SystemExit("Passwords do not match.")

if not username:
    raise SystemExit("Username cannot be empty.")

if not password:
    raise SystemExit("Password cannot be empty.")

if get_user_by_username(username):
    raise SystemExit("Username already exists.")

create_user(
    username=username,
    password=password,
    role="admin",
)

print(f"Admin user '{username}' created successfully.")