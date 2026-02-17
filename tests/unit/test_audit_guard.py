"""Audit logging fail-closed startup tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_host import main as main_module
from agent_host.audit_logger import AuditLogError


@pytest.mark.asyncio
async def test_run_server_fails_when_audit_logging_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingAuditLogger:
        def __init__(self, _path: Path) -> None:
            raise AuditLogError("audit init failed")

    monkeypatch.setattr(main_module, "AuditLogger", FailingAuditLogger)

    config = SimpleNamespace(
        audit_log_path=Path("/tmp/test-audit.log"),
        model_name="gemini-2.0-flash-exp",
    )
    result = await main_module.run_server(config)  # type: ignore[arg-type]
    assert result == main_module.EXIT_CONFIG_ERROR


def test_main_fails_when_audit_logging_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSchemaValidator:
        def __init__(self, _schemas_dir: Path) -> None:
            pass

        def get_all_tools_for_gemini(self) -> list[dict[str, object]]:
            return [{"name": "search_files", "description": "desc", "parameters": {}}]

    class FakeToolExecutor:
        @classmethod
        def from_config(cls, _config: object) -> object:
            return object()

    class FailingAuditLogger:
        def __init__(self, _path: Path) -> None:
            raise AuditLogError("audit init failed")

    fake_config = SimpleNamespace(
        gemini_api_key="test-key",
        model_name="gemini-2.0-flash-exp",
        schemas_dir=Path("schemas"),
        audit_log_path=Path("/tmp/test-audit.log"),
        max_retries=1,
        retry_delay=0.1,
        memory_root=Path("/tmp/ai-agent-memory"),
        allowed_roots=[Path("/tmp")],
        automations_dir=Path("/tmp"),
        require_no_training=False,
        use_vertexai=False,
        vertex_project=None,
        vertex_location="us-central1",
    )

    class FakeConfigClass:
        @staticmethod
        def from_env(*_args: object, **_kwargs: object) -> object:
            return fake_config

    monkeypatch.setattr(main_module, "Config", FakeConfigClass)
    monkeypatch.setattr(main_module, "SchemaValidator", FakeSchemaValidator)
    monkeypatch.setattr(main_module, "MemoryManager", lambda _root: object())
    monkeypatch.setattr(main_module, "ToolExecutor", FakeToolExecutor)
    monkeypatch.setattr(main_module, "AuditLogger", FailingAuditLogger)

    result = main_module.main(["hello"])
    assert result == main_module.EXIT_CONFIG_ERROR


@pytest.mark.asyncio
async def test_run_server_fails_when_embedding_service_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class WorkingAuditLogger:
        def __init__(self, _path: Path) -> None:
            pass

        def log_event(self, _event: object, _payload: dict[str, object]) -> None:
            pass

        def log_error(self, _error_type: str, _message: str) -> None:
            pass

    class FakeSchemaValidator:
        def __init__(self, _schemas_dir: Path) -> None:
            pass

        def get_all_tools_for_gemini(self) -> list[dict[str, object]]:
            return [{"name": "search_files", "description": "desc", "parameters": {}}]

    class FakeToolExecutor:
        @classmethod
        def from_config(cls, _config: object) -> object:
            return object()

    class FakeGeminiClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self._client = object()

    class FailingEmbeddingService:
        def __init__(self, _client: object) -> None:
            raise RuntimeError("embedding init failed")

    config = SimpleNamespace(
        gemini_api_key="test-key",
        model_name="gemini-2.0-flash-exp",
        schemas_dir=Path("schemas"),
        audit_log_path=Path("/tmp/test-audit.log"),
        max_retries=1,
        retry_delay=0.1,
        memory_root=Path("/tmp/ai-agent-memory"),
        allowed_roots=[Path("/tmp")],
        automations_dir=Path("/tmp"),
        require_no_training=False,
        use_vertexai=False,
        vertex_project=None,
        vertex_location="us-central1",
    )

    monkeypatch.setattr(main_module, "AuditLogger", WorkingAuditLogger)
    monkeypatch.setattr(main_module, "SchemaValidator", FakeSchemaValidator)
    monkeypatch.setattr(main_module, "MemoryManager", lambda _root: object())
    monkeypatch.setattr(main_module, "ToolExecutor", FakeToolExecutor)
    monkeypatch.setattr(main_module, "GeminiClient", FakeGeminiClient)
    monkeypatch.setattr(main_module, "EmbeddingService", FailingEmbeddingService)

    result = await main_module.run_server(config)  # type: ignore[arg-type]
    assert result == main_module.EXIT_CONFIG_ERROR


def test_main_fails_when_embedding_service_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSchemaValidator:
        def __init__(self, _schemas_dir: Path) -> None:
            pass

        def get_all_tools_for_gemini(self) -> list[dict[str, object]]:
            return [{"name": "search_files", "description": "desc", "parameters": {}}]

    class FakeToolExecutor:
        @classmethod
        def from_config(cls, _config: object) -> object:
            return object()

    class WorkingAuditLogger:
        def __init__(self, _path: Path) -> None:
            pass

        def log_event(self, _event: object, _payload: dict[str, object]) -> None:
            pass

        def log_error(self, _error_type: str, _message: str) -> None:
            pass

    class FakeGeminiClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self._client = object()

    class FailingEmbeddingService:
        def __init__(self, _client: object) -> None:
            raise RuntimeError("embedding init failed")

    fake_config = SimpleNamespace(
        gemini_api_key="test-key",
        model_name="gemini-2.0-flash-exp",
        schemas_dir=Path("schemas"),
        audit_log_path=Path("/tmp/test-audit.log"),
        max_retries=1,
        retry_delay=0.1,
        memory_root=Path("/tmp/ai-agent-memory"),
        allowed_roots=[Path("/tmp")],
        automations_dir=Path("/tmp"),
        require_no_training=False,
        use_vertexai=False,
        vertex_project=None,
        vertex_location="us-central1",
    )

    class FakeConfigClass:
        @staticmethod
        def from_env(*_args: object, **_kwargs: object) -> object:
            return fake_config

    monkeypatch.setattr(main_module, "Config", FakeConfigClass)
    monkeypatch.setattr(main_module, "SchemaValidator", FakeSchemaValidator)
    monkeypatch.setattr(main_module, "MemoryManager", lambda _root: object())
    monkeypatch.setattr(main_module, "ToolExecutor", FakeToolExecutor)
    monkeypatch.setattr(main_module, "AuditLogger", WorkingAuditLogger)
    monkeypatch.setattr(main_module, "GeminiClient", FakeGeminiClient)
    monkeypatch.setattr(main_module, "EmbeddingService", FailingEmbeddingService)

    result = main_module.main(["hello"])
    assert result == main_module.EXIT_CONFIG_ERROR
