"""Tests for the contracts layer (Ring 1).

Verifies that all types, error hierarchy, events, and port protocols
work correctly and maintain their zero-dependency invariant.
"""

from __future__ import annotations

import ast
import time
from pathlib import Path
from typing import Any, Mapping

import pytest

from agent_host.contracts.types.result import Result, Success, Failure
from agent_host.contracts.types.errors import AgentError, ErrorCode, ErrorSeverity
from agent_host.contracts.types.events import (
    Event,
    ToolExecutionStarted,
    ToolExecutionCompleted,
    PromptReceived,
    PromptCompleted,
    SessionCreated,
    SessionDeleted,
    NoteCreated,
    NoteUpdated,
    NoteDeleted,
    ErrorOccurred,
    HealthCheckCompleted,
)
from agent_host.contracts.types.domain import (
    ExecutionMode,
    MemoryMode,
    MemoryKind,
    SessionRecord,
    MemoryCandidate,
    MemoryRecord,
    MemoryHit,
    MemoryContextBundle,
    SessionMessage,
    ClarificationIntentResult,
    PreparedPrompt,
)
from agent_host.contracts.ports import (
    AuditPort,
    EventBus,
    IPCPort,
    LLMProvider,
    MemoryPort,
    ModeHandler,
    NLPClassifierPort,
    PlanStore,
    ToolPlugin,
)


# ── contracts directory path (for import-rule tests) ──────────────
CONTRACTS_DIR = Path(__file__).resolve().parent.parent.parent / "agent_host" / "contracts"


# =========================================================================
# Result[T] tests
# =========================================================================


class TestSuccess:
    def test_is_ok(self):
        s = Success(42)
        assert s.is_ok is True
        assert s.is_err is False

    def test_value(self):
        s = Success("hello")
        assert s.value == "hello"

    def test_unwrap(self):
        assert Success(99).unwrap() == 99

    def test_unwrap_or(self):
        assert Success(10).unwrap_or(0) == 10

    def test_map(self):
        result = Success(5).map(lambda x: x * 2)
        assert isinstance(result, Success)
        assert result.value == 10

    def test_flat_map_to_success(self):
        result = Success(3).flat_map(lambda x: Success(x + 1))
        assert isinstance(result, Success)
        assert result.value == 4

    def test_flat_map_to_failure(self):
        err = AgentError(ErrorCode.TIMEOUT, "oops")
        result = Success(3).flat_map(lambda _: Failure(err))
        assert isinstance(result, Failure)
        assert result.error is err

    def test_frozen(self):
        s = Success(1)
        with pytest.raises(AttributeError):
            s.value = 2  # type: ignore[misc]


class TestFailure:
    def test_is_err(self):
        f = Failure(AgentError(ErrorCode.INTERNAL, "bad"))
        assert f.is_ok is False
        assert f.is_err is True

    def test_unwrap_raises(self):
        f = Failure(AgentError(ErrorCode.NOT_FOUND, "missing"))
        with pytest.raises(ValueError, match="Failure"):
            f.unwrap()

    def test_unwrap_or(self):
        f = Failure(AgentError(ErrorCode.TIMEOUT, "slow"))
        assert f.unwrap_or(42) == 42

    def test_map_is_noop(self):
        err = AgentError(ErrorCode.VALIDATION, "invalid")
        f = Failure(err)
        result = f.map(lambda x: x * 2)
        assert isinstance(result, Failure)
        assert result.error is err

    def test_flat_map_is_noop(self):
        err = AgentError(ErrorCode.CANCELLED, "cancelled")
        f = Failure(err)
        result = f.flat_map(lambda x: Success(x))
        assert isinstance(result, Failure)
        assert result.error is err

    def test_frozen(self):
        f = Failure("error")
        with pytest.raises(AttributeError):
            f.error = "other"  # type: ignore[misc]


# =========================================================================
# AgentError tests
# =========================================================================


class TestAgentError:
    def test_basic_creation(self):
        err = AgentError(ErrorCode.TIMEOUT, "request timed out")
        assert err.code == ErrorCode.TIMEOUT
        assert err.message == "request timed out"
        assert err.retryable is False
        assert err.severity == ErrorSeverity.ERROR
        assert err.source == ""
        assert err.context == {}

    def test_with_all_fields(self):
        err = AgentError(
            code=ErrorCode.RATE_LIMITED,
            message="too many requests",
            source="gemini_adapter",
            retryable=True,
            severity=ErrorSeverity.WARNING,
            context={"retry_after": 30},
        )
        assert err.retryable is True
        assert err.source == "gemini_adapter"
        assert err.context["retry_after"] == 30

    def test_with_context(self):
        err = AgentError(ErrorCode.INTERNAL, "oops", context={"a": 1})
        enriched = err.with_context(b=2, c=3)
        assert enriched.context == {"a": 1, "b": 2, "c": 3}
        # Original unchanged (frozen)
        assert err.context == {"a": 1}

    def test_frozen(self):
        err = AgentError(ErrorCode.INTERNAL, "test")
        with pytest.raises(AttributeError):
            err.code = ErrorCode.TIMEOUT  # type: ignore[misc]


class TestErrorCode:
    def test_all_values_are_strings(self):
        for code in ErrorCode:
            assert isinstance(code.value, str)

    def test_expected_codes_exist(self):
        expected = {
            "validation", "not_found", "permission", "timeout",
            "rate_limited", "configuration", "dependency",
            "internal", "cancelled", "transient",
        }
        actual = {c.value for c in ErrorCode}
        assert expected == actual


# =========================================================================
# Event tests
# =========================================================================


class TestEvent:
    def test_base_event_defaults(self):
        before = time.time()
        e = Event(event_type="test.event")
        after = time.time()
        assert e.event_type == "test.event"
        assert before <= e.timestamp <= after
        assert len(e.correlation_id) == 16
        assert e.source == ""
        assert e.payload == {}

    def test_custom_fields(self):
        e = Event(
            event_type="tool.started",
            source="executor",
            correlation_id="abc123",
            payload={"tool": "search_files"},
        )
        assert e.source == "executor"
        assert e.correlation_id == "abc123"
        assert e.payload["tool"] == "search_files"

    def test_subclasses_are_events(self):
        subclasses = [
            ToolExecutionStarted, ToolExecutionCompleted,
            PromptReceived, PromptCompleted,
            SessionCreated, SessionDeleted,
            NoteCreated, NoteUpdated, NoteDeleted,
            ErrorOccurred, HealthCheckCompleted,
        ]
        for cls in subclasses:
            e = cls(event_type=f"test.{cls.__name__}")
            assert isinstance(e, Event)
            assert e.event_type == f"test.{cls.__name__}"


# =========================================================================
# Domain type tests
# =========================================================================


class TestExecutionMode:
    def test_values(self):
        assert ExecutionMode.DIRECT == "direct"
        assert ExecutionMode.PLAN == "plan"
        assert ExecutionMode.TEACHER == "teacher"

    def test_is_str(self):
        assert isinstance(ExecutionMode.DIRECT, str)


class TestMemoryMode:
    def test_values(self):
        assert MemoryMode.ON == "on"
        assert MemoryMode.OFF == "off"
        assert MemoryMode.EPHEMERAL == "ephemeral"


class TestMemoryKind:
    def test_values(self):
        assert MemoryKind.PREFERENCE == "preference"
        assert MemoryKind.PROFILE_FACT == "profile_fact"


class TestSessionRecord:
    def test_creation(self):
        sr = SessionRecord(
            session_id="s1",
            title="Test",
            memory_mode=MemoryMode.ON,
            created_at=1.0,
            updated_at=2.0,
            last_activity=3.0,
        )
        assert sr.session_id == "s1"
        assert sr.status == "active"
        assert sr.store_version == 0

    def test_frozen(self):
        sr = SessionRecord(
            session_id="s1", title="T", memory_mode=MemoryMode.ON,
            created_at=1.0, updated_at=2.0, last_activity=3.0,
        )
        with pytest.raises(AttributeError):
            sr.title = "Changed"  # type: ignore[misc]


class TestSessionMessage:
    def test_creation(self):
        sm = SessionMessage(
            message_id="m1", role="user", content="hello",
            created_at=1.0, turn_index=0,
        )
        assert sm.role == "user"
        assert sm.meta == {}

    def test_with_meta(self):
        sm = SessionMessage(
            message_id="m2", role="assistant", content="hi",
            created_at=2.0, turn_index=1, meta={"model": "gemini"},
        )
        assert sm.meta["model"] == "gemini"


class TestClarificationIntentResult:
    def test_creation(self):
        r = ClarificationIntentResult(
            is_clarification_reply=True,
            confidence=0.9,
            source="builtin",
            model_name="spacy",
            sanitized_reply="yes",
            sanitized_root_prompt="do X",
        )
        assert r.is_clarification_reply is True
        assert r.confidence == 0.9


class TestPreparedPrompt:
    def test_creation(self):
        bundle = MemoryContextBundle(session_id="s1")
        pp = PreparedPrompt(augmented_prompt="enriched prompt", context_bundle=bundle)
        assert pp.augmented_prompt == "enriched prompt"
        assert pp.context_bundle.session_id == "s1"


# =========================================================================
# Backward compatibility tests
# =========================================================================


class TestBackwardCompat:
    """Verify re-export shims resolve to the same class objects."""

    def test_memory_types_reexport(self):
        from agent_host.memory.types import MemoryMode as MT_MM
        from agent_host.contracts.types.domain import MemoryMode as CT_MM
        assert MT_MM is CT_MM

    def test_memory_types_session_record(self):
        from agent_host.memory.types import SessionRecord as MT_SR
        from agent_host.contracts.types.domain import SessionRecord as CT_SR
        assert MT_SR is CT_SR

    def test_execution_mode_reexport(self):
        from agent_host.main import ExecutionMode as Main_EM
        from agent_host.contracts.types.domain import ExecutionMode as CT_EM
        assert Main_EM is CT_EM

    def test_isinstance_across_paths(self):
        from agent_host.memory.types import MemoryMode
        from agent_host.contracts.types.domain import MemoryMode as DomainMM
        val = MemoryMode.ON
        assert isinstance(val, DomainMM)


# =========================================================================
# Protocol (port) tests
# =========================================================================


class TestProtocolsAreRuntimeCheckable:
    """All port protocols must be @runtime_checkable for isinstance checks."""

    @pytest.mark.parametrize("protocol", [
        AuditPort, EventBus, IPCPort, LLMProvider, MemoryPort,
        ModeHandler, NLPClassifierPort, PlanStore, ToolPlugin,
    ])
    def test_runtime_checkable(self, protocol):
        # runtime_checkable protocols can be used with isinstance
        assert not isinstance(42, protocol)


class TestToolPluginProtocol:
    """Verify a concrete class can satisfy the ToolPlugin protocol."""

    def test_satisfies_protocol(self):
        class FakeTool:
            @property
            def name(self) -> str:
                return "fake_tool"

            @property
            def description(self) -> str:
                return "A fake tool"

            @property
            def input_schema(self) -> dict[str, Any]:
                return {"type": "object"}

            def execute(self, arguments: Mapping[str, Any]) -> Result:
                return Success({"ok": True})

            def health_check(self) -> Result:
                return Success(True)

        tool = FakeTool()
        assert isinstance(tool, ToolPlugin)
        result = tool.execute({"query": "test"})
        assert result.is_ok
        assert result.value == {"ok": True}


class TestModeHandlerProtocol:
    """Verify a concrete class can satisfy the ModeHandler protocol."""

    def test_satisfies_protocol(self):
        class FakeMode:
            @property
            def name(self) -> str:
                return "fake"

            def get_system_prompt_addition(self) -> str:
                return "fake mode"

            def filter_active_tools(self, available_tools):
                return available_tools

            def get_timeout_multiplier(self) -> float:
                return 1.0

            async def pre_generation_hook(self, **kwargs) -> bool | None:
                return False

            async def post_generation_hook(self, response_text: str, **kwargs) -> None:
                pass

            def should_show_tool_call_card(self) -> bool:
                return True

            def get_chain_status_message(self, chain_depth: int) -> str | None:
                return None

            def get_pre_generation_status_message(self) -> str | None:
                return None

        mode = FakeMode()
        assert isinstance(mode, ModeHandler)


# =========================================================================
# Import rule enforcement tests
# =========================================================================


class TestImportRules:
    """Verify contracts layer has ZERO imports from outer layers."""

    def _get_python_files(self) -> list[Path]:
        """Collect all .py files in the contracts directory."""
        return list(CONTRACTS_DIR.rglob("*.py"))

    def _extract_imports(self, filepath: Path) -> list[str]:
        """Extract all import module paths from a Python file."""
        source = filepath.read_text()
        tree = ast.parse(source)
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    modules.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    modules.append(node.module)
        return modules

    def test_no_imports_from_outer_layers(self):
        """Contracts must not import from core/, adapters/, or main.py."""
        violations = []
        for filepath in self._get_python_files():
            modules = self._extract_imports(filepath)
            for mod in modules:
                if mod.startswith("agent_host.") and not mod.startswith("agent_host.contracts"):
                    rel = filepath.relative_to(CONTRACTS_DIR)
                    violations.append(f"{rel} imports {mod}")
        assert violations == [], f"Import violations:\n" + "\n".join(violations)

    def test_no_external_framework_imports(self):
        """Contracts must not import external frameworks (google, spacy, etc.)."""
        forbidden = {"google", "spacy", "beautifulsoup4", "bs4", "websockets", "cryptography"}
        violations = []
        for filepath in self._get_python_files():
            modules = self._extract_imports(filepath)
            for mod in modules:
                top_level = mod.split(".")[0]
                if top_level in forbidden:
                    rel = filepath.relative_to(CONTRACTS_DIR)
                    violations.append(f"{rel} imports {mod}")
        assert violations == [], f"Framework import violations:\n" + "\n".join(violations)
