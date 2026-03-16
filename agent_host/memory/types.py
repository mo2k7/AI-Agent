"""Typed models for session and semantic memory management.

Canonical definitions now live in ``agent_host.contracts.types.domain``.
This module re-exports them for backward compatibility — all existing
imports from ``agent_host.memory.types`` continue to work.
"""

from agent_host.contracts.types.domain import (  # noqa: F401
    MemoryMode,
    MemoryKind,
    SessionRecord,
    MemoryCandidate,
    MemoryRecord,
    MemoryHit,
    MemoryContextBundle,
    SessionMessage,
)

__all__ = [
    "MemoryMode",
    "MemoryKind",
    "SessionRecord",
    "MemoryCandidate",
    "MemoryRecord",
    "MemoryHit",
    "MemoryContextBundle",
    "SessionMessage",
]
