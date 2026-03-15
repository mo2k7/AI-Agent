TEACHER_DEFAULT_NOTE_TYPE = "study"
TEACHER_DEFAULT_NOTE_TAGS = ["auto-generated", "teacher-mode"]
TEACHER_NOTE_COMPLETION_TOOLS = {"manage_notes", "plan_ops"}

def _build_teacher_note_body(response_text: str) -> str:
    """Helper to structure the raw output into a formatted study note."""
    return (
        f"# Teacher Mode Auto-Note\n\n"
        f"{response_text}\n\n"
        f"---\n"
        f"*Note automatically captured during teacher mode session.*\n"
    )
