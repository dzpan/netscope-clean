"""Tests for SSH credential encryption/decryption."""

import base64
import hashlib
import json

import pytest
from cryptography.fernet import Fernet

from backend.credential_vault import CredentialVault


@pytest.fixture
def vault() -> CredentialVault:
    return CredentialVault("test-secret-key-for-unit-tests-1234")


def test_encrypt_decrypt_roundtrip(vault: CredentialVault) -> None:
    plaintext = "my-ssh-password"
    encrypted = vault.encrypt(plaintext)
    assert encrypted != plaintext
    assert vault.decrypt(encrypted) == plaintext


def test_encrypt_produces_different_ciphertext(vault: CredentialVault) -> None:
    """Fernet uses a random IV, so two encryptions of the same value differ."""
    a = vault.encrypt("same")
    b = vault.encrypt("same")
    assert a != b


def test_decrypt_with_wrong_key() -> None:
    vault1 = CredentialVault("key-one-abcdef")
    vault2 = CredentialVault("key-two-abcdef")
    encrypted = vault1.encrypt("secret")
    with pytest.raises(Exception):
        vault2.decrypt(encrypted)


def test_encrypt_json_blob(vault: CredentialVault) -> None:
    """DiscoverRequest credentials are JSON — verify round-trip."""
    creds = json.dumps({"username": "admin", "password": "cisco123"})
    encrypted = vault.encrypt(creds)
    decrypted = vault.decrypt(encrypted)
    assert json.loads(decrypted) == {"username": "admin", "password": "cisco123"}


def test_encrypt_empty_string(vault: CredentialVault) -> None:
    encrypted = vault.encrypt("")
    assert vault.decrypt(encrypted) == ""


def test_legacy_sha256_ciphertext_still_decryptable() -> None:
    """Existing data encrypted with old SHA-256 derivation must still decrypt."""
    secret = "test-secret-key-for-unit-tests-1234"
    legacy_key = hashlib.sha256(secret.encode()).digest()
    legacy_fernet = Fernet(base64.urlsafe_b64encode(legacy_key))
    legacy_ciphertext = legacy_fernet.encrypt(b"legacy-data").decode()

    vault = CredentialVault(secret)
    assert vault.decrypt(legacy_ciphertext) == "legacy-data"


def test_new_encrypt_not_decryptable_by_legacy_key() -> None:
    """New vault encrypts with PBKDF2 key — legacy Fernet cannot decrypt it."""
    secret = "test-secret-key-for-unit-tests-1234"
    vault = CredentialVault(secret)
    new_ciphertext = vault.encrypt("new-data")

    legacy_key = hashlib.sha256(secret.encode()).digest()
    legacy_fernet = Fernet(base64.urlsafe_b64encode(legacy_key))
    with pytest.raises(Exception):
        legacy_fernet.decrypt(new_ciphertext.encode())
