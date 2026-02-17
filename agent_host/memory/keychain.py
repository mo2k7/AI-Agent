"""Keychain-backed key management for local memory encryption."""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
from dataclasses import dataclass


SERVICE_NAME = "ai-agent-memory-master-key-v1"
ACCOUNT_NAME = "default-user"
MASTER_KEY_BYTES = 32


class KeychainError(RuntimeError):
    """Raised when secure key material cannot be acquired."""


@dataclass(frozen=True)
class KeyMaterial:
    """In-memory encryption key material."""

    raw: bytes


def _decode_master_key_b64(encoded: str, *, source: str) -> bytes:
    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise KeychainError(f"{source} is not valid base64") from exc

    if len(raw) != MASTER_KEY_BYTES:
        raise KeychainError(
            f"{source} must decode to exactly {MASTER_KEY_BYTES} bytes for AES-256-GCM"
        )
    return raw


def _security_available() -> bool:
    return shutil.which("security") is not None


def _run_security(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["security", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def _load_from_keychain() -> bytes | None:
    if not _security_available():
        return None

    proc = _run_security(
        [
            "find-generic-password",
            "-s",
            SERVICE_NAME,
            "-a",
            ACCOUNT_NAME,
            "-w",
        ]
    )
    if proc.returncode != 0:
        return None

    value = proc.stdout.strip()
    if not value:
        return None

    return _decode_master_key_b64(value, source="Keychain memory key payload")


def _persist_to_keychain(key: bytes) -> None:
    if not _security_available():
        return

    encoded = base64.b64encode(key).decode("ascii")
    proc = _run_security(
        [
            "add-generic-password",
            "-U",
            "-s",
            SERVICE_NAME,
            "-a",
            ACCOUNT_NAME,
            "-w",
            encoded,
        ]
    )
    if proc.returncode != 0:
        raise KeychainError(
            f"Failed to persist memory key in Keychain: {proc.stderr.strip() or 'unknown error'}"
        )


def get_or_create_master_key() -> KeyMaterial:
    """Return a stable master key, creating one if needed.

    Preference order:
    1) macOS Keychain entry
    2) generate and store in Keychain
    """
    existing = _load_from_keychain()
    if existing:
        return KeyMaterial(raw=existing)

    generated = os.urandom(32)
    if _security_available():
        _persist_to_keychain(generated)
        return KeyMaterial(raw=generated)

    raise KeychainError(
        "Keychain is required in this runtime. Provide a valid macOS keychain context."
    )
