"""Authentication and JWT utilities for ChangeGuard."""

import os
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv
from pwdlib import PasswordHash


# -------------------------------------------------------------------
# Load environment configuration
# -------------------------------------------------------------------

load_dotenv()


# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------

JWT_SECRET_KEY = os.getenv("CHANGEGUARD_JWT_SECRET")

if not JWT_SECRET_KEY:
    raise RuntimeError(
        "CHANGEGUARD_JWT_SECRET is not configured."
    )

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60


# -------------------------------------------------------------------
# Password hashing
# -------------------------------------------------------------------

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Return a secure password hash."""
    return password_hash.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    """Verify a password against its stored hash."""
    return password_hash.verify(
        plain_password,
        hashed_password,
    )


# -------------------------------------------------------------------
# JWT access tokens
# -------------------------------------------------------------------

def create_access_token(
    username: str,
    role: str,
) -> str:
    """Create a signed JWT access token."""

    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    payload = {
        "sub": username,
        "role": role,
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token."""

    return jwt.decode(
        token,
        JWT_SECRET_KEY,
        algorithms=[JWT_ALGORITHM],
    )