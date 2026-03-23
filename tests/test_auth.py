"""Tests for auth module — password hashing and token generation."""

from backend.auth import generate_api_key, hash_api_key, hash_password, verify_password


def test_hash_and_verify_password() -> None:
    hashed = hash_password("my-secure-password")
    assert hashed != "my-secure-password"
    assert verify_password("my-secure-password", hashed)


def test_verify_wrong_password() -> None:
    hashed = hash_password("correct-password")
    assert not verify_password("wrong-password", hashed)


def test_hash_password_unique_salts() -> None:
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2  # different salts


def test_generate_api_key_format() -> None:
    key = generate_api_key()
    assert key.startswith("ns_")
    assert len(key) > 20


def test_hash_api_key_deterministic() -> None:
    key = "ns_abc123"
    h1 = hash_api_key(key)
    h2 = hash_api_key(key)
    assert h1 == h2


def test_hash_api_key_different_keys() -> None:
    h1 = hash_api_key("ns_key1")
    h2 = hash_api_key("ns_key2")
    assert h1 != h2
