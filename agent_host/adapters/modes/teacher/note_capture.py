"""Helper to build structured study notes for teacher mode auto-capture.

This is the simplified version used by the TeacherModeHandler's
``post_generation_hook`` when the model did not produce a note itself.
The more detailed version (with student question, highlights, etc.)
lives in ``agent_host.tools._helpers._build_teacher_note_body``.
"""

from __future__ import annotations


def build_teacher_note_body(response_text: str) -> str:
    """Structure the raw model output into a formatted study note."""
    return (
        f"# Teacher Mode Auto-Note\n\n"
        f"{response_text}\n\n"
        f"---\n"
        f"*Note automatically captured during teacher mode session.*\n"
    )
