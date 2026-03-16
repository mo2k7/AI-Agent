"""Core domain types and value objects.

These types are used across the entire system.  They are defined in the
contracts layer (Ring 1) so all other layers can depend on them without
creating import cycles.

Note: ``MemoryMode``, ``SessionRecord``, etc. are *redefined* here
rather than imported from ``memory.types`` to maintain the contracts
layer's zero-dependency invariant.  ``memory.types`` will be updated
to re-export from here for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Execution mode
# ---------------------------------------------------------------------------


class ExecutionMode(str, Enum):
    """Prompt execution behavior mode selected by the UI."""

    DIRECT = "direct"
    PLAN = "plan"
    TEACHER = "teacher"


# ---------------------------------------------------------------------------
# Memory types (canonical definitions -- memory/types.py re-exports these)
# ---------------------------------------------------------------------------


class MemoryMode(str, Enum):
    """Controls how memory is used for a prompt/session."""

    ON = "on"
    OFF = "off"
    EPHEMERAL = "ephemeral"


class MemoryKind(str, Enum):
    """Semantic memory categories."""

    PREFERENCE = "preference"
    PROFILE_FACT = "profile_fact"
    TASK_STATE = "task_state"
    ARTIFACT_REFERENCE = "artifact_reference"


@dataclass(frozen=True)
class SessionRecord:
    """Persisted session metadata."""

    session_id: str
    title: str
    memory_mode: MemoryMode
    created_at: float
    updated_at: float
    last_activity: float
    status: str = "active"
    store_version: int = 0


@dataclass(frozen=True)
class MemoryCandidate:
    """Candidate semantic memory extracted from a turn."""

    kind: MemoryKind
    fact_key: str
    content: str
    confidence: float
    source_role: str
    trust_flags: tuple[str, ...] = ()
    policy_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class MemoryRecord:
    """Stored semantic memory with provenance."""

    memory_id: str
    session_id: str
    kind: MemoryKind
    fact_key: str
    content: str
    confidence: float
    source_message_id: str
    trust_flags: tuple[str, ...]
    policy_flags: tuple[str, ...]
    created_at: float
    updated_at: float


@dataclass(frozen=True)
class MemoryHit:
    """Retrieval result used for memory context composition."""

    memory_id: str
    session_id: str
    kind: MemoryKind
    content: str
    confidence: float
    score: float
    trust_flags: tuple[str, ...]
    policy_flags: tuple[str, ...]


@dataclass(frozen=True)
class MemoryContextBundle:
    """Context assembled from prior memory before model invocation."""

    session_id: str
    recent_turns: tuple[tuple[str, str], ...] = ()
    historical_turns: tuple[tuple[str, str], ...] = ()
    summary: str = ""
    semantic_hits: tuple[MemoryHit, ...] = ()


@dataclass(frozen=True)
class SessionMessage:
    """Persisted chat turn."""

    message_id: str
    role: str
    content: str
    created_at: float
    turn_index: int
    meta: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Clarification intent result (used by NLP port)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClarificationIntentResult:
    """Result returned by clarification-reply intent analysis."""

    is_clarification_reply: bool
    confidence: float
    source: str
    model_name: str
    sanitized_reply: str
    sanitized_root_prompt: str


# ---------------------------------------------------------------------------
# Prepared prompt (used by memory port)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Tool name constants
# ---------------------------------------------------------------------------

NOTE_TOOL_NAMES: frozenset[str] = frozenset({"manage_notes", "generate_image"})


@dataclass(frozen=True)
class PreparedPrompt:
    """Result of prompt context preparation by the memory port."""

    augmented_prompt: str
    context_bundle: MemoryContextBundle
