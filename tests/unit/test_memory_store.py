"""Unit tests for secure session/semantic memory storage."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from agent_host.memory.crypto import compute_hmac
from agent_host.memory.store import MemoryStore, MemoryStoreError
from agent_host.memory.types import MemoryKind, MemoryMode


def _build_store(tmp_path) -> MemoryStore:
    return MemoryStore(root_dir=tmp_path / "memory-store", master_key=b"m" * 32)


class _StubEmbeddingService:
    def embed(self, *_args, **_kwargs):
        return tuple([0.1] * 8)


def test_ensure_session_updates_memory_mode(tmp_path) -> None:
    store = _build_store(tmp_path)
    created = store.create_session(title="Session A", memory_mode=MemoryMode.ON)

    updated = store.ensure_session(created.session_id, memory_mode=MemoryMode.EPHEMERAL)

    assert updated.session_id == created.session_id
    assert updated.memory_mode == MemoryMode.EPHEMERAL


def test_semantic_delete_removes_cross_session_index_entry(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Session B", memory_mode=MemoryMode.ON)
    message = store.append_message(
        session.session_id,
        role="user",
        content="Remember that I prefer markdown summaries.",
    )

    memory = store.upsert_semantic_memory(
        session.session_id,
        kind=MemoryKind.PREFERENCE,
        fact_key="preference_markdown",
        content="User prefers markdown summaries.",
        confidence=0.82,
        source_message_id=message.message_id,
        trust_flags=("user_stated",),
        policy_flags=(),
        embedding_service=_StubEmbeddingService(),
    )

    candidate_ids = {row["memory_id"] for row in store.semantic_index_candidates(limit=20)}
    assert memory.memory_id in candidate_ids

    deleted = store.delete_memory(session.session_id, memory.memory_id)
    assert deleted is True

    candidate_ids_after_delete = {row["memory_id"] for row in store.semantic_index_candidates(limit=20)}
    assert memory.memory_id not in candidate_ids_after_delete


def test_semantic_memory_detects_policy_flag_tampering(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Tamper Check", memory_mode=MemoryMode.ON)
    message = store.append_message(
        session.session_id,
        role="user",
        content="Remember my editor preference.",
    )
    memory = store.upsert_semantic_memory(
        session.session_id,
        kind=MemoryKind.PREFERENCE,
        fact_key="editor_preference",
        content="User prefers Vim.",
        confidence=0.9,
        source_message_id=message.message_id,
        trust_flags=("user_stated",),
        policy_flags=(),
        embedding_service=_StubEmbeddingService(),
    )

    session_db = store._session_db_path(session.session_id)
    with closing(sqlite3.connect(session_db)) as conn:
        conn.execute(
            "UPDATE semantic_memories SET policy_flags_json = ? WHERE memory_id = ?",
            ('["quarantine"]', memory.memory_id),
        )
        conn.commit()

    with pytest.raises(MemoryStoreError, match="Failed to decode memory record"):
        store.list_session_memories(session.session_id, limit=20)


def test_semantic_memory_legacy_hmac_rows_fail_without_preflight_migration(tmp_path) -> None:
    root = tmp_path / "memory-store"
    store = MemoryStore(root_dir=root, master_key=b"m" * 32)
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
        embedding_service=_StubEmbeddingService(),
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
            b"m" * 32,
            f"{row[0]}:{row[3]}:{row[2]}:{row[1]}",
        )
        conn.execute(
            "UPDATE semantic_memories SET hmac = ? WHERE memory_id = ?",
            (legacy_hmac, memory.memory_id),
        )
        conn.commit()

    reloaded = MemoryStore(root_dir=root, master_key=b"m" * 32)
    with pytest.raises(MemoryStoreError, match="HMAC verification failed"):
        reloaded.list_session_memories(session.session_id, limit=20)


def test_list_messages_returns_full_ordered_conversation(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Session C", memory_mode=MemoryMode.ON)

    store.append_message(
        session.session_id,
        role="user",
        content="First message",
    )
    store.append_message(
        session.session_id,
        role="assistant",
        content="Second message",
    )
    store.append_message(
        session.session_id,
        role="user",
        content="Third message",
    )

    messages = store.list_messages(session.session_id, limit=20)
    assert [message.role for message in messages] == ["user", "assistant", "user"]
    assert [message.content for message in messages] == [
        "First message",
        "Second message",
        "Third message",
    ]
    assert [message.turn_index for message in messages] == [0, 1, 2]


def test_rename_session_updates_title(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Initial Name", memory_mode=MemoryMode.ON)

    renamed = store.rename_session(session.session_id, title="Renamed Session")

    assert renamed.session_id == session.session_id
    assert renamed.title == "Renamed Session"


def test_index_schema_recreated_empty_does_not_restore_sessions_runtime(tmp_path) -> None:
    store = _build_store(tmp_path)
    _ = store.create_session(title="Before", memory_mode=MemoryMode.ON)

    store.index_db_path.unlink(missing_ok=True)
    sqlite3.connect(store.index_db_path).close()

    sessions = store.list_sessions(limit=20)
    assert sessions == []

    created = store.create_session(title="After", memory_mode=MemoryMode.ON)
    assert created.title == "After"


def test_index_schema_missing_sessions_table_does_not_restore_legacy_session_rows(tmp_path) -> None:
    store = _build_store(tmp_path)
    _ = store.create_session(title="Before Drop", memory_mode=MemoryMode.ON)

    with closing(sqlite3.connect(store.index_db_path)) as conn:
        conn.execute("DROP TABLE sessions")
        conn.commit()

    sessions = store.list_sessions(limit=20)
    assert sessions == []

    created = store.create_session(title="After Drop", memory_mode=MemoryMode.ON)
    assert created.title == "After Drop"


def test_delete_session_removes_sqlite_sidecars(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Session D", memory_mode=MemoryMode.ON)
    message = store.append_message(
        session.session_id,
        role="user",
        content="delete-test",
    )
    memory = store.upsert_semantic_memory(
        session.session_id,
        kind=MemoryKind.PREFERENCE,
        fact_key="delete_test",
        content="delete me",
        confidence=0.71,
        source_message_id=message.message_id,
        trust_flags=("user_stated",),
        policy_flags=(),
        embedding_service=_StubEmbeddingService(),
    )

    session_db = store._session_db_path(session.session_id)
    sidecar_wal = Path(f"{session_db}-wal")
    sidecar_shm = Path(f"{session_db}-shm")

    candidate_ids = {row["memory_id"] for row in store.semantic_index_candidates(limit=20)}
    assert memory.memory_id in candidate_ids

    # Create sidecars explicitly so deletion behavior is deterministic.
    sidecar_wal.write_text("wal")
    sidecar_shm.write_text("shm")

    store.delete_session(session.session_id)

    assert not session_db.exists()
    assert not sidecar_wal.exists()
    assert not sidecar_shm.exists()
    assert store.get_session(session.session_id) is None
    assert session.session_id not in {row.session_id for row in store.list_sessions(limit=20)}
    candidate_ids_after = {row["memory_id"] for row in store.semantic_index_candidates(limit=20)}
    assert memory.memory_id not in candidate_ids_after


def test_list_sessions_self_heals_invalid_memory_mode_values(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Mode Repair", memory_mode=MemoryMode.ON)

    with store._index_connection() as conn:
        conn.execute(
            "UPDATE sessions SET memory_mode = ? WHERE session_id = ?",
            ("broken_mode", session.session_id),
        )

    rows = store.list_sessions(limit=10)
    assert len(rows) == 1
    assert rows[0].memory_mode == MemoryMode.ON

    repaired = store.get_session(session.session_id)
    assert repaired is not None
    assert repaired.memory_mode == MemoryMode.ON


def test_list_messages_raises_on_corrupted_message_rows(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Corruption", memory_mode=MemoryMode.ON)

    store.append_message(session.session_id, role="user", content="good-1")
    store.append_message(session.session_id, role="assistant", content="good-2")

    session_db = store._session_db_path(session.session_id)
    with closing(sqlite3.connect(session_db)) as conn:
        conn.execute(
            """
            UPDATE messages
            SET content_enc = 'corrupted-payload'
            WHERE turn_index = 0
            """
        )
        conn.commit()

    with pytest.raises(MemoryStoreError, match="Failed to decode message"):
        store.list_messages(session.session_id, limit=20)


def test_session_schema_self_heals_when_messages_table_is_missing(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Message Table Drop", memory_mode=MemoryMode.ON)
    store.append_message(session.session_id, role="user", content="persist-me")

    session_db = store._session_db_path(session.session_id)
    with closing(sqlite3.connect(session_db)) as conn:
        conn.execute("DROP TABLE messages")
        conn.commit()

    # Should not raise; missing table is recreated automatically.
    recovered = store.list_messages(session.session_id, limit=20)
    assert recovered == []


def test_delete_note_also_soft_deletes_attached_images(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Notes Session", memory_mode=MemoryMode.ON)
    note = store.create_note(session.session_id, content="Body", source="user")
    image = store.create_note_image(
        session.session_id,
        note["note_id"],
        image_bytes=b"\x89PNG\r\n\x1a\n",
        mime_type="image/png",
        width=10,
        height=10,
        alt_text="diagram",
    )

    assert store.get_note_image(session.session_id, image["image_id"]) is not None
    assert len(store.list_note_images(session.session_id, note["note_id"])) == 1

    deleted = store.delete_note(session.session_id, note["note_id"])
    assert deleted is True
    assert store.get_note_image(session.session_id, image["image_id"]) is None
    assert store.list_note_images(session.session_id, note["note_id"]) == []


def test_create_note_image_rejects_deleted_note(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Deleted Note Session", memory_mode=MemoryMode.ON)
    note = store.create_note(session.session_id, content="Body", source="user")
    assert store.delete_note(session.session_id, note["note_id"]) is True

    with pytest.raises(MemoryStoreError, match="Note not found or deleted"):
        store.create_note_image(
            session.session_id,
            note["note_id"],
            image_bytes=b"\x89PNG\r\n\x1a\n",
            mime_type="image/png",
        )
