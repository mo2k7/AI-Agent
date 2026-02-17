"""Tests for one-time strict memory preflight migration."""

from __future__ import annotations

import sqlite3
from contextlib import closing

from agent_host.memory.crypto import compute_hmac
from agent_host.memory.migration import run_preflight_migration
from agent_host.memory.store import MemoryStore
from agent_host.memory.types import MemoryKind, MemoryMode


def _build_store(tmp_path) -> MemoryStore:
    return MemoryStore(root_dir=tmp_path / "memory-store", master_key=b"k" * 32)


def test_preflight_migration_upgrades_legacy_semantic_hmac_rows(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Legacy Upgrade", memory_mode=MemoryMode.ON)
    message = store.append_message(
        session.session_id,
        role="user",
        content="Store this preference.",
    )
    memory = store.upsert_semantic_memory(
        session.session_id,
        kind=MemoryKind.PREFERENCE,
        fact_key="legacy_pref",
        content="Legacy value",
        confidence=0.75,
        source_message_id=message.message_id,
        trust_flags=("user_stated",),
        policy_flags=(),
        embedding_service=type("_Embed", (), {"embed": lambda self, *_args, **_kwargs: tuple([0.1] * 8)})(),
    )

    session_db = store._session_db_path(session.session_id)
    with closing(sqlite3.connect(session_db)) as conn:
        row = conn.execute(
            """
            SELECT memory_id, kind, fact_key, content_enc
            FROM semantic_memories
            WHERE memory_id = ?
            """,
            (memory.memory_id,),
        ).fetchone()
        assert row is not None
        legacy_hmac = compute_hmac(
            b"k" * 32,
            f"{row[0]}:{row[3]}:{row[2]}:{row[1]}",
        )
        conn.execute(
            "UPDATE semantic_memories SET hmac = ? WHERE memory_id = ?",
            (legacy_hmac, memory.memory_id),
        )
        conn.commit()

    result = run_preflight_migration(store.root_dir)
    assert result.already_migrated is False
    assert result.upgraded_hmac_rows >= 1

    reloaded = _build_store(tmp_path)
    records = reloaded.list_session_memories(session.session_id, limit=20)
    assert any(record.memory_id == memory.memory_id for record in records)


def test_preflight_migration_removes_ipc_ghost_sessions(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Reference", memory_mode=MemoryMode.ON)
    ghost_id = "ipc-ghost-session"

    with store._index_connection() as conn:
        row = conn.execute(
            """
            SELECT created_at, updated_at, wrapped_dek, wrap_nonce
            FROM sessions
            WHERE session_id = ?
            """,
            (session.session_id,),
        ).fetchone()
        assert row is not None
        now = float(row["updated_at"])
        conn.execute(
            """
            INSERT INTO sessions (
                session_id, title, memory_mode, created_at, updated_at, last_activity,
                status, wrapped_dek, wrap_nonce
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ghost_id,
                "Legacy Ghost",
                MemoryMode.ON.value,
                float(row["created_at"]),
                now,
                now,
                "active",
                str(row["wrapped_dek"]),
                str(row["wrap_nonce"]),
            ),
        )

    store._ensure_session_db(ghost_id)

    result = run_preflight_migration(store.root_dir)
    assert result.removed_ghost_sessions >= 1
    assert not store._session_db_path(ghost_id).exists()
    assert store.get_session(ghost_id) is None


def test_preflight_migration_is_idempotent_after_marker(tmp_path) -> None:
    store = _build_store(tmp_path)
    first = run_preflight_migration(store.root_dir)
    assert first.already_migrated is False

    second = run_preflight_migration(store.root_dir)
    assert second.already_migrated is True
