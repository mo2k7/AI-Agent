"""Markdown formatters for tool execution output.

Each tool type has a dedicated formatter that converts raw execution
dictionaries into clean, human-readable markdown.  The primary entry
point is ``format_tool_execution_output`` which dispatches to the
correct per-tool formatter.

The Python backend is the **primary** formatter.  The Swift
``ToolResultFormatter`` acts as a defensive fallback only.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def format_tool_execution_output(
    tool_name: str,
    execution: dict[str, object],
) -> tuple[str, str]:
    """Build user-facing content + concise summary for executed tools.

    Args:
        tool_name: The canonical tool name (e.g. ``search_files``).
        execution: The full execution dict returned by ``ToolExecutor.execute``.

    Returns:
        A ``(content, summary)`` tuple where *content* is the full markdown
        and *summary* is a truncated version suitable for status notifications.
    """
    normalized = str(tool_name).strip().lower()
    execution_tool = str(execution.get("tool", "")).strip().lower()
    if normalized != execution_tool and execution_tool:
        normalized = execution_tool

    output = _extract_output_dict(execution)

    formatter = _FORMATTERS.get(normalized)
    if formatter is not None:
        return formatter(output, execution)

    # Fallback: provide readable markdown instead of raw JSON.
    return _format_unknown_tool(normalized or "unknown_tool", execution)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_output_dict(execution: dict[str, object]) -> dict[str, object]:
    """Normalise the ``output`` field to a dict."""
    output = execution.get("output")
    if isinstance(output, dict):
        return output
    if isinstance(output, str):
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError:
            parsed = None
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _format_unknown_tool(
    tool_name: str,
    execution: dict[str, object],
) -> tuple[str, str]:
    ok_value = execution.get("ok")
    status = "succeeded" if ok_value is True else "did not complete successfully"
    error_text = str(execution.get("error", "")).strip()
    output = _extract_output_dict(execution)

    lines = [
        f"**Tool Execution Result**: `{tool_name}`",
        "",
        f"- Status: {status}",
    ]

    if error_text:
        lines.append(f"- Error: {error_text}")

    if output:
        lines.append("- Output highlights:")
        for key, value in list(output.items())[:8]:
            rendered_value = _render_fallback_value(value)
            lines.append(f"  - **{key}**: {rendered_value}")
        if len(output) > 8:
            lines.append(f"  - ... {len(output) - 8} more field(s) omitted")
    else:
        lines.append("- Output: no structured fields were returned.")

    content = "\n".join(lines)
    return content, content[:1200]


def _render_fallback_value(value: object) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return "(empty)"
        return text if len(text) <= 200 else f"{text[:200]}…"
    if isinstance(value, list):
        if not value:
            return "[]"
        preview = ", ".join(_render_fallback_value(item) for item in value[:5])
        if len(value) > 5:
            return f"[{preview}, …] ({len(value)} items)"
        return f"[{preview}]"
    if isinstance(value, dict):
        keys = list(value.keys())
        preview = ", ".join(str(key) for key in keys[:5])
        if len(keys) > 5:
            preview += ", …"
        return f"{{{preview}}}"
    try:
        serialized = json.dumps(value, ensure_ascii=False)
    except Exception:
        serialized = str(value)
    serialized = serialized.strip()
    return serialized if len(serialized) <= 200 else f"{serialized[:200]}…"


def _human_size(size_bytes: object) -> str:
    """Convert bytes to a human-readable string."""
    if isinstance(size_bytes, bool):
        return "—"
    if not isinstance(size_bytes, (int, float, str, bytes, bytearray)):
        return "—"
    try:
        raw = int(size_bytes)
    except (TypeError, ValueError):
        return "—"
    if raw < 0:
        return "—"
    n = float(raw)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


def _ts_to_str(ts: object) -> str:
    """Convert a Unix timestamp to a human-readable date string."""
    try:
        value = float(ts)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "—"
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(value))
    except (OSError, OverflowError, ValueError):
        return "—"


def _compact_warning_line(warnings: object, *, limit: int = 1) -> str:
    if not isinstance(warnings, list):
        return ""
    normalized = [
        str(item).strip()
        for item in warnings
        if str(item).strip()
    ]
    if not normalized:
        return ""
    visible = normalized[:max(1, limit)]
    summary = " | ".join(visible)
    if len(summary) > 180:
        summary = summary[:177].rstrip() + "..."
    remaining = len(normalized) - len(visible)
    if remaining > 0:
        summary += f" (+{remaining} more)"
    return summary


# ---------------------------------------------------------------------------
# Per-tool formatters
# ---------------------------------------------------------------------------

def _format_search_files(
    output: dict[str, object],
    execution: dict[str, object],
) -> tuple[str, str]:
    query = str(output.get("query", "")).strip()
    matches = output.get("matches")
    match_rows = matches if isinstance(matches, list) else []

    if not match_rows:
        message = (
            "No files found."
            + (f" Query: {query}." if query else "")
            + " Try a more specific filename, extension, or folder keyword."
        )
        return message, message

    lines = [f"Found {len(match_rows)} matching file(s). Click any link to open it:"]
    rendered = 0
    for item in match_rows[:20]:
        if not isinstance(item, dict):
            continue
        path_raw = str(item.get("path", "")).strip()
        if not path_raw:
            continue

        path_obj = Path(path_raw).expanduser()
        if not path_obj.is_absolute():
            path_obj = (Path.cwd() / path_obj).resolve(strict=False)
        else:
            path_obj = path_obj.resolve(strict=False)

        label_raw = str(item.get("name", "")).strip() or path_obj.name or str(path_obj)
        label = label_raw.replace("[", r"\[").replace("]", r"\]")
        path_display = str(item.get("display_path", "")).strip() or str(path_obj)
        path_literal = path_display.replace("`", r"\`")

        file_uri_raw = item.get("uri")
        file_uri = str(file_uri_raw).strip() if isinstance(file_uri_raw, str) else ""
        if not file_uri:
            try:
                file_uri = path_obj.as_uri()
            except ValueError:
                file_uri = ""

        if file_uri:
            lines.append(f"- [{label}]({file_uri}) (`{path_literal}`)")
        else:
            lines.append(f"- `{path_literal}`")
        rendered += 1

    if rendered == 0:
        message = (
            "No files found."
            + (f" Query: {query}." if query else "")
            + " Try a more specific filename, extension, or folder keyword."
        )
        return message, message

    if bool(output.get("truncated")):
        reason = str(output.get("truncated_reason", "")).strip()
        if reason:
            lines.append(f"Search scan truncated: {reason}. Refine query for deeper results.")
        else:
            lines.append("Search scan reached the limit; refine query for deeper results.")
    scanned_entries = output.get("scanned_entries")
    if isinstance(scanned_entries, int):
        lines.append(f"Scanned entries: {scanned_entries}.")
    next_token = output.get("next_token")
    if isinstance(next_token, str) and next_token.strip():
        lines.append("More results are available. Ask for the next page to continue the search.")

    content = "\n".join(lines)
    summary = "\n".join(lines[:8])
    return content, summary


def _format_get_metadata(
    output: dict[str, object],
    execution: dict[str, object],
) -> tuple[str, str]:
    items = output.get("items")
    if not isinstance(items, list) or not items:
        return "No metadata available.", "No metadata available."

    sections: list[str] = [f"**File Metadata** for {len(items)} path(s):\n"]
    for item in items:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", "")).strip() or "—"
        exists = "Yes" if item.get("exists") else "No"
        is_file = item.get("is_file")
        is_dir = item.get("is_dir")
        ftype = "File" if is_file else ("Directory" if is_dir else "—")
        size = _human_size(item.get("size_bytes"))
        created = _ts_to_str(item.get("created_at"))
        modified = _ts_to_str(item.get("modified_at"))
        perms = str(item.get("permissions_octal", "—"))
        error = str(item.get("error", "")).strip()

        # Generate clickable file:// link
        path_obj = Path(path).expanduser()
        if not path_obj.is_absolute():
            path_obj = (Path.cwd() / path_obj).resolve(strict=False)
        else:
            path_obj = path_obj.resolve(strict=False)
        try:
            file_uri = path_obj.as_uri()
        except ValueError:
            file_uri = ""

        path_display = path
        label = path_obj.name or path
        if file_uri and exists == "Yes":
            sections.append(f"### [{label}]({file_uri})")
        else:
            sections.append(f"### `{path_display}`")

        sections.append("")
        sections.append("| Property | Value |")
        sections.append("|----------|-------|")
        sections.append(f"| Path | `{path}` |")
        sections.append(f"| Exists | {exists} |")
        if exists == "Yes":
            sections.append(f"| Type | {ftype} |")
            sections.append(f"| Size | {size} |")
            sections.append(f"| Created | {created} |")
            sections.append(f"| Modified | {modified} |")
            sections.append(f"| Permissions | {perms} |")
        if error:
            sections.append(f"| Error | {error} |")
        sections.append("")

    content = "\n".join(sections).rstrip()
    return content, content[:1200]


def _format_read_text(
    output: dict[str, object],
    execution: dict[str, object],
) -> tuple[str, str]:
    path = str(output.get("path", "")).strip() or "unknown"
    text_content = str(output.get("content", ""))
    byte_range = output.get("byte_range")
    range_str = ""
    if isinstance(byte_range, list) and len(byte_range) == 2:
        range_str = f" (bytes {byte_range[0]}–{byte_range[1]})"

    # Generate clickable link
    path_obj = Path(path).expanduser().resolve(strict=False)
    try:
        file_uri = path_obj.as_uri()
        path_link = f"[{path_obj.name}]({file_uri})"
    except ValueError:
        path_link = f"`{path}`"

    lines = [
        f"**File Content**: {path_link}{range_str}",
        "",
        "```",
        text_content,
        "```",
    ]
    content = "\n".join(lines)
    summary = content[:1200]
    return content, summary


def _format_extract_content(
    output: dict[str, object],
    execution: dict[str, object],
) -> tuple[str, str]:
    mode = str(output.get("mode", "text")).strip()
    path = str(output.get("path", "")).strip() or "unknown"
    text_content = str(output.get("content", ""))
    line_count = output.get("line_count")
    warning = str(output.get("warning", "")).strip()
    extraction_method = str(output.get("extraction_method", "")).strip()

    ext = Path(path).suffix.lstrip(".") if path != "unknown" else ""
    lang_hint = ext if ext else ""

    # Generate clickable link
    path_obj = Path(path).expanduser().resolve(strict=False)
    try:
        file_uri = path_obj.as_uri()
        path_link = f"[{path_obj.name}]({file_uri})"
    except ValueError:
        path_link = f"`{path}`"

    header = f"**Extracted Content** (mode: {mode}): {path_link}"
    if extraction_method:
        header += f" via {extraction_method}"
    if isinstance(line_count, int):
        header += f"\nLines: {line_count}"
    if warning:
        header += f"\n⚠️ {warning}"

    lines = [
        header,
        "",
        f"```{lang_hint}",
        text_content,
        "```",
    ]
    content = "\n".join(lines)
    return content, content[:1200]


def _format_plan_ops(
    output: dict[str, object],
    execution: dict[str, object],
) -> tuple[str, str]:
    plan_id = str(output.get("plan_id", execution.get("plan_id", ""))).strip()
    ops = output.get("ops")
    if not isinstance(ops, list):
        ops = []
    issues = output.get("issues")
    if not isinstance(issues, list):
        issues = []
    planner = output.get("planner")
    complexity = output.get("complexity")
    privacy = output.get("privacy")

    lines = [f"**Operation Plan** `{plan_id}`", ""]
    lines.append("| # | Op | Source | Destination | Policy | Valid |")
    lines.append("|---|-----|--------|-------------|--------|-------|")
    for idx, op in enumerate(ops):
        if not isinstance(op, dict):
            continue
        op_kind = str(op.get("op", "—"))
        src = str(op.get("src", "—"))
        dest = str(op.get("dest") or "—")
        overwrite_policy = str(op.get("overwrite_policy", "fail"))
        valid = "✅" if op.get("valid") else "❌"
        lines.append(
            f"| {idx + 1} | {op_kind} | {src} | {dest} | {overwrite_policy} | {valid} |"
        )

    lines.append("")
    if isinstance(planner, dict):
        lines.append(
            "Planner: "
            f"{planner.get('engine', 'unknown')} "
            f"{planner.get('engine_version', '')} "
            f"(status: {planner.get('status', 'unknown')})"
        )
    if isinstance(complexity, dict):
        lines.append(
            "Complexity: "
            f"{complexity.get('level', 'unknown')} "
            f"(score: {complexity.get('score', 'n/a')}, strategy: {complexity.get('strategy', 'n/a')})"
        )
    if isinstance(privacy, dict):
        lines.append(
            "Privacy: "
            f"path_data_sent_to_unified_planning={privacy.get('path_data_sent_to_unified_planning')} "
            f"network_disabled_during_planning={privacy.get('network_disabled_during_planning')} "
            f"boundary_payload_mode={privacy.get('boundary_payload_mode')} "
            f"policy_version={privacy.get('policy_version')} "
            f"planner_security_locked={privacy.get('planner_security_locked')} "
            f"policy_attestation_verified={privacy.get('policy_attestation_verified')} "
            f"package_hash_verified={privacy.get('package_hash_verified')} "
            f"package_hash_pinned={privacy.get('package_hash_pinned')} "
            f"package_hash_auto_rotate_enabled={privacy.get('package_hash_auto_rotate_enabled')}"
        )
    lines.append("")
    if issues:
        lines.append("Issues:")
        for issue in issues:
            lines.append(f"- {issue}")
    else:
        lines.append("Issues: none")

    content = "\n".join(lines)
    return content, content[:1200]


def _format_apply_ops(
    output: dict[str, object],
    execution: dict[str, object],
) -> tuple[str, str]:
    plan_id = str(execution.get("plan_id", output.get("plan_id", ""))).strip()
    applied = execution.get("applied", output.get("applied", 0))
    failed = execution.get("failed", output.get("failed", 0))
    skipped = execution.get("skipped", output.get("skipped", 0))
    replay = bool(execution.get("idempotent_replay", output.get("idempotent_replay", False)))
    results = execution.get("results", output.get("results"))
    if not isinstance(results, list):
        results = []

    lines = [
        f"**Operations Applied** — plan `{plan_id}`",
        f"Applied: {applied} | Failed: {failed} | Skipped: {skipped}",
        "",
    ]
    if replay:
        lines.append("Idempotency replay: returned cached result for this idempotency key.")
        lines.append("")
    for result in results:
        if not isinstance(result, dict):
            continue
        idx = result.get("index")
        if isinstance(idx, int) and idx >= 0:
            index_label = str(idx + 1)
        elif idx is None or str(idx).strip() == "":
            index_label = "?"
        else:
            index_label = str(idx)
        op_kind = str(result.get("op", "—"))
        ok = result.get("ok", False)
        skipped_entry = bool(result.get("skipped", False))
        src = str(result.get("src", "—"))
        dest = result.get("dest")
        error = str(result.get("error", "")).strip()
        delete_mode = str(result.get("delete_mode", "")).strip()
        overwrite_policy = str(result.get("overwrite_policy", "")).strip()
        overwrite_suffix = f" [policy: {overwrite_policy}]" if overwrite_policy else ""

        icon = "⏭️" if skipped_entry else ("✅" if ok else "❌")
        if skipped_entry:
            lines.append(f"{index_label}. {icon} **skipped** — {error}")
            continue
        if ok and dest:
            lines.append(
                f"{index_label}. {icon} **{op_kind}** `{src}` → `{dest}`{overwrite_suffix}"
            )
        elif ok and op_kind == "delete":
            suffix = " (moved to Trash)" if "trash" in delete_mode else ""
            lines.append(f"{index_label}. {icon} **{op_kind}** `{src}`{suffix}{overwrite_suffix}")
        elif ok:
            lines.append(f"{index_label}. {icon} **{op_kind}** `{src}`{overwrite_suffix}")
        else:
            lines.append(f"{index_label}. {icon} **{op_kind}** `{src}` — {error}")

    content = "\n".join(lines)
    return content, content[:1200]


def _format_open_item(
    output: dict[str, object],
    execution: dict[str, object],
) -> tuple[str, str]:
    path = str(output.get("path", "")).strip() or "unknown"
    ok = execution.get("ok", output.get("ok", False))
    application = str(output.get("application", "")).strip()
    icon = "✅" if ok else "❌"

    path_obj = Path(path).expanduser().resolve(strict=False)
    try:
        file_uri = path_obj.as_uri()
        path_link = f"[{path_obj.name}]({file_uri})"
    except ValueError:
        path_link = f"`{path}`"

    if application:
        content = f"{icon} Opened {path_link} with **{application}**"
    else:
        content = f"{icon} Opened {path_link}"
    return content, content





def _format_create_directory(
    output: dict[str, object],
    execution: dict[str, object],
) -> tuple[str, str]:
    path = str(output.get("path", "")).strip() or "unknown"
    ok = execution.get("ok", output.get("ok", False))
    already_existed = output.get("already_existed", False)
    icon = "✅" if ok else "❌"
    if already_existed:
        content = f"{icon} Directory already exists: `{path}`"
    else:
        content = f"{icon} Created directory: `{path}`"
    return content, content


def _format_generate_image(
    output: dict[str, object],
    execution: dict[str, object],
) -> tuple[str, str]:
    model = str(output.get("model", "")).strip() or "unknown"
    summary = str(output.get("summary", "")).strip()
    raw_images = output.get("images")
    images = raw_images if isinstance(raw_images, list) else []

    lines: list[str] = [f"**Image Generation** — model `{model}`"]
    if summary:
        lines.append(summary)

    if not images:
        lines.append("No saved images were returned.")
        content = "\n".join(lines)
        return content, content

    lines.append("")
    lines.append(f"Generated {len(images)} image(s):")
    for index, image in enumerate(images[:12], start=1):
        if not isinstance(image, dict):
            lines.append(f"- {index}. (invalid image record)")
            continue
        path = str(image.get("path", "")).strip()
        mime = str(image.get("mime_type", "")).strip() or "unknown"
        width = int(image.get("width", 0) or 0)
        height = int(image.get("height", 0) or 0)
        dims = f"{width}x{height}" if width > 0 and height > 0 else "unknown size"

        path_display = path or "unknown-path"
        try:
            path_obj = Path(path_display).expanduser()
            if not path_obj.is_absolute():
                path_obj = (Path.cwd() / path_obj).resolve(strict=False)
            else:
                path_obj = path_obj.resolve(strict=False)
            file_uri = path_obj.as_uri()
            path_display = str(path_obj)
            path_link = f"[{path_obj.name or path_display}]({file_uri})"
        except Exception:
            path_link = f"`{path_display}`"

        embedded = bool(image.get("note_embedded"))
        embed_text = "embedded in note" if embedded else "saved to file"
        lines.append(f"- {index}. {path_link} — {dims}, {mime}, {embed_text}")

    if len(images) > 12:
        lines.append(f"- ... {len(images) - 12} additional image(s) omitted")

    warnings = output.get("warnings")
    if isinstance(warnings, list) and warnings:
        lines.append("")
        lines.append("Warnings:")
        for warning in warnings:
            lines.append(f"- {warning}")

    content = "\n".join(lines)
    summary_text = "\n".join(lines[:8])
    return content, summary_text


def _format_browse_web(
    output: dict[str, object],
    execution: dict[str, object],
) -> tuple[str, str]:
    final_url = str(output.get("final_url", output.get("url", ""))).strip()
    title = str(output.get("title", "")).strip()
    profile = str(output.get("effective_browse_profile", "")).strip().lower()
    content = str(output.get("content", "")).strip()
    content_type = str(output.get("content_type", "")).strip() or "unknown"
    warning_line = _compact_warning_line(output.get("policy_warnings"), limit=1)

    if final_url:
        label = title or final_url
        source_line = f"Source: [{label}]({final_url})"
    else:
        source_line = f"Source: {title or 'unknown'}"

    lines = ["**Web Browse**"]
    lines.append(source_line)

    if profile and profile != "strict":
        lines.append(f"Browse profile: `{profile}`")
        if warning_line:
            lines.append(
                f"Policy notice: `{profile}` browsing allowed this result with policy warnings."
            )
        else:
            lines.append(
                f"Policy notice: relaxed `{profile}` browsing rules were active for this fetch."
            )

    if warning_line:
        lines.append("")
        lines.append(f"Caution: {warning_line}")

    if content:
        lines.extend(["", content])
    else:
        lines.append("")
        lines.append(f"No extractable text was returned (`{content_type}`).")

    rendered = "\n".join(lines)
    summary_lines = [line for line in lines if line]
    summary = "\n".join(summary_lines[:5])
    return rendered, summary[:1200]


def _format_planner(
    output: dict[str, object],
    execution: dict[str, object],
) -> tuple[str, str]:
    mode = str(output.get("mode", "")).strip() or "unknown"
    goal = str(output.get("goal", "")).strip()
    lines = [f"**Planner** (`{mode}`)"]
    if goal:
        lines.append(f"Goal: {goal}")

    if "plan_id" in output:
        lines.append(f"Plan ID: `{output.get('plan_id')}`")

    complexity = output.get("complexity")
    if isinstance(complexity, dict):
        lines.append(
            "Complexity: "
            f"{complexity.get('level', 'unknown')} "
            f"(score: {complexity.get('score', 'n/a')}, strategy: {complexity.get('strategy', 'n/a')})"
        )
    privacy = output.get("privacy")
    if isinstance(privacy, dict):
        lines.append(
            "Privacy: "
            f"path_data_sent_to_unified_planning={privacy.get('path_data_sent_to_unified_planning')} "
            f"network_disabled_during_planning={privacy.get('network_disabled_during_planning')} "
            f"boundary_payload_mode={privacy.get('boundary_payload_mode')} "
            f"policy_version={privacy.get('policy_version')} "
            f"planner_security_locked={privacy.get('planner_security_locked')} "
            f"policy_attestation_verified={privacy.get('policy_attestation_verified')} "
            f"package_hash_verified={privacy.get('package_hash_verified')} "
            f"package_hash_pinned={privacy.get('package_hash_pinned')} "
            f"package_hash_auto_rotate_enabled={privacy.get('package_hash_auto_rotate_enabled')}"
        )

    issues = output.get("issues")
    if isinstance(issues, list) and issues:
        lines.append("Issues:")
        for issue in issues:
            lines.append(f"- {issue}")
    content = "\n".join(lines)
    return content, content[:1200]


# ---------------------------------------------------------------------------
# Dispatcher table
# ---------------------------------------------------------------------------

_FORMATTERS: dict[
    str,
    Any,
] = {
    "search_files": _format_search_files,
    "get_metadata": _format_get_metadata,
    "read_text": _format_read_text,
    "extract_content": _format_extract_content,
    "planner": _format_planner,
    "plan_ops": _format_plan_ops,
    "apply_ops": _format_apply_ops,
    "open_item": _format_open_item,
    "create_directory": _format_create_directory,
    "generate_image": _format_generate_image,
    "browse_web": _format_browse_web,
}
