"""Tests for system prompt loading and runtime tool-belt injection."""

from pathlib import Path

import pytest

from agent_host.system_prompt import (
    SystemPromptLoadError,
    build_system_prompt,
    format_tool_belt,
    inject_model_identity,
    load_system_prompt,
)


def test_format_tool_belt_lists_required_and_optional_args() -> None:
    tools = [
        {
            "name": "search_files",
            "description": "Find files based on metadata or content",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "path": {"type": "string"},
                },
                "required": ["query"],
            },
        }
    ]

    text = format_tool_belt(tools)

    assert "ACTIVE TOOL BELT" in text
    assert "`search_files`" in text
    assert "Required args: query" in text
    assert "Optional args: path" in text


def test_format_tool_belt_includes_tool_routing_playbook_for_loaded_tools() -> None:
    tools = [
        {
            "name": "search_files",
            "description": "Find files based on metadata or content",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
        {
            "name": "read_document",
            "description": "Extract text from documents",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "mode": {"type": "string"}}},
        },
        {
            "name": "browse_web",
            "description": "Browse and extract content from web pages",
            "parameters": {"type": "object", "properties": {"url": {"type": "string"}}},
        },
        {
            "name": "apply_ops",
            "description": "Execute a previously planned operation",
            "parameters": {"type": "object", "properties": {"plan_id": {"type": "string"}}, "required": ["plan_id"]},
        },
    ]

    text = format_tool_belt(tools)

    assert "TOOL ROUTING PLAYBOOK" in text
    assert "CONVERSATION-FIRST RULES" in text
    assert "If the conversation context already answers the request, do not call a tool." in text
    assert "Use `search_files` to discover candidate local paths" in text
    assert "Use `read_document` to inspect files" in text
    assert "Use `browse_web` only for web content" in text
    assert "If the user explicitly asks you to look up, verify, browse, search online, or get the latest/current web information" in text
    assert "Do not use `browse_web` just to restate, reformat, or continue an existing conversation." in text
    assert "Do not answer time-sensitive web questions from memory first" in text
    assert "Use `apply_ops` only when a concrete plan already exists" in text
    assert "TOOL CHOICE ANTI-PATTERNS" in text
    assert "Do not treat every follow-up as a new research task." in text
    assert "Do not answer latest/current web questions from stale memory" in text


def test_build_system_prompt_preserves_base_tool_routing_contract(tmp_path: Path) -> None:
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text(
        "## SYSTEM IDENTITY\n\nBase body\n\n## TOOL ROUTING CONTRACT\n\nUse tools by execution stage.\n",
        encoding="utf-8",
    )

    built = build_system_prompt(tools=[], prompt_path=prompt_path)

    assert "## TOOL ROUTING CONTRACT" in built
    assert "Use tools by execution stage." in built


def test_build_system_prompt_appends_runtime_tool_catalog(tmp_path: Path) -> None:
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("## SYSTEM IDENTITY\nBase prompt body", encoding="utf-8")

    tools = [
        {
            "name": "read_document",
            "description": "Read text content from a file",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        }
    ]

    built = build_system_prompt(tools=tools, prompt_path=prompt_path)

    assert "Base prompt body" in built
    assert "ACTIVE TOOL BELT" in built
    assert "`read_document`" in built


def test_build_system_prompt_without_tools_uses_base_prompt(tmp_path: Path) -> None:
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("## SYSTEM IDENTITY\nOnly base", encoding="utf-8")

    base = load_system_prompt(prompt_path=prompt_path)
    built = build_system_prompt(tools=None, prompt_path=prompt_path)

    assert built == base


def test_load_system_prompt_raises_when_file_missing(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing-system-prompt.md"
    with pytest.raises(SystemPromptLoadError):
        load_system_prompt(prompt_path=missing_path)


def test_load_system_prompt_raises_when_file_empty(tmp_path: Path) -> None:
    empty_prompt = tmp_path / "empty-prompt.md"
    empty_prompt.write_text("   \n\n", encoding="utf-8")
    with pytest.raises(SystemPromptLoadError):
        load_system_prompt(prompt_path=empty_prompt)


def test_default_system_prompt_routes_notes_to_session_pad() -> None:
    prompt = load_system_prompt()
    assert "`Session Notes` pad" in prompt
    assert "Do NOT create a separate tab unless the user explicitly asks for one." in prompt
    assert "Do not turn ordinary follow-up questions into fresh searches." in prompt


def test_inject_model_identity_includes_requested_verbosity_level() -> None:
    base = "## SYSTEM IDENTITY\nBase body"

    rendered = inject_model_identity(
        base,
        "gemini-3-flash-preview",
        verbosity=2,
    )

    assert "MODEL IDENTITY" in rendered
    assert "gemini-3-flash-preview" in rendered
    assert "ACTIVE VERBOSITY LEVEL" in rendered
    assert "Current verbosity: **V2**" in rendered
    assert "Runtime checklist (mandatory for V2)" in rendered
    assert "Do NOT include dedicated sections titled Alternatives, Pitfalls, Verification, or Recommendation." in rendered


def test_inject_model_identity_ignores_invalid_verbosity() -> None:
    base = "Base body"
    rendered = inject_model_identity(base, "gemini-3-flash-preview", verbosity=99)
    assert "ACTIVE VERBOSITY LEVEL" not in rendered


def test_inject_model_identity_includes_v3_runtime_checklist() -> None:
    base = "## SYSTEM IDENTITY\nBase body"
    rendered = inject_model_identity(base, "gemini-3-flash-preview", verbosity=3)

    assert "Runtime checklist (mandatory for V3)" in rendered
    assert "compare at least two viable options with tradeoffs" in rendered
    assert "explicit test/check steps" in rendered
    assert "Summary, Alternatives, Pitfalls, Verification, Recommendation" in rendered


def test_inject_model_identity_includes_active_presentation_style_guidance() -> None:
    base = "## SYSTEM IDENTITY\nBase body"
    rendered = inject_model_identity(
        base,
        "gemini-3-flash-preview",
        verbosity=1,
        presentation_style="glass_editorial",
    )

    assert "ACTIVE PRESENTATION STYLE" in rendered
    assert "Current style: **glass_editorial**" in rendered
    assert "visually distinct callouts" in rendered
