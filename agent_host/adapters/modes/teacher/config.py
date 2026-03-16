"""Single source of truth for teacher mode constants.

These values are the canonical defaults for note type, tags, and the
set of tool names that count as "note captured" in teacher mode.
All other modules (registry, manage_notes, etc.) should import from here.
"""

from __future__ import annotations

TEACHER_DEFAULT_NOTE_TYPE: str = "study_guide"

TEACHER_DEFAULT_NOTE_TAGS: tuple[str, ...] = (
    "teacher-mode",
    "autonomous",
    "key-highlights",
)

TEACHER_NOTE_COMPLETION_TOOLS: frozenset[str] = frozenset({"manage_notes"})
