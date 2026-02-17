"""Unit tests for memory manager session behaviors."""

from __future__ import annotations

import base64
import time

import pytest

from agent_host.memory import keychain as keychain_module
from agent_host.memory.manager import MemoryManager
from agent_host.memory.types import MemoryMode


class _StubEmbeddingService:
    def embed(self, *_args, **_kwargs):
        return tuple([0.1] * 8)


def test_create_session_default_name_uses_session_number_date(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"z" * 32).decode("ascii"),
    )
    manager = MemoryManager(tmp_path / "memory")

    today = time.strftime("%Y%m%d")
    first = manager.create_session(memory_mode=MemoryMode.ON)
    second = manager.create_session(memory_mode=MemoryMode.ON)

    assert first.title == f"session_1_{today}"
    assert second.title == f"session_2_{today}"


def test_list_session_messages_raises_for_unknown_session(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"y" * 32).decode("ascii"),
    )
    manager = MemoryManager(tmp_path / "memory")

    with pytest.raises(ValueError, match="Unknown session"):
        manager.list_session_messages("unknown-session")


def test_list_memories_and_delete_raise_for_unknown_session(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"u" * 32).decode("ascii"),
    )
    manager = MemoryManager(tmp_path / "memory")

    with pytest.raises(ValueError, match="Unknown session"):
        manager.list_memories("unknown-session")

    with pytest.raises(ValueError, match="Unknown session"):
        manager.delete_memory("unknown-session", "memory-1")


def test_set_session_mode_updates_existing_session_and_rejects_unknown(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"v" * 32).decode("ascii"),
    )
    manager = MemoryManager(tmp_path / "memory")
    session = manager.create_session(memory_mode=MemoryMode.ON)
    manager.set_embedding_service(_StubEmbeddingService())

    updated = manager.set_session_mode(session.session_id, memory_mode=MemoryMode.EPHEMERAL)
    assert updated.memory_mode == MemoryMode.EPHEMERAL

    with pytest.raises(ValueError, match="Unknown session"):
        manager.set_session_mode("unknown-session", memory_mode=MemoryMode.ON)


def test_record_interaction_persists_transcript_when_memory_off(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"x" * 32).decode("ascii"),
    )
    manager = MemoryManager(tmp_path / "memory")
    session = manager.create_session(memory_mode=MemoryMode.OFF)

    manager.record_interaction(
        session_id=session.session_id,
        memory_mode=MemoryMode.OFF,
        user_prompt="Hello there",
        assistant_response="Hi! How can I help?",
        model_name="gemini-3-flash-preview",
    )

    history = manager.list_session_messages(session.session_id, limit=20)
    assert [entry["role"] for entry in history] == ["user", "assistant"]
    assert [entry["content"] for entry in history] == ["Hello there", "Hi! How can I help?"]
    assert manager.list_memories(session.session_id, limit=20) == []


def test_record_interaction_persists_transcript_when_memory_ephemeral(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"w" * 32).decode("ascii"),
    )
    manager = MemoryManager(tmp_path / "memory")
    session = manager.create_session(memory_mode=MemoryMode.EPHEMERAL)

    manager.record_interaction(
        session_id=session.session_id,
        memory_mode=MemoryMode.EPHEMERAL,
        user_prompt="Remember this only for now",
        assistant_response="Understood for this runtime.",
        model_name="gemini-3-flash-preview",
    )

    history = manager.list_session_messages(session.session_id, limit=20)
    assert [entry["role"] for entry in history] == ["user", "assistant"]
    assert [entry["content"] for entry in history] == [
        "Remember this only for now",
        "Understood for this runtime.",
    ]
    assert manager.list_memories(session.session_id, limit=20) == []


def test_prepare_prompt_context_includes_relevant_historical_turns(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"q" * 32).decode("ascii"),
    )
    manager = MemoryManager(tmp_path / "memory")
    session = manager.create_session(memory_mode=MemoryMode.ON)

    # Record the target interaction early so it falls outside the recent window.
    manager.record_interaction(
        session_id=session.session_id,
        memory_mode=MemoryMode.ON,
        user_prompt="Remember that my launch codename is AtlasBeacon",
        assistant_response="Stored your codename as AtlasBeacon.",
        model_name="gemini-3-flash-preview",
    )

    # Add enough filler turns to push the target interaction out of the
    # recent window (list_recent_messages limit=20 means 20 messages = 10 turns).
    for i in range(10):
        manager.record_interaction(
            session_id=session.session_id,
            memory_mode=MemoryMode.ON,
            user_prompt=f"Filler topic number {i}",
            assistant_response=f"Acknowledged filler {i}.",
            model_name="gemini-3-flash-preview",
        )

    prepared = manager.prepare_prompt_context(
        session_id=session.session_id,
        prompt="What was the AtlasBeacon codename again?",
        memory_mode=MemoryMode.ON,
    )

    assert "[SESSION_ARCHIVE_CONTEXT]" in prepared.augmented_prompt
    assert "AtlasBeacon" in prepared.augmented_prompt


def test_list_session_messages_sanitizes_json_assistant_content(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"p" * 32).decode("ascii"),
    )
    manager = MemoryManager(tmp_path / "memory")
    session = manager.create_session(memory_mode=MemoryMode.OFF)

    manager.record_interaction(
        session_id=session.session_id,
        memory_mode=MemoryMode.OFF,
        user_prompt="show me status",
        assistant_response='{"status":"ok","count":2}',
        model_name="gemini-3-flash-preview",
    )

    history = manager.list_session_messages(session.session_id, limit=20)
    assistant_entries = [entry for entry in history if entry["role"] == "assistant"]
    assert assistant_entries
    rendered = str(assistant_entries[0]["content"])
    assert "readable summary" in rendered
    assert "\"status\"" not in rendered


def test_delete_sessions_removes_multiple_sessions_and_returns_summary(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"m" * 32).decode("ascii"),
    )
    manager = MemoryManager(tmp_path / "memory")
    first = manager.create_session(memory_mode=MemoryMode.ON)
    second = manager.create_session(memory_mode=MemoryMode.ON)
    third = manager.create_session(memory_mode=MemoryMode.ON)

    deleted, failed = manager.delete_sessions([first.session_id, second.session_id])

    assert deleted == [first.session_id, second.session_id]
    assert failed == {}
    remaining = {session.session_id for session in manager.list_sessions(limit=10)}
    assert third.session_id in remaining
    assert first.session_id not in remaining
    assert second.session_id not in remaining


def test_delete_sessions_skips_empty_ids_and_is_idempotent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"n" * 32).decode("ascii"),
    )
    manager = MemoryManager(tmp_path / "memory")
    session = manager.create_session(memory_mode=MemoryMode.ON)

    deleted_once, failed_once = manager.delete_sessions(["", "   ", session.session_id])
    deleted_twice, failed_twice = manager.delete_sessions([session.session_id])

    assert deleted_once == [session.session_id]
    assert failed_once == {}
    assert deleted_twice == [session.session_id]
    assert failed_twice == {}


def test_memory_manager_requires_keychain_when_unavailable(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(keychain_module, "_load_from_keychain", lambda: None)
    monkeypatch.setattr(keychain_module, "_security_available", lambda: False)

    with pytest.raises(RuntimeError, match="Keychain is required"):
        MemoryManager(tmp_path / "memory")


def test_note_operations_reject_unknown_session_without_creating_session_db(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"b" * 32).decode("ascii"),
    )
    manager = MemoryManager(tmp_path / "memory")
    unknown_session = "unknown-session"
    session_db_path = manager.store._session_db_path(unknown_session)
    assert not session_db_path.exists()

    with pytest.raises(ValueError, match="Unknown session"):
        manager.list_notes(unknown_session)
    with pytest.raises(ValueError, match="Unknown session"):
        manager.delete_note(unknown_session, "note-1")
    with pytest.raises(ValueError, match="Unknown session"):
        manager.get_note_image(unknown_session, "image-1")
    with pytest.raises(ValueError, match="Unknown session"):
        manager.list_note_versions(unknown_session, "note-1")

    assert not session_db_path.exists()
