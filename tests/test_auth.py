"""Unit tests for JWT and password-hashing helpers."""

import pytest

from backend.auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("correct-horse-battery-staple")

    assert verify_password("correct-horse-battery-staple", hashed)
    assert not verify_password("wrong-password", hashed)


def test_password_hash_is_not_plaintext():
    hashed = hash_password("my-secret-password")

    assert hashed != "my-secret-password"


def test_access_token_roundtrip():
    token = create_access_token(username="alice", role="reviewer")
    payload = decode_access_token(token)

    assert payload["sub"] == "alice"
    assert payload["role"] == "reviewer"


def test_tampered_token_is_rejected():
    token = create_access_token(username="bob", role="admin")

    import jwt as pyjwt

    with pytest.raises(pyjwt.InvalidTokenError):
        decode_access_token(token + "tampered")
