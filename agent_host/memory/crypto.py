"""Cryptographic helpers for encrypted memory persistence."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


@dataclass(frozen=True)
class EncryptedBlob:
    """Serializable encrypted payload."""

    nonce: str
    ciphertext: str

    def to_json(self) -> str:
        return json.dumps({"nonce": self.nonce, "ciphertext": self.ciphertext})

    @classmethod
    def from_json(cls, payload: str) -> "EncryptedBlob":
        data = json.loads(payload)
        return cls(nonce=str(data["nonce"]), ciphertext=str(data["ciphertext"]))


class CryptoBox:
    """AES-GCM helper bound to a specific key."""

    def __init__(self, key: bytes):
        if len(key) != 32:
            raise ValueError("AES-256-GCM requires a 32-byte key")
        self._key = key
        self._cipher = AESGCM(key)

    def encrypt_text(self, plaintext: str, aad: bytes = b"") -> str:
        nonce = os.urandom(12)
        ciphertext = self._cipher.encrypt(nonce, plaintext.encode("utf-8"), aad)
        return EncryptedBlob(nonce=_b64e(nonce), ciphertext=_b64e(ciphertext)).to_json()

    def decrypt_text(self, payload: str, aad: bytes = b"") -> str:
        blob = EncryptedBlob.from_json(payload)
        nonce = _b64d(blob.nonce)
        ciphertext = _b64d(blob.ciphertext)
        plaintext = self._cipher.decrypt(nonce, ciphertext, aad)
        return plaintext.decode("utf-8")

    def encrypt_bytes(self, data: bytes, aad: bytes = b"") -> str:
        """Encrypt raw bytes, returning an EncryptedBlob JSON string."""
        nonce = os.urandom(12)
        ciphertext = self._cipher.encrypt(nonce, data, aad)
        return EncryptedBlob(nonce=_b64e(nonce), ciphertext=_b64e(ciphertext)).to_json()

    def decrypt_bytes(self, payload: str, aad: bytes = b"") -> bytes:
        """Decrypt an EncryptedBlob JSON string back to raw bytes."""
        blob = EncryptedBlob.from_json(payload)
        nonce = _b64d(blob.nonce)
        ciphertext = _b64d(blob.ciphertext)
        return self._cipher.decrypt(nonce, ciphertext, aad)

    def wrap_key(self, data_key: bytes) -> tuple[str, str]:
        nonce = os.urandom(12)
        wrapped = self._cipher.encrypt(nonce, data_key, b"session-key-wrap")
        return _b64e(wrapped), _b64e(nonce)

    def unwrap_key(self, wrapped_b64: str, nonce_b64: str) -> bytes:
        wrapped = _b64d(wrapped_b64)
        nonce = _b64d(nonce_b64)
        return self._cipher.decrypt(nonce, wrapped, b"session-key-wrap")


def compute_hmac(key: bytes, value: str) -> str:
    """Return hex HMAC-SHA256 for tamper checks."""
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_hmac(key: bytes, value: str, digest: str) -> bool:
    expected = compute_hmac(key, value)
    return hmac.compare_digest(expected, digest)
