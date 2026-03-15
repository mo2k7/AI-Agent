"""Unit tests for secure session/semantic memory storage."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag

import agent_host.memory.store as store_module
from agent_host.memory.crypto import compute_hmac
from agent_host.memory.store import MemoryStore, MemoryStoreError
from agent_host.memory.types import MemoryKind, MemoryMode


def _build_store(tmp_path) -> MemoryStore:
    return MemoryStore(root_dir=tmp_path / "memory-store", master_key=b"m" * 32)


class _TrackingConnection(sqlite3.Connection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.closed_explicitly = False

    def close(self) -> None:
        self.closed_explicitly = True
        super().close()


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

    with store._db_connection() as conn:
        conn.execute(
            "UPDATE semantic_memories SET policy_flags_json = ? WHERE memory_id = ?",
            ('["quarantine"]', memory.memory_id),
        )

    with pytest.raises(MemoryStoreError, match="HMAC verification failed"):
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

    with store._db_connection() as conn:
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


def test_list_messages_page_returns_latest_and_older_windows(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Paged Session", memory_mode=MemoryMode.ON)

    for index in range(10):
        store.append_message(session.session_id, role="user", content=f"m{index}")

    latest, latest_has_older = store.list_messages_page(
        session.session_id,
        direction="latest",
        limit=4,
    )
    assert [message.content for message in latest] == ["m6", "m7", "m8", "m9"]
    assert [message.turn_index for message in latest] == [6, 7, 8, 9]
    assert latest_has_older is True

    older, older_has_older = store.list_messages_page(
        session.session_id,
        direction="older",
        anchor_turn_index=latest[0].turn_index,
        limit=4,
    )
    assert [message.content for message in older] == ["m2", "m3", "m4", "m5"]
    assert [message.turn_index for message in older] == [2, 3, 4, 5]
    assert older_has_older is True

    oldest, oldest_has_older = store.list_messages_page(
        session.session_id,
        direction="older",
        anchor_turn_index=older[0].turn_index,
        limit=4,
    )
    assert [message.content for message in oldest] == ["m0", "m1"]
    assert [message.turn_index for message in oldest] == [0, 1]
    assert oldest_has_older is False


def test_rename_session_updates_title(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Initial Name", memory_mode=MemoryMode.ON)

    renamed = store.rename_session(session.session_id, title="Renamed Session")

    assert renamed.session_id == session.session_id
    assert renamed.title == "Renamed Session"





def test_validate_session_deks_closes_direct_sqlite_connections(tmp_path, monkeypatch) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Close Tracking", memory_mode=MemoryMode.ON)
    store.append_message(
        session.session_id,
        role="user",
        content="Keep this session alive.",
    )

    original_connect = sqlite3.connect
    opened: list[_TrackingConnection] = []

    def tracking_connect(*args, **kwargs):
        kwargs["factory"] = _TrackingConnection
        conn = original_connect(*args, **kwargs)
        opened.append(conn)
        return conn

    monkeypatch.setattr(store_module.sqlite3, "connect", tracking_connect)
    monkeypatch.setattr(
        store._master_box,
        "unwrap_key",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(InvalidTag()),
    )

    store._validate_session_deks()

    assert opened
    assert all(conn.closed_explicitly for conn in opened)


def test_list_sessions_self_heals_invalid_memory_mode_values(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Mode Repair", memory_mode=MemoryMode.ON)

    # Tamper with the mode AND recompute the HMAC so the integrity check
    # passes but the invalid mode value still gets self-healed.
    # Read the raw updated_at from the DB to avoid float formatting mismatches.
    with store._db_connection() as conn:
        row = conn.execute(
            "SELECT updated_at FROM sessions WHERE session_id = ?",
            (session.session_id,),
        ).fetchone()
        raw_updated_at = row["updated_at"]
        hmac_for_tampered = compute_hmac(
            b"m" * 32,
            f"{session.session_id}|Mode Repair|broken_mode|{raw_updated_at}",
        )
        conn.execute(
            "UPDATE sessions SET memory_mode = ?, row_hmac = ? WHERE session_id = ?",
            ("broken_mode", hmac_for_tampered, session.session_id),
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

    with store._db_connection() as conn:
        conn.execute(
            """
            UPDATE messages
            SET content_enc = 'corrupted-payload'
            WHERE session_id = ? AND turn_index = 0
            """,
            (session.session_id,)
        )

    with pytest.raises(MemoryStoreError, match="Failed to decode message"):
        store.list_messages(session.session_id, limit=20)





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


def test_list_notes_backfills_session_pad_and_orders_it_first(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Pad Session", memory_mode=MemoryMode.ON)
    legacy = store.create_note(session.session_id, content="Legacy body", source="user")

    notes = store.list_notes(session.session_id)

    assert len(notes) >= 2
    assert notes[0]["is_default_tab"] is True
    assert notes[0]["workspace_kind"] == "session_pad"
    assert notes[0]["title"] == "Session Notes"
    assert any(note["note_id"] == legacy["note_id"] for note in notes)


def test_delete_note_rejects_session_pad(tmp_path) -> None:
    store = _build_store(tmp_path)
    session = store.create_session(title="Protected Pad", memory_mode=MemoryMode.ON)
    session_pad = store.get_or_create_session_pad(session.session_id)

    with pytest.raises(MemoryStoreError, match="Cannot delete the session pad"):
        store.delete_note(session.session_id, session_pad["note_id"])





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
