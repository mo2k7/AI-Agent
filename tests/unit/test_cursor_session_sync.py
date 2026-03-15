"""Unit tests for cursor-based session sync (Upgrade D)."""

from __future__ import annotations

import sqlite3

import pytest

from agent_host.memory.store import MemoryStore, MemoryStoreError
from agent_host.memory.types import MemoryMode


def _build_store(tmp_path) -> MemoryStore:
    return MemoryStore(root_dir=tmp_path / "memory-store", master_key=b"m" * 32)


def _get_store_version(store: MemoryStore, session_id: str) -> int:
    """Read store_version from the SessionRecord."""
    session = store.get_session(session_id)
    assert session is not None, f"session {session_id} not found"
    return session.store_version


def test_version_bumps_on_create(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Version Create", memory_mode=MemoryMode.ON)

    version = _get_store_version(store, session.session_id)
    assert version > 0, "store_version should be positive after create"


def test_version_bumps_on_rename(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Before Rename", memory_mode=MemoryMode.ON)

    version1 = _get_store_version(store, session.session_id)
    store.rename_session(session.session_id, title="After Rename")
    version2 = _get_store_version(store, session.session_id)

    assert version2 > version1, "store_version should increase after rename"


def test_version_bumps_on_set_mode(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Mode Change", memory_mode=MemoryMode.ON)

    version1 = _get_store_version(store, session.session_id)
    store.set_session_mode(session.session_id, MemoryMode.OFF)
    version2 = _get_store_version(store, session.session_id)

    assert version2 > version1, "store_version should increase after set_session_mode"


def test_version_bumps_on_touch(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Touch Version", memory_mode=MemoryMode.ON)

    version1 = _get_store_version(store, session.session_id)
    store.append_message(session.session_id, role="user", content="bump")
    version2 = _get_store_version(store, session.session_id)

    assert version2 > version1, "store_version should increase after append_message"


def test_list_sessions_since_zero_returns_all(tmp_path) -> None:
    store = _build_store(tmp_path)
    ids = []
    for i in range(3):
        s = store.create_session(title=f"Session {i}", memory_mode=MemoryMode.ON)
        ids.append(s.session_id)

    records, max_ver = store.list_sessions_since(0)
    returned_ids = {r.session_id for r in records}
    for sid in ids:
        assert sid in returned_ids, f"session {sid} should be in list_sessions_since(0)"
    assert len(records) == 3


def test_list_sessions_since_returns_only_changed(tmp_path) -> None:
    store = _build_store(tmp_path)
    s1 = store.create_session(title="Session A", memory_mode=MemoryMode.ON)
    s2 = store.create_session(title="Session B", memory_mode=MemoryMode.ON)

    old_max = store.max_store_version()
    store.rename_session(s1.session_id, title="Session A Renamed")

    records, max_ver = store.list_sessions_since(old_max)
    returned_ids = {r.session_id for r in records}
    assert s1.session_id in returned_ids, "renamed session should appear in delta"
    assert s2.session_id not in returned_ids, "unchanged session should not appear in delta"
    assert len(records) == 1


def test_max_store_version_correctness(tmp_path) -> None:
    store = _build_store(tmp_path)
    s1 = store.create_session(title="Session X", memory_mode=MemoryMode.ON)
    s2 = store.create_session(title="Session Y", memory_mode=MemoryMode.ON)

    store.rename_session(s1.session_id, title="Session X Renamed")

    v1 = _get_store_version(store, s1.session_id)
    v2 = _get_store_version(store, s2.session_id)
    expected_max = max(v1, v2)

    assert store.max_store_version() == expected_max


def test_deleted_sessions_excluded_from_delta(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Doomed", memory_mode=MemoryMode.ON)

    store.delete_session(session.session_id)

    records, max_ver = store.list_sessions_since(0)
    returned_ids = {r.session_id for r in records}
    assert session.session_id not in returned_ids, "deleted session should not appear"
    assert len(records) == 0


def test_column_auto_created(tmp_path) -> None:
    store = _build_store(tmp_path)
    # Force schema creation by creating at least one session.
    _ = store.create_session(title="Schema Check", memory_mode=MemoryMode.ON)

    index_db = tmp_path / "memory-store" / "index.db"
    with sqlite3.connect(str(index_db)) as conn:
        columns = conn.execute("PRAGMA table_info(sessions)").fetchall()
    column_names = [col[1] for col in columns]
    assert "store_version" in column_names, "store_version column should exist in sessions table"
