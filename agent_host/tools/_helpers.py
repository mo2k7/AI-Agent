"""Shared helper utilities for tool handlers.

These functions were extracted from main.py to enable reuse across
per-tool handler modules without circular imports.
"""

from __future__ import annotations

import re
import time
import uuid
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_OCR_SIGNAL_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "i",
    "if",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "what",
    "with",
    "you",
    "your",
}

_NOTE_TAG_SANITIZER = re.compile(r"[^a-z0-9_-]+")


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _path_within_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _path_within_any_root(path: Path, roots: list[Path]) -> bool:
    return any(_path_within_root(path, root) for root in roots)


# ---------------------------------------------------------------------------
# Image output helpers
# ---------------------------------------------------------------------------

def _default_image_file_extension(mime_type: str) -> str:
    return ".jpg" if mime_type.strip().lower() == "image/jpeg" else ".png"


def _sanitize_image_filename_fragment(raw: str, *, default: str) -> str:
    collapsed = re.sub(r"\s+", "-", raw.strip().lower())
    sanitized = re.sub(r"[^a-z0-9._-]+", "", collapsed).strip("._-")
    if not sanitized:
        return default
    return sanitized[:48]


def _build_default_image_output_path(
    *,
    image_output_root: Path,
    session_id: str,
    prompt: str,
    image_index: int,
    output_mime_type: str,
) -> Path:
    date_segment = time.strftime("%Y/%m/%d")
    session_segment = _sanitize_image_filename_fragment(session_id, default="session")
    stem_fragment = _sanitize_image_filename_fragment(prompt[:80], default="image")
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    unique = uuid.uuid4().hex[:8]
    stem = f"{timestamp}-{stem_fragment}-{unique}"
    if image_index > 0:
        stem = f"{stem}-{image_index + 1:02d}"
    extension = _default_image_file_extension(output_mime_type)
    return (
        image_output_root
        / session_segment
        / date_segment
        / f"{stem}{extension}"
    )


# ---------------------------------------------------------------------------
# Note helpers
# ---------------------------------------------------------------------------

def _normalize_note_tags(
    raw_tags: object,
    *,
    extra_tags: tuple[str, ...] = (),
    max_tags: int = 10,
) -> list[str]:
    """Normalize note tags into safe lowercase slugs."""
    normalized: list[str] = []
    seen: set[str] = set()
    candidates: list[str] = []
    if isinstance(raw_tags, list):
        for item in raw_tags:
            if isinstance(item, str):
                candidates.append(item)
    candidates.extend(extra_tags)
    for candidate in candidates:
        cleaned = _NOTE_TAG_SANITIZER.sub("-", candidate.strip().lower()).strip("-_")
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned[:50])
        if len(normalized) >= max_tags:
            break
    return normalized


def _extract_teacher_highlights(source_text: str, *, max_items: int = 5) -> list[str]:
    """Extract concise highlight bullets from generated teaching text."""
    highlights: list[str] = []
    seen: set[str] = set()
    for raw_line in source_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("<!--") and line.endswith("-->"):
            continue
        if line.startswith("```"):
            continue
        line = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s*", "", line)
        line = re.sub(r"^\s*#{1,6}\s*", "", line)
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered in {
            "student question",
            "teacher explanation",
            "lesson summary",
            "key highlights",
            "review prompts",
        }:
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        highlights.append(line)
        if len(highlights) >= max_items:
            break
    return highlights


def _build_teacher_note_body(*, prompt: str, response_text: str) -> str:
    """Build a structured teacher note with key highlights and checks."""
    prompt_line = prompt.strip()
    if not prompt_line:
        raise ValueError("Teacher mode requires a non-empty user prompt.")
    lesson_text = response_text.strip()
    if not lesson_text:
        raise ValueError("Teacher mode requires a non-empty response to capture notes.")
    highlights = _extract_teacher_highlights(lesson_text)
    if not highlights:
        raise ValueError("Teacher mode could not extract key highlights from the response.")
    title = prompt_line.splitlines()[0].strip()[:100]
    lines = [
        f"**Study Session — {title}**",
        "",
        "## Student Question",
        prompt_line,
        "",
        "## Teacher Explanation",
        lesson_text,
        "",
        "## Key Highlights",
    ]
    lines.extend(f"- {item}" for item in highlights)
    lines.extend(
        [
            "",
            "## Review Prompts",
            "- Explain the idea above in your own words without looking.",
            "- Which highlight is still unclear and needs another example?",
        ]
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# OCR compaction
# ---------------------------------------------------------------------------

def _compact_ocr_text_for_model(
    ocr_text: str,
    *,
    purpose: str,
    prompt: str,
    max_chars: int,
    max_lines: int,
) -> tuple[str, bool, int, int]:
    """Compact OCR text for model function-response payloads without dropping key signal lines."""
    if max_chars <= 0 or max_lines <= 0:
        return "", True, 0, 0

    normalized_lines: list[str] = []
    for raw_line in ocr_text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        if normalized_lines and normalized_lines[-1].casefold() == line.casefold():
            continue
        normalized_lines.append(line)

    total_lines = len(normalized_lines)
    if total_lines == 0:
        return "", False, 0, 0

    full_text = "\n".join(normalized_lines)
    if total_lines <= max_lines and len(full_text) <= max_chars:
        return full_text, False, total_lines, total_lines

    keyword_terms: list[str] = []
    for token in re.findall(r"[a-z0-9]{3,}", f"{purpose}\n{prompt}".lower()):
        if token in _OCR_SIGNAL_STOPWORDS or token in keyword_terms:
            continue
        keyword_terms.append(token)
        if len(keyword_terms) >= 24:
            break

    ranked_candidates: list[tuple[float, int]] = []
    for idx, line in enumerate(normalized_lines):
        line_lower = line.lower()
        keyword_hits = sum(1 for term in keyword_terms if term in line_lower)
        score = 0.0
        if keyword_hits > 0:
            score += 2.5 + min(4.0, keyword_hits * 0.6)
        if idx < 20:
            score += 0.8
        if ":" in line:
            score += 0.2
        if line.startswith(("-", "*", "\u2022")) or re.match(r"^\d+[.)]\s+", line):
            score += 0.25
        if len(line) <= 120:
            score += 0.1
        ranked_candidates.append((score, idx))

    lead_count = min(8, total_lines, max(1, max_lines // 2))
    selected_indexes: set[int] = set(range(lead_count))
    for score, idx in sorted(ranked_candidates, key=lambda item: (item[0], -item[1]), reverse=True):
        if len(selected_indexes) >= max_lines:
            break
        if score <= 0.0:
            continue
        selected_indexes.add(idx)

    if len(selected_indexes) < min(max_lines, total_lines):
        for idx in range(total_lines):
            if len(selected_indexes) >= max_lines:
                break
            selected_indexes.add(idx)

    selected_lines = [normalized_lines[idx] for idx in sorted(selected_indexes)]

    compact_lines: list[str] = []
    current_chars = 0
    for line in selected_lines:
        line_len = len(line)
        projected = current_chars + line_len + (1 if compact_lines else 0)
        if projected > max_chars:
            break
        compact_lines.append(line)
        current_chars = projected

    if not compact_lines:
        clipped = selected_lines[0][:max_chars].strip()
        if clipped:
            compact_lines = [clipped]

    compact_text = "\n".join(compact_lines)
    included_lines = len(compact_lines)
    was_truncated = included_lines < total_lines or len(compact_text) < len(full_text)
    return compact_text, was_truncated, included_lines, total_lines
