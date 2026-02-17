"""Regression tests for memory-store corruption handling and recovery paths."""

from __future__ import annotations

import base64
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from agent_host.memory.manager import MemoryManager
from agent_host.memory.store import MemoryStoreError
from agent_host.memory.types import MemoryMode


class _StubEmbeddingService:
    def embed(self, *_args, **_kwargs):
        return tuple([0.1] * 8)


def _set_master_key(monkeypatch) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"k" * 32).decode("ascii"),
    )


def test_corrupted_session_db_is_quarantined_and_interactions_continue(tmp_path, monkeypatch) -> None:
    _set_master_key(monkeypatch)
    manager = MemoryManager(tmp_path / "memory")
    manager.set_embedding_service(_StubEmbeddingService())
    session = manager.create_session(memory_mode=MemoryMode.ON)

    manager.record_interaction(
        session_id=session.session_id,
        memory_mode=MemoryMode.ON,
        user_prompt="first prompt",
        assistant_response="first answer",
        model_name="gemini-3-flash-preview",
    )

    session_db = manager.store._session_db_path(session.session_id)
    session_db.write_text("not-a-real-sqlite-database")

    manager.record_interaction(
        session_id=session.session_id,
        memory_mode=MemoryMode.ON,
        user_prompt="second prompt",
        assistant_response="second answer",
        model_name="gemini-3-flash-preview",
    )

    history = manager.list_session_messages(session.session_id, limit=50)
    contents = [entry["content"] for entry in history]
    assert "second prompt" in contents
    assert "second answer" in contents

    quarantined = list(session_db.parent.glob(f"{session_db.name}.corrupt-*"))
    assert quarantined, "Expected corrupted session DB to be quarantined."


def test_corrupted_index_db_is_quarantined_on_reinit(tmp_path, monkeypatch) -> None:
    _set_master_key(monkeypatch)
    root = tmp_path / "memory"
    manager = MemoryManager(root)
    created = manager.create_session(memory_mode=MemoryMode.ON)

    index_db = manager.store.index_db_path
    index_db.write_text("broken-index-db")
    Path(f"{index_db}-wal").unlink(missing_ok=True)
    Path(f"{index_db}-shm").unlink(missing_ok=True)

    recovered_manager = MemoryManager(root)
    recovered_sessions = recovered_manager.list_sessions(limit=20)
    assert len(recovered_sessions) == 1
    assert recovered_sessions[0].session_id == created.session_id

    recreated = recovered_manager.create_session(memory_mode=MemoryMode.ON)
    assert recreated.session_id

    quarantined = list(index_db.parent.glob(f"{index_db.name}.corrupt-*"))
    assert quarantined, "Expected corrupted index DB to be quarantined."


def test_manager_history_listing_fails_on_corrupted_message_rows(tmp_path, monkeypatch) -> None:
    _set_master_key(monkeypatch)
    manager = MemoryManager(tmp_path / "memory")
    manager.set_embedding_service(_StubEmbeddingService())
    session = manager.create_session(memory_mode=MemoryMode.ON)

    manager.record_interaction(
        session_id=session.session_id,
        memory_mode=MemoryMode.ON,
        user_prompt="keep this safe",
        assistant_response="stored response",
        model_name="gemini-3-flash-preview",
    )

    session_db = manager.store._session_db_path(session.session_id)
    with closing(sqlite3.connect(session_db)) as conn:
        conn.execute(
            """
            UPDATE messages
            SET content_enc = 'bad-ciphertext'
            WHERE turn_index = 0
            """
        )
        conn.commit()

    with pytest.raises(MemoryStoreError, match="Failed to decode message"):
        manager.list_session_messages(session.session_id, limit=20)
