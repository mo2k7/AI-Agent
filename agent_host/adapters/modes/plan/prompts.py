"""Prompt templates for Plan Mode.

Moved from ``agent_host/modes/plan/prompts.py`` -- identical logic,
no external dependencies.
"""

from __future__ import annotations


def get_plan_mode_header(
    is_followup: bool,
    requires_unified_planning: bool,
    discovery_budget: int,
) -> str:
    """Returns the pre-prompt headers for Plan Mode."""
    if is_followup:
        return (
            "## PLAN MODE -- Conversation Follow-up\n\n"
            "Current mode: **PLAN** (responding to an existing plan).\n\n"
            "The user is responding to a plan you previously produced in this session.\n"
            "Check [RECENT_SESSION_CONTEXT] for the full conversation history.\n"
            "Respond conversationally to their follow-up:\n"
            "- If they confirm/approve, summarize the next concrete steps.\n"
            "- If they ask to revise, adjust the plan.\n"
            "- If they ask a question, answer it in context.\n"
            "- If they reference notes (e.g. 'elaborate on the notes', 'make them detailed'),\n"
            "  use the [SESSION_NOTES] section in the prompt -- the notes are already there.\n"
            "  Do NOT call `read_screen` or `search_files` to find note content.\n"
            "  Use `manage_notes` to modify or add notes directly.\n"
            "Do NOT restart the planning process. Do NOT ask clarification questions.\n"
            "Only call `plan_ops` if they explicitly request a revised or new plan.\n"
        )

    header = (
        "## EXECUTION MODE\n\n"
        "Current mode: **PLAN**.\n"
        "This mode is planning-only. Unified-planning context is preloaded.\n\n"
        "**MANDATORY**: You MUST produce a structured plan by calling `plan_ops`.\n"
        "Workflow: (1) optionally gather context with discovery tools, then "
        "(2) call `plan_ops` to create the phased execution plan.\n"
        "NEVER return only discovery results or empty text without a plan.\n"
        "Your text response must be a human-readable plan summary -- not raw tool output.\n\n"
        "Blend advanced planning rigor with concise, user-friendly communication.\n"
        "Make assumptions explicit and easy to revise.\n"
        "Do not execute destructive tools in this mode (`apply_ops`).\n"
    )

    if requires_unified_planning:
        header += (
            "This prompt indicates actionable file-operations.\n"
            "Use unified planning via `planner`/`plan_ops` early.\n"
            "Limit pre-planning discovery calls (`search_files`, "
            "`read_document`) to "
            f"{discovery_budget} before producing a plan.\n"
        )

    return header


def get_auto_exec_header() -> str:
    """Returns the pre-prompt header for Auto Execute / Approved Plan transitions."""
    return (
        "## EXECUTION MODE -- Plan Approved\n\n"
        "Current mode: **DIRECT** (auto-switched from plan after user approval).\n\n"
        "The user approved a plan you previously produced in this session.\n"
        "Check [RECENT_SESSION_CONTEXT] for the plan and conversation history.\n"
        "Execute the plan now using all available tools.\n"
        "Start with the first concrete step. Be safe and confirm destructive actions.\n"
        "Report progress as you go.\n"
    )


def normalize_plan_mode_banner(text: str) -> str:
    """Ensures consistent markdown banners for plan mode overrides."""
    lines = text.split("\n")
    if lines and not lines[0].startswith("### "):
        lines[0] = f"### {lines[0]}"
    return "\n".join(lines).strip()
