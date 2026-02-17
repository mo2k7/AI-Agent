"""System prompt management for the macOS autonomous assistant.

This module provides:
1) strict loading of the base system prompt from knowledge-vault
2) runtime augmentation with the currently loaded tool belt
3) a single builder used by both CLI and IPC server flows
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Sequence


class SystemPromptLoadError(RuntimeError):
    """Raised when the system prompt cannot be loaded safely."""


def _default_prompt_path() -> Path:
    """Return the canonical system prompt path in the repository."""
    base_dir = Path(__file__).parent.parent
    return base_dir / "knowledge-vault" / "plans" / "system-prompt-v1.md"


def load_system_prompt(prompt_path: Optional[Path] = None) -> str:
    """Load the system prompt from a file.
    
    Args:
        prompt_path: Optional path to a custom system prompt file.
                    If None, uses the canonical knowledge-vault prompt file.
    
    Returns:
        The system prompt as a string.

    Raises:
        SystemPromptLoadError: If prompt file is missing, unreadable, or empty.
    """
    if prompt_path is None:
        prompt_path = _default_prompt_path()

    if not prompt_path.exists():
        raise SystemPromptLoadError(
            f"System prompt file not found: {prompt_path}"
        )

    try:
        content = prompt_path.read_text(encoding="utf-8")
    except Exception as exc:
        raise SystemPromptLoadError(
            f"Failed to read system prompt file: {prompt_path}"
        ) from exc

    # Keep prompt body from identity section onward when present.
    if "## SYSTEM IDENTITY" in content:
        start_idx = content.find("## SYSTEM IDENTITY")
        if start_idx != -1:
            content = content[start_idx:]

    # Trim optional trailing metadata section.
    if "## VERSION INFORMATION" in content:
        end_idx = content.find("## VERSION INFORMATION")
        content = content[:end_idx]

    normalized = content.strip()
    if not normalized:
        raise SystemPromptLoadError(
            f"System prompt file is empty: {prompt_path}"
        )
    return normalized


def format_tool_belt(tools: Sequence[dict[str, Any]]) -> str:
    """Format the runtime tool list into prompt-ready guidance.

    Args:
        tools: Tool definitions produced by SchemaValidator.get_all_tools_for_gemini().

    Returns:
        Markdown-like text describing available tools and argument expectations.
    """
    if not tools:
        return (
            "## ACTIVE TOOL BELT\n\n"
            "No runtime tools are currently loaded.\n"
            "Respond with reasoning-only guidance and clearly explain that execution is unavailable."
        )

    lines: list[str] = [
        "## ACTIVE TOOL BELT",
        "",
        "Use only the tools listed below. Do not invent tool names or arguments.",
        "When a task requires execution, prefer these tools over free-form text.",
        "",
    ]

    sorted_tools = sorted(
        tools,
        key=lambda item: str(item.get("name", "")).lower(),
    )

    for tool in sorted_tools:
        name = str(tool.get("name", "")).strip() or "unknown_tool"
        description = str(tool.get("description", "")).strip() or "No description provided."
        parameters = tool.get("parameters", {}) if isinstance(tool.get("parameters"), dict) else {}
        properties = parameters.get("properties", {}) if isinstance(parameters.get("properties"), dict) else {}
        required_raw = parameters.get("required", [])
        required = [str(item) for item in required_raw] if isinstance(required_raw, list) else []
        optional = [key for key in properties.keys() if key not in required]

        required_text = ", ".join(required) if required else "none"
        optional_text = ", ".join(optional) if optional else "none"

        lines.append(f"- `{name}`: {description}")
        lines.append(f"  Required args: {required_text}")
        lines.append(f"  Optional args: {optional_text}")

    lines.extend(
        [
            "",
            "## TOOL SELECTION RULES",
            "",
            "1. If user intent maps cleanly to one tool, call that tool directly.",
            "2. If task requires multiple tools, chain them in a minimal safe sequence.",
            "3. Never use broad destructive operations without explicit user confirmation.",
            "4. If required arguments are missing, ask only for the missing fields.",
            "5. If a request is out of tool scope, explain limits and offer alternatives.",
            "",
            "## SEARCH TOOL BEST PRACTICES",
            "",
            "When calling `search_files`, always translate user intent into structured parameters:",
            "- Use `extensions` to specify file types: e.g., user says 'photos' → extensions: [\"jpg\", \"jpeg\", \"heic\", \"png\"]",
            "- Use `folder_hint` for known locations: e.g., user says 'in my downloads' → folder_hint: \"downloads\"",
            "- Use `path_filter` for path substring matching",
            "- The `query` field should contain the specific filename or content search term, NOT the full natural language request",
            "- Strip filler words from the query — pass only meaningful search tokens",
            "- When the user mentions a file type category (documents, images, code, etc.), always provide the corresponding `extensions` array",
        ]
    )

    return "\n".join(lines)


def build_system_prompt(
    tools: Optional[Sequence[dict[str, Any]]] = None,
    prompt_path: Optional[Path] = None,
) -> str:
    """Build the full runtime system prompt.

    Args:
        tools: Optional runtime tool definitions.
        prompt_path: Optional custom prompt path.

    Returns:
        Base system prompt augmented with runtime tool-belt guidance.
    """
    base_prompt = load_system_prompt(prompt_path=prompt_path).strip()
    if not tools:
        return base_prompt
    return f"{base_prompt}\n\n---\n\n{format_tool_belt(tools)}"


def inject_model_identity(
    base_prompt: str,
    model_name: str,
    *,
    verbosity: int | None = None,
    presentation_style: str | None = None,
    deep_think: bool = False,
) -> str:
    """Prepend a MODEL IDENTITY block and optional verbosity override.

    This is called per-request with the model name extracted from the
    incoming IPC/CLI request.  The base prompt is built once at startup
    and cached; only the identity header and verbosity changes per request.

    Args:
        base_prompt: The cached system prompt (with tool belt already appended).
        model_name:  Gemini model identifier, e.g. ``gemini-2.0-flash``.
        verbosity:   Optional verbosity level override (0-3).
        presentation_style: Optional response presentation style selected by UI.

    Returns:
        Full system instruction string with identity and verbosity blocks prepended.
    """
    header_parts: list[str] = []

    if model_name and model_name.strip():
        header_parts.append(
            f"## MODEL IDENTITY\n\n"
            f"You are currently running as **{model_name.strip()}**.\n"
            f"When asked which model or version you are, respond truthfully with this identifier.\n"
            f"Do not guess or fabricate model names.\n"
        )

    if verbosity is not None and isinstance(verbosity, int) and 0 <= verbosity <= 3:
        runtime_rubric = _runtime_verbosity_rubric(verbosity)
        header_parts.append(
            f"## ACTIVE VERBOSITY LEVEL\n\n"
            f"Current verbosity: **V{verbosity}**\n"
            f"Apply the V{verbosity} constraints from the VERBOSITY CONTRACT section.\n"
            f"Do not exceed section, bullet, or word limits for this level.\n"
            f"{runtime_rubric}\n"
        )

    style_rubric = _runtime_presentation_rubric(presentation_style)
    if style_rubric:
        header_parts.append(
            "## ACTIVE PRESENTATION STYLE\n\n"
            f"{style_rubric}\n"
        )

    if deep_think:
        header_parts.append(
            "## ACTIVE REASONING MODE\n\n"
            "Current mode: **DEEP THINK**\n"
            f"{_runtime_deep_think_rubric()}\n"
        )

    if not header_parts:
        return base_prompt

    header = "\n\n".join(header_parts)
    return f"{header}\n\n{base_prompt}"


def _runtime_verbosity_rubric(verbosity: int) -> str:
    """Return hard runtime constraints to increase level separation.

    These constraints are additive to the prompt's VERBOSITY CONTRACT and are
    injected per request so High and Extra High produce visibly different output.
    """
    if verbosity <= 0:
        return (
            "Runtime checklist:\n"
            "- Keep response short and direct.\n"
            "- Output 3-6 bullets total.\n"
            "- Do not include rationale, alternatives, or verification steps.\n"
        )
    if verbosity == 1:
        return (
            "Runtime checklist:\n"
            "- Use 1-3 short sections.\n"
            "- Keep explanations compact.\n"
            "- Include at most one brief follow-up action.\n"
        )
    if verbosity == 2:
        return (
            "Runtime checklist (mandatory for V2):\n"
            "- Use 2-4 sections with concise practical detail.\n"
            "- Include rationale and at least one edge case when relevant.\n"
            "- Focus on one primary approach; include at most one brief alternative.\n"
            "- Do NOT include dedicated sections titled Alternatives, Pitfalls, Verification, or Recommendation.\n"
        )
    return (
        "Runtime checklist (mandatory for V3):\n"
        "- Use 5-8 clearly labeled sections.\n"
        "- Include dedicated sections with these headings: Summary, Alternatives, Pitfalls, Verification, Recommendation.\n"
        "- In Alternatives, compare at least two viable options with tradeoffs.\n"
        "- In Pitfalls, list concrete failure modes and mitigations.\n"
        "- In Verification, include explicit test/check steps.\n"
        "- End with Recommendation as the final section.\n"
    )


def _runtime_presentation_rubric(presentation_style: str | None) -> str:
    """Return optional style-aware output guidance."""
    if not isinstance(presentation_style, str):
        return ""
    normalized = presentation_style.strip().lower()
    if normalized == "glass_editorial":
        return (
            "Current style: **glass_editorial**\n"
            "Render with polished section titles, short lead paragraph, and visually distinct callouts."
        )
    if normalized == "dense_technical":
        return (
            "Current style: **dense_technical**\n"
            "Favor compact technical structure: terse headings, high signal bullets, and minimal decorative wording."
        )
    if normalized == "readable_pro":
        return (
            "Current style: **readable_pro**\n"
            "Prioritize clear hierarchy, concise paragraphs, and scannable bullets."
        )
    return ""


def _runtime_deep_think_rubric() -> str:
    """Return runtime guardrails for deeper multi-step reasoning."""
    return (
        "Runtime checklist (mandatory):\n"
        "- Spend additional internal reasoning effort before answering.\n"
        "- Explicitly identify assumptions and uncertainties.\n"
        "- Evaluate at least one alternative path before final recommendation.\n"
        "- Verify your final answer against the request constraints.\n"
        "- Keep the visible answer concise, clear, and actionable."
    )


def get_system_prompt(prompt_path: Optional[Path] = None) -> str:
    """Get the current base system prompt without runtime tool injection."""
    return load_system_prompt(prompt_path=prompt_path)
