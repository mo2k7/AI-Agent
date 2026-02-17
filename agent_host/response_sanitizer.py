"""Utilities to normalize model text into user-friendly markdown.

These helpers enforce a hard guardrail: if the model returns a raw JSON
payload, it is converted into readable markdown before it is shown or stored.
"""

from __future__ import annotations

import json
from typing import Any

_MAX_JSON_INPUT_CHARS = 200_000
_MAX_SECTION_ITEMS = 8
_MAX_BULLETS = 12
_MAX_TOP_LEVEL_FIELDS = 12
_MAX_LIST_ITEMS = 20
_MAX_VALUE_CHARS = 220


def looks_like_json_payload(text: str) -> bool:
    """Fast pre-check used to avoid unnecessary parsing work."""
    candidate = text.lstrip()
    if not candidate:
        return False
    if candidate.startswith("{") or candidate.startswith("["):
        return True
    if candidate.startswith("```json") or candidate.startswith("```JSON"):
        return True
    if candidate.startswith("```"):
        # Some models wrap JSON in plain code fences without language tag.
        snippet = candidate[:40].lower()
        return "{" in snippet or "[" in snippet
    return False


def sanitize_user_visible_response(text: str) -> str:
    """Convert raw JSON model text into readable markdown.

    If ``text`` is not raw JSON, it is returned unchanged.
    """
    if not looks_like_json_payload(text):
        return text

    payload = _parse_json_text(text)
    if payload is None:
        return text

    rendered = _render_payload(payload)
    return rendered.strip() or text


def _parse_json_text(text: str) -> Any | None:
    candidate = text.strip()
    if not candidate:
        return None

    if len(candidate) > _MAX_JSON_INPUT_CHARS:
        return None

    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if len(lines) >= 3 and lines[0].strip().startswith("```") and lines[-1].strip() == "```":
            candidate = "\n".join(lines[1:-1]).strip()

    if not candidate or candidate[0] not in "{[":
        return None

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def _render_payload(payload: Any) -> str:
    if isinstance(payload, dict) and _looks_like_structured_contract(payload):
        contract_rendered = _render_structured_contract(payload)
        if contract_rendered:
            return contract_rendered

    if isinstance(payload, dict):
        return _render_generic_mapping(payload)
    if isinstance(payload, list):
        return _render_generic_list(payload, heading="Results")
    return _to_text(payload)


def _looks_like_structured_contract(payload: dict[str, Any]) -> bool:
    sections = payload.get("sections")
    return isinstance(sections, list) and (
        isinstance(payload.get("summary"), str)
        or isinstance(payload.get("title"), str)
        or isinstance(payload.get("next_actions"), list)
    )


def _render_structured_contract(payload: dict[str, Any]) -> str:
    lines: list[str] = []

    summary = _clean_text(payload.get("summary"))
    title = _clean_text(payload.get("title"))
    if summary:
        lines.append(summary)
    elif title:
        lines.append(title)

    if title and (not summary or title.lower() != summary.lower()):
        lines.extend(["", f"## {title}"])

    sections = payload.get("sections")
    if isinstance(sections, list):
        for section in sections[:_MAX_SECTION_ITEMS]:
            if not isinstance(section, dict):
                continue
            heading = _clean_text(section.get("heading"))
            content = _clean_text(section.get("content"))
            bullets = section.get("bullets")
            code = section.get("code")

            if heading:
                lines.extend(["", f"## {heading}"])
            elif content or bullets or code:
                lines.extend(["", "## Details"])

            if content:
                lines.append(content)

            if isinstance(bullets, list):
                for bullet in bullets[:_MAX_BULLETS]:
                    bullet_text = _clean_text(bullet)
                    if bullet_text:
                        lines.append(f"- {bullet_text}")

            if isinstance(code, list):
                for snippet in code[:2]:
                    snippet_text = _clean_text(snippet)
                    if snippet_text:
                        lines.append(f"- Example: {snippet_text}")

    next_actions = payload.get("next_actions")
    if isinstance(next_actions, list):
        actionable = [item for item in (_clean_text(entry) for entry in next_actions[:10]) if item]
        if actionable:
            lines.extend(["", "## Next Actions"])
            for item in actionable:
                lines.append(f"- {item}")

    return "\n".join(lines).strip()


def _render_generic_mapping(payload: dict[str, Any]) -> str:
    if not payload:
        return "I produced a structured result, but it contained no readable fields."

    lines = ["I converted a structured payload into a readable summary:", ""]
    keys = list(payload.keys())
    for key in keys[:_MAX_TOP_LEVEL_FIELDS]:
        pretty_key = str(key).replace("_", " ").strip() or "value"
        lines.append(f"- **{pretty_key}**: {_render_fallback_value(payload.get(key))}")
    if len(keys) > _MAX_TOP_LEVEL_FIELDS:
        lines.append(f"- ... {len(keys) - _MAX_TOP_LEVEL_FIELDS} more field(s) omitted.")
    return "\n".join(lines)


def _render_generic_list(payload: list[Any], *, heading: str) -> str:
    lines = [f"## {heading}"]
    if not payload:
        lines.append("- No items.")
        return "\n".join(lines)

    for index, item in enumerate(payload[:_MAX_LIST_ITEMS], start=1):
        if isinstance(item, (dict, list)):
            compact = _render_payload(item)
            compact_line = _single_line(compact)
            lines.append(f"{index}. {compact_line}")
        else:
            lines.append(f"{index}. {_to_text(item)}")

    if len(payload) > _MAX_LIST_ITEMS:
        lines.append(f"- ... {len(payload) - _MAX_LIST_ITEMS} more item(s) omitted.")

    return "\n".join(lines)

def _to_text(value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        cleaned = _clean_text(value)
        return cleaned if cleaned else "(empty)"
    return _single_line(str(value))


def _single_line(value: str) -> str:
    return " ".join(part for part in value.splitlines() if part.strip()).strip() or "(empty)"


def _render_fallback_value(value: Any) -> str:
    if isinstance(value, dict):
        keys = list(value.keys())
        preview = ", ".join(str(k) for k in keys[:5])
        if len(keys) > 5:
            preview += ", …"
        return f"{{{preview}}}" if preview else "{}"
    if isinstance(value, list):
        if not value:
            return "[]"
        preview = ", ".join(_to_text(item) for item in value[:5])
        if len(value) > 5:
            preview += ", …"
        return f"[{preview}]"
    rendered = _to_text(value)
    if len(rendered) > _MAX_VALUE_CHARS:
        return f"{rendered[:_MAX_VALUE_CHARS]}…"
    return rendered


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = value.strip()
    if not cleaned:
        return ""
    return cleaned.replace("\r\n", "\n")
