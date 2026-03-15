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





def test_corrupted_db_is_quarantined_on_reinit(tmp_path, monkeypatch) -> None:
    _set_master_key(monkeypatch)
    root = tmp_path / "memory"
    manager = MemoryManager(root)
    created = manager.create_session(memory_mode=MemoryMode.ON)

    db_path = manager.store.db_path
    db_path.write_text("broken-index-db")
    Path(f"{db_path}-wal").unlink(missing_ok=True)
    Path(f"{db_path}-shm").unlink(missing_ok=True)

    recovered_manager = MemoryManager(root)
    recovered_sessions = recovered_manager.list_sessions(limit=20)
    assert len(recovered_sessions) == 0

    recreated = recovered_manager.create_session(memory_mode=MemoryMode.ON)
    assert recreated.session_id

    quarantined = list(db_path.parent.glob(f"{db_path.name}.corrupt-*"))
    assert quarantined, "Expected corrupted DB to be quarantined."


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

    with manager.store._db_connection() as conn:
        conn.execute(
            """
            UPDATE messages
            SET content_enc = 'bad-ciphertext'
            WHERE session_id = ? AND turn_index = 0
            """,
            (session.session_id,)
        )

    with pytest.raises(MemoryStoreError, match="Failed to decode message"):
        manager.list_session_messages(session.session_id, limit=20)
