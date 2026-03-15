"""Regression coverage for session/memory reliability fixes."""

from __future__ import annotations

import base64
import sqlite3
from contextlib import closing

import pytest

from agent_host.memory.manager import MemoryManager
from agent_host.memory.store import MemoryStore, MemoryStoreError
from agent_host.memory.types import MemoryMode


def _build_store(tmp_path) -> MemoryStore:
    return MemoryStore(root_dir=tmp_path / "memory-store", master_key=b"k" * 32)




def test_list_messages_returns_recent_window_in_chronological_order(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Windowed", memory_mode=MemoryMode.ON)

    for index in range(10):
        store.append_message(session.session_id, role="user", content=f"m{index}")

    recent = store.list_messages(session.session_id, limit=3)
    assert [row.content for row in recent] == ["m7", "m8", "m9"]


def test_index_schema_self_heals_missing_sessions_columns(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Legacy Schema", memory_mode=MemoryMode.ON)

    with closing(sqlite3.connect(store.db_path)) as conn:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("ALTER TABLE sessions RENAME TO sessions_old")
        conn.execute(
            """
            CREATE TABLE sessions (
                session_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                memory_mode TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO sessions (session_id, title, memory_mode, created_at, updated_at)
            SELECT session_id, title, memory_mode, created_at, updated_at
            FROM sessions_old
            """
        )
        conn.execute("DROP TABLE sessions_old")
        conn.commit()

    rows = store.list_sessions(limit=10)
    assert rows and rows[0].session_id == session.session_id

    with store._db_connection() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    assert {"last_activity", "status", "wrapped_dek", "wrap_nonce"}.issubset(columns)


def test_prepare_prompt_context_rejects_unknown_session_for_non_persistent_modes(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"a" * 32).decode("ascii"),
    )
    manager = MemoryManager(tmp_path / "memory")

    with pytest.raises(Exception, match="Unknown session"):
        manager.prepare_prompt_context(
            session_id="auto-off-session",
            prompt="hello",
            memory_mode=MemoryMode.OFF,
        )
    with pytest.raises(Exception, match="Unknown session"):
        manager.prepare_prompt_context(
            session_id="auto-ephemeral-session",
            prompt="hello",
            memory_mode=MemoryMode.EPHEMERAL,
        )
