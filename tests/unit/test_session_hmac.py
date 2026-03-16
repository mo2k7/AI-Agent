"""Unit tests for session row HMAC integrity (Upgrade E)."""

from __future__ import annotations

import sqlite3

import pytest

from agent_host.memory.store import MemoryStore, MemoryStoreError
from agent_host.memory.types import MemoryMode


def _build_store(tmp_path) -> MemoryStore:
    return MemoryStore(root_dir=tmp_path / "memory-store", master_key=b"m" * 32)


def _get_row_hmac(tmp_path, session_id: str) -> str:
    """Read the raw row_hmac value from the index DB for a given session."""
    index_db = tmp_path / "memory-store" / "memory.db"
    with sqlite3.connect(str(index_db)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT row_hmac FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    assert row is not None, f"session {session_id} not found in index DB"
    return row["row_hmac"]


def test_create_session_computes_hmac(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="HMAC Session", memory_mode=MemoryMode.ON)

    hmac_value = _get_row_hmac(tmp_path, session.session_id)
    assert hmac_value, "row_hmac should be non-empty after create"
    assert all(c in "0123456789abcdef" for c in hmac_value), (
        "row_hmac should be a hex string"
    )


def test_get_session_verifies_hmac(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Verify OK", memory_mode=MemoryMode.ON)

    # Should succeed without raising.
    fetched = store.get_session(session.session_id)
    assert fetched is not None
    assert fetched.title == "Verify OK"


def test_tampered_title_detected(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Original", memory_mode=MemoryMode.ON)

    index_db = tmp_path / "memory-store" / "memory.db"
    with sqlite3.connect(str(index_db)) as conn:
        conn.execute(
            "UPDATE sessions SET title = 'hacked' WHERE session_id = ?",
            (session.session_id,),
        )
        conn.commit()

    with pytest.raises(MemoryStoreError, match="HMAC verification failed"):
        store.get_session(session.session_id)


def test_tampered_mode_detected(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Mode Tamper", memory_mode=MemoryMode.ON)

    index_db = tmp_path / "memory-store" / "memory.db"
    with sqlite3.connect(str(index_db)) as conn:
        conn.execute(
            "UPDATE sessions SET memory_mode = 'off' WHERE session_id = ?",
            (session.session_id,),
        )
        conn.commit()

    with pytest.raises(MemoryStoreError, match="HMAC verification failed"):
        store.get_session(session.session_id)


def test_empty_hmac_passes_premigration(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Legacy Row", memory_mode=MemoryMode.ON)

    index_db = tmp_path / "memory-store" / "memory.db"
    with sqlite3.connect(str(index_db)) as conn:
        conn.execute(
            "UPDATE sessions SET row_hmac = '' WHERE session_id = ?",
            (session.session_id,),
        )
        conn.commit()

    # Empty HMAC means pre-migration row — should pass verification.
    fetched = store.get_session(session.session_id)
    assert fetched is not None
    assert fetched.title == "Legacy Row"


def test_rename_recomputes_hmac(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Before Rename", memory_mode=MemoryMode.ON)

    hmac1 = _get_row_hmac(tmp_path, session.session_id)
    store.rename_session(session.session_id, title="After Rename")
    hmac2 = _get_row_hmac(tmp_path, session.session_id)

    assert hmac1 != hmac2, "HMAC should change after rename"


def test_set_mode_recomputes_hmac(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Mode Change", memory_mode=MemoryMode.ON)

    hmac1 = _get_row_hmac(tmp_path, session.session_id)
    store.set_session_mode(session.session_id, MemoryMode.OFF)
    hmac2 = _get_row_hmac(tmp_path, session.session_id)

    assert hmac1 != hmac2, "HMAC should change after mode update"


def test_touch_recomputes_hmac(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Touch Test", memory_mode=MemoryMode.ON)

    hmac1 = _get_row_hmac(tmp_path, session.session_id)
    store.append_message(session.session_id, role="user", content="hello")
    hmac2 = _get_row_hmac(tmp_path, session.session_id)

    assert hmac1 != hmac2, "HMAC should change after append_message (touch)"
