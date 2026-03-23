"""Fernet-based encryption for SSH credentials stored at rest.

Derives a 32-byte Fernet key from the master secret using PBKDF2-HMAC-SHA256
with 260,000 iterations for brute-force resistance. Maintains backward
compatibility with data encrypted using the legacy SHA-256 derivation.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

_PBKDF2_ITERATIONS = 260_000


class CredentialVault:
    """Encrypt/decrypt strings using a Fernet key derived from a master secret."""

    def __init__(self, master_secret: str) -> None:
        # New: PBKDF2-derived key (brute-force resistant)
        salt = hashlib.sha256(master_secret.encode()).digest()[:16]
        key_bytes = hashlib.pbkdf2_hmac("sha256", master_secret.encode(), salt, _PBKDF2_ITERATIONS)
        self._fernet = Fernet(base64.urlsafe_b64encode(key_bytes))

        # Legacy: bare SHA-256 key (for reading old data during migration)
        legacy_key = hashlib.sha256(master_secret.encode()).digest()
        self._legacy_fernet = Fernet(base64.urlsafe_b64encode(legacy_key))

    def encrypt(self, plaintext: str) -> str:
        """Return a Fernet-encrypted, base64-encoded ciphertext string."""
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Return the original plaintext from a Fernet ciphertext string.

        Tries the new PBKDF2-derived key first, then falls back to the legacy
        SHA-256 key for backward compatibility with existing encrypted data.
        """
        raw = ciphertext.encode()
        try:
            return self._fernet.decrypt(raw).decode()
        except InvalidToken:
            return self._legacy_fernet.decrypt(raw).decode()
