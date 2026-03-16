"""Content extraction and sanitization for browse_web.

Contains text sanitization, prompt injection detection, HTML-to-markdown
conversion, and content extraction from HTML/JSON/plain text responses.
"""

from __future__ import annotations

import base64
import binascii
import html as html_module
import json
import re
import unicodedata
from typing import Any
from urllib.parse import unquote

from agent_host.tools.executor import ToolExecutionError

# ---------------------------------------------------------------------------
# BeautifulSoup import with graceful fallback
# ---------------------------------------------------------------------------

try:
    from bs4 import BeautifulSoup  # type: ignore[import-untyped]
    _BS4_AVAILABLE = True
except ImportError:
    BeautifulSoup = None  # type: ignore[assignment,misc]
    _BS4_AVAILABLE = False

# ---------------------------------------------------------------------------
# Constants (duplicated from browse_web.py for standalone use)
# ---------------------------------------------------------------------------

_MAX_CONTENT_EXTRACT_CHARS = 80_000  # ~20k tokens for the agent

# Tags whose content is never useful for extraction.
_STRIP_TAGS = frozenset({
    "script", "style", "noscript", "iframe", "object", "embed",
    "svg", "canvas", "template", "head",
})

# CSS-ish selectors for boilerplate regions to deprioritize.
_BOILERPLATE_PATTERNS = re.compile(
    r"(?i)(cookie|consent|gdpr|banner|popup|modal|overlay|sidebar|"
    r"advertisement|promo|newsletter|subscribe|social-share|"
    r"footer|nav|header|menu|breadcrumb|related-posts|comment-form)",
)

_PROMPT_INJECTION_PATTERNS: tuple[str, ...] = (
    r"(?i)ignore\s+(previous|all|above)\s+(instructions?|prompts?)",
    r"(?i)you\s+are\s+now\s+(a|an|in)\s+",
    r"(?i)system\s*:\s*",
    r"(?i)<\s*/?(?:system|instruction|prompt)\s*>",
    r"(?i)do\s+not\s+follow\s+your\s+(original|previous)",
)

_PROMPT_INJECTION_SCAN_MAX_CHARS = _MAX_CONTENT_EXTRACT_CHARS
_PROMPT_INJECTION_BLOCK_SCORE = 45
_PROMPT_INJECTION_WARN_SCORE = 25
_PROMPT_INJECTION_MAX_VARIANTS = 16
_PROMPT_INJECTION_MAX_DECODED_CANDIDATES = 8

_ZERO_WIDTH_RE = re.compile(r"[\u200B-\u200D\u2060\uFEFF\u00AD\u180E]")
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
_BASE64_CANDIDATE_RE = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{24,}={0,2}(?![A-Za-z0-9+/=])")
_HEX_CANDIDATE_RE = re.compile(r"\b(?:[0-9a-fA-F]{2}){12,}\b")
_HEX_ESCAPE_RE = re.compile(r"(?:\\x[0-9a-fA-F]{2}){6,}")

_PROMPT_EXFIL_PATTERNS: tuple[str, ...] = (
    r"(?i)\b(reveal|exfiltrate|dump|leak|print)\b.{0,48}\b(secret|credential|token|password|memory|system prompt)\b",
    r"(?i)\bshow\b.{0,32}\b(hidden|internal|confidential)\b.{0,32}\b(instruction|prompt|message)\b",
)
_PROMPT_TOOL_CALL_PATTERNS: tuple[str, ...] = (
    r"(?i)\b(call|invoke|run|execute)\b.{0,36}\btool|function\b",
    r"(?i)\b(send|post|upload|transmit)\b.{0,48}\b(api key|token|credential|secret)\b",
)
_PROMPT_OBFUSCATED_PATTERNS: tuple[str, ...] = (
    r"(?i)i\W*g\W*n\W*o\W*r\W*e\W+(?:p\W*r\W*e\W*v\W*i\W*o\W*u\W*s|a\W*l\W*l|a\W*b\W*o\W*v\W*e)\W+(?:i\W*n\W*s\W*t\W*r\W*u\W*c\W*t\W*i\W*o\W*n\W*s?)",
    r"(?i)s\W*y\W*s\W*t\W*e\W*m\W*:",
    r"(?i)d\W*o\W*\W*n\W*o\W*t\W+\W*f\W*o\W*l\W*l\W*o\W*w",
)
_INSTRUCTION_LIKE_LINE_PATTERNS: tuple[str, ...] = (
    r"(?i)^\s*(system|developer|assistant)\s*:\s*",
    r"(?i)\bignore\b.{0,40}\binstruction",
    r"(?i)\b(do not|don't)\b.{0,40}\b(follow|obey)\b",
    r"(?i)\b(reveal|exfiltrate|dump|leak)\b.{0,40}\b(secret|token|credential|prompt)\b",
    r"(?i)\b(call|invoke|execute|run)\b.{0,40}\b(tool|function)\b",
)


# ---------------------------------------------------------------------------
# Text sanitization & normalization
# ---------------------------------------------------------------------------

def _sanitize_extracted_text(text: str) -> str:
    """Remove potentially dangerous content from extracted text."""
    if not text:
        return ""
    # Decode HTML entities.
    text = html_module.unescape(text)
    # Remove null bytes.
    text = text.replace("\x00", "")
    # Collapse excessive whitespace but preserve paragraph structure.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Strip leading/trailing whitespace per line.
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    return text.strip()


def _normalize_untrusted_text(text: str) -> str:
    """Canonicalize untrusted text to reduce evasion via encoding/Unicode tricks."""
    if not text:
        return ""
    sample = text[:_PROMPT_INJECTION_SCAN_MAX_CHARS]
    sample = html_module.unescape(sample)
    for _ in range(2):
        decoded = unquote(sample)
        if decoded == sample:
            break
        sample = decoded
    sample = unicodedata.normalize("NFKC", sample)
    sample = _ZERO_WIDTH_RE.sub("", sample)
    sample = _CONTROL_CHAR_RE.sub(" ", sample)
    sample = re.sub(r"[ \t]+", " ", sample)
    return sample.strip()


# ---------------------------------------------------------------------------
# Encoding detection helpers
# ---------------------------------------------------------------------------

def _decode_base64_candidate(candidate: str) -> str | None:
    try:
        decoded = base64.b64decode(candidate, validate=True)
    except (binascii.Error, ValueError):
        return None
    if not decoded:
        return None
    text = decoded.decode("utf-8", errors="replace")
    printable_ratio = (
        sum(1 for ch in text if ch.isprintable() or ch in "\n\r\t") / max(len(text), 1)
    )
    if printable_ratio < 0.7:
        return None
    return text


def _decode_hex_candidate(candidate: str) -> str | None:
    compact = candidate.replace("\\x", "")
    if len(compact) % 2 != 0:
        return None
    try:
        decoded = bytes.fromhex(compact).decode("utf-8", errors="replace")
    except ValueError:
        return None
    if not decoded:
        return None
    return decoded


def _expand_encoded_candidates(text: str) -> list[str]:
    if not text:
        return []
    candidates: list[str] = []
    seen: set[str] = set()

    for pattern, decoder in (
        (_BASE64_CANDIDATE_RE, _decode_base64_candidate),
        (_HEX_CANDIDATE_RE, _decode_hex_candidate),
        (_HEX_ESCAPE_RE, _decode_hex_candidate),
    ):
        for match in pattern.finditer(text):
            raw_candidate = match.group(0)
            if raw_candidate in seen:
                continue
            seen.add(raw_candidate)
            decoded = decoder(raw_candidate)
            if decoded:
                candidates.append(decoded)
            if len(candidates) >= _PROMPT_INJECTION_MAX_DECODED_CANDIDATES:
                return candidates
    return candidates


# ---------------------------------------------------------------------------
# Prompt injection detection
# ---------------------------------------------------------------------------

def _extract_html_structural_text(raw_body: str) -> str:
    """Extract script/comment/meta/title text that may contain hidden instructions."""
    if not raw_body:
        return ""
    sample = raw_body[:_PROMPT_INJECTION_SCAN_MAX_CHARS]
    chunks: list[str] = []
    for pattern in (
        r"(?is)<script\b[^>]*>(.*?)</script>",
        r"(?is)<!--(.*?)-->",
        r'(?is)<meta\b[^>]*\bcontent\s*=\s*["\']([^"\']{1,5000})["\']',
        r"(?is)<title\b[^>]*>(.*?)</title>",
    ):
        chunks.extend(m.group(1) for m in re.finditer(pattern, sample))
    return "\n".join(chunks)


def _build_prompt_injection_variants(
    content_text: str,
    raw_body: str,
    content_type: str,
) -> list[str]:
    variants: list[str] = []
    seen: set[str] = set()

    def _add_variant(value: str) -> None:
        normalized = _normalize_untrusted_text(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            variants.append(normalized)

    _add_variant(content_text)
    _add_variant(raw_body)
    if "html" in (content_type or "").lower():
        _add_variant(_extract_html_structural_text(raw_body))

    for source in list(variants):
        for decoded in _expand_encoded_candidates(source):
            _add_variant(decoded)
            if len(variants) >= _PROMPT_INJECTION_MAX_VARIANTS:
                return variants

    return variants[:_PROMPT_INJECTION_MAX_VARIANTS]


def _score_prompt_injection_variants(variants: list[str]) -> dict[str, Any]:
    score = 0
    signals: list[str] = []
    matched_categories: set[str] = set()

    def _mark(category: str, weight: int, signal: str) -> None:
        nonlocal score
        if category in matched_categories:
            return
        matched_categories.add(category)
        score += weight
        signals.append(signal)

    for text in variants:
        if any(re.search(pattern, text) for pattern in _PROMPT_INJECTION_PATTERNS):
            _mark("directive_override", 35, "Directive override instructions detected.")
        if any(re.search(pattern, text) for pattern in _PROMPT_EXFIL_PATTERNS):
            _mark("secret_exfiltration", 30, "Secret/system-prompt exfiltration attempt detected.")
        if any(re.search(pattern, text) for pattern in _PROMPT_TOOL_CALL_PATTERNS):
            _mark("tool_commanding", 30, "Tool invocation or data exfiltration command detected.")
        if any(re.search(pattern, text) for pattern in _PROMPT_OBFUSCATED_PATTERNS):
            _mark("obfuscated_directives", 25, "Obfuscated instruction-like markers detected.")
        if re.search(r"(?i)<\s*/?(system|developer|assistant|instruction)\s*>", text):
            _mark("instruction_tags", 25, "Instruction-role tags detected in untrusted content.")
        if re.search(r"(?i)\b(base64|hex|rot13|unicode)\b.{0,32}\b(decode|deobfuscate)\b", text):
            _mark("decode_evasion", 20, "Decode/deobfuscation evasion marker detected.")

    risk_level = "low"
    if score >= _PROMPT_INJECTION_BLOCK_SCORE:
        risk_level = "high"
    elif score >= _PROMPT_INJECTION_WARN_SCORE:
        risk_level = "medium"

    return {
        "risk_score": score,
        "risk_level": risk_level,
        "signals": signals,
        "detected": score >= _PROMPT_INJECTION_BLOCK_SCORE,
    }


def _contains_prompt_injection_patterns(text: str) -> bool:
    """Backwards-compatible helper for tests and callers."""
    variants = _build_prompt_injection_variants(
        content_text=text,
        raw_body="",
        content_type="text/plain",
    )
    return _score_prompt_injection_variants(variants)["detected"]


def _strip_instruction_like_lines(text: str) -> tuple[str, int]:
    """Strip lines that look like executable instructions from untrusted content."""
    if not text:
        return "", 0
    kept: list[str] = []
    removed = 0
    for line in text.splitlines():
        if any(re.search(pattern, line) for pattern in _INSTRUCTION_LIKE_LINE_PATTERNS):
            removed += 1
            continue
        kept.append(line)
    return "\n".join(kept).strip(), removed


def _sanitize_raw_html_for_agent(raw_html: str) -> str:
    """Return a conservative HTML subset safe for downstream parsing."""
    if not raw_html:
        return ""
    sample = raw_html[:_MAX_CONTENT_EXTRACT_CHARS]
    sample = re.sub(r"(?is)<(script|style|noscript|template)\b[^>]*>.*?</\1>", "", sample)
    sample = re.sub(r"(?is)<!--.*?-->", "", sample)
    for pattern in _PROMPT_INJECTION_PATTERNS + _PROMPT_EXFIL_PATTERNS + _PROMPT_TOOL_CALL_PATTERNS:
        sample = re.sub(pattern, "[redacted-instruction]", sample)
    return sample


def _detect_content_warnings(text: str, url: str) -> list[str]:
    """Detect content that the agent should be cautious about.

    NOTE: Prompt injection scanning is NOT done here -- it is performed
    once in ``_process_single_url`` with both ``content_text`` and
    ``raw_body`` for full coverage.  This function only checks for
    structural content anomalies (link density, etc.).
    """
    warnings: list[str] = []

    # Detect pages that are mostly links (likely spam or directory listings).
    link_density_threshold = 0.6
    link_chars = len(re.findall(r"https?://\S+", text))
    if len(text) > 200 and link_chars / len(text) > link_density_threshold:
        warnings.append(
            "High link density detected — this page may be a directory listing "
            "or aggregator rather than substantive content."
        )

    return warnings


# ---------------------------------------------------------------------------
# HTML content extraction & markdown conversion
# ---------------------------------------------------------------------------

def _extract_content_from_html(
    raw_html: str,
    url: str,
) -> dict[str, Any]:
    """Extract readable content, metadata, and HTML elements to clean Markdown."""
    result: dict[str, Any] = {
        "title": "",
        "content": "",
        "content_format": "text",
        "meta_description": "",
        "meta_author": "",
        "meta_robots": "",
        "canonical_url": "",
        "language": "",
        "published_at": "",
        "updated_at": "",
        "links_found": 0,
        "images_found": 0,
        "extraction_method": "unknown",
        "content_length_chars": 0,
    }

    if not _BS4_AVAILABLE:
        raise ToolExecutionError(
            "browse_web requires BeautifulSoup4 for HTML extraction."
        )

    soup = BeautifulSoup(raw_html, "html.parser")

    # --- Extract metadata from <head> ---
    title_tag = soup.find("title")
    if title_tag:
        result["title"] = _sanitize_extracted_text(title_tag.get_text())

    meta_desc = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
    if meta_desc and meta_desc.get("content"):
        result["meta_description"] = str(meta_desc["content"])[:500]

    meta_author = soup.find("meta", attrs={"name": re.compile(r"author", re.I)})
    if meta_author and meta_author.get("content"):
        result["meta_author"] = str(meta_author["content"])[:200]

    meta_robots = soup.find("meta", attrs={"name": re.compile(r"robots", re.I)})
    if meta_robots and meta_robots.get("content"):
        result["meta_robots"] = str(meta_robots["content"])[:200]

    canonical = soup.find("link", attrs={"rel": "canonical"})
    if canonical and canonical.get("href"):
        result["canonical_url"] = str(canonical["href"])[:500]

    html_tag = soup.find("html")
    if html_tag and html_tag.get("lang"):
        result["language"] = str(html_tag["lang"])[:10]

    for attr_name in (
        ("article:published_time", "published_at"),
        ("og:published_time", "published_at"),
        ("publish_date", "published_at"),
        ("article:modified_time", "updated_at"),
        ("og:updated_time", "updated_at"),
        ("lastmod", "updated_at"),
        ("date", "updated_at"),
    ):
        selector_value, output_key = attr_name
        meta_tag = (
            soup.find("meta", attrs={"property": selector_value})
            or soup.find("meta", attrs={"name": re.compile(rf"^{re.escape(selector_value)}$", re.I)})
        )
        if meta_tag and meta_tag.get("content") and not result.get(output_key):
            result[output_key] = str(meta_tag["content"])[:80]

    # --- Count links and images ---
    result["links_found"] = len(soup.find_all("a", href=True))
    result["images_found"] = len(soup.find_all("img"))

    # --- Strip non-content tags ---
    for tag_name in _STRIP_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # --- Extract main content and convert to markdown ---
    main_content = _extract_main_content_heuristic(soup)
    content_soup = BeautifulSoup(main_content, "html.parser") if main_content and len(main_content) > 100 else soup
    result["extraction_method"] = "markdown_conversion"
    result["content_format"] = "markdown"
    result["content"] = _html_to_markdown(content_soup)

    # Enforce size cap.
    if len(result["content"]) > _MAX_CONTENT_EXTRACT_CHARS:
        result["content"] = result["content"][:_MAX_CONTENT_EXTRACT_CHARS]
        result["content_truncated"] = True
        result["content_truncated_at_chars"] = _MAX_CONTENT_EXTRACT_CHARS

    result["content_length_chars"] = len(result["content"])
    return result


def _html_to_markdown(soup: Any) -> str:
    """Convert HTML elements to simplified markdown using BeautifulSoup.

    Handles: headings, bold, italic, code blocks, inline code, links, images,
    ordered/unordered lists, blockquotes, and horizontal rules.
    """
    if not _BS4_AVAILABLE or soup is None:
        return _sanitize_extracted_text(soup.get_text("\n") if soup else "")

    lines: list[str] = []

    def _process_element(el: Any, depth: int = 0) -> None:
        """Recursively process an element and append markdown lines."""
        if hasattr(el, "name") and el.name is None:
            # NavigableString
            text = str(el).strip()
            if text:
                lines.append(text)
            return

        tag = getattr(el, "name", None)
        if not tag:
            text = str(el).strip()
            if text:
                lines.append(text)
            return

        # Headings
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag[1])
            text = el.get_text(strip=True)
            if text:
                lines.append(f"\n{'#' * level} {text}\n")
            return

        # Bold
        if tag in ("b", "strong"):
            text = el.get_text(strip=True)
            if text:
                lines.append(f"**{text}**")
            return

        # Italic
        if tag in ("i", "em"):
            text = el.get_text(strip=True)
            if text:
                lines.append(f"*{text}*")
            return

        # Code blocks
        if tag == "pre":
            code_el = el.find("code")
            code_text = code_el.get_text() if code_el else el.get_text()
            lines.append(f"\n```\n{code_text.strip()}\n```\n")
            return

        # Inline code
        if tag == "code":
            text = el.get_text(strip=True)
            if text:
                lines.append(f"`{text}`")
            return

        # Links
        if tag == "a":
            href = el.get("href", "")
            text = el.get_text(strip=True)
            if text and href:
                lines.append(f"[{text}]({href})")
            elif text:
                lines.append(text)
            return

        # Images
        if tag == "img":
            alt = el.get("alt", "")
            src = el.get("src", "")
            if src:
                lines.append(f"![{alt}]({src})")
            return

        # Unordered lists
        if tag == "ul":
            for li in el.find_all("li", recursive=False):
                text = li.get_text(strip=True)
                if text:
                    lines.append(f"- {text}")
            lines.append("")
            return

        # Ordered lists
        if tag == "ol":
            for idx, li in enumerate(el.find_all("li", recursive=False), 1):
                text = li.get_text(strip=True)
                if text:
                    lines.append(f"{idx}. {text}")
            lines.append("")
            return

        # Blockquotes
        if tag == "blockquote":
            text = el.get_text(strip=True)
            if text:
                for quote_line in text.split("\n"):
                    lines.append(f"> {quote_line.strip()}")
            return

        # Horizontal rule
        if tag == "hr":
            lines.append("\n---\n")
            return

        # Paragraphs and divs
        if tag in ("p", "div", "section", "article"):
            text = el.get_text(strip=True)
            if text:
                lines.append(f"\n{text}\n")
            return

        # Default: recurse into children
        for child in el.children:
            _process_element(child, depth + 1)

    _process_element(soup)

    # Clean up excessive blank lines.
    markdown = "\n".join(lines)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()
    return _sanitize_extracted_text(markdown)


def _extract_main_content_heuristic(soup: Any) -> str:
    """Simplified readability-style content extraction.

    Scores text-bearing containers by text density vs. link density,
    selects the best candidate, and returns its cleaned text.
    """
    # Look for semantic containers first.
    semantic_elements = list(soup.find_all(["article", "main"]))
    semantic_elements.extend(soup.find_all(attrs={"role": "main"}))
    if semantic_elements:
        best = max(semantic_elements, key=lambda el: len(el.get_text(strip=True)))
        text = best.get_text(strip=True)
        if len(text) > 200:
            return _sanitize_extracted_text(best.get_text("\n"))

    # Fall back to scoring all block-level containers.
    candidates: list[tuple[float, Any]] = []
    for tag in soup.find_all(["div", "section", "td", "blockquote"]):
        text = tag.get_text(strip=True)
        text_len = len(text)
        if text_len < 80:
            continue

        # Calculate text density (text chars vs. total HTML chars).
        html_len = len(str(tag))
        if html_len == 0:
            continue
        text_density = text_len / html_len

        # Penalize containers that are mostly links.
        links = tag.find_all("a")
        link_text_len = sum(len(a.get_text(strip=True)) for a in links)
        link_ratio = link_text_len / text_len if text_len > 0 else 1.0

        # Penalize boilerplate regions.
        tag_classes = " ".join(tag.get("class", []) + [tag.get("id", "")])
        boilerplate_penalty = 0.5 if _BOILERPLATE_PATTERNS.search(tag_classes) else 1.0

        # Boost containers with many <p> children (article-like).
        p_count = len(tag.find_all("p", recursive=False))
        p_boost = 1.0 + min(p_count * 0.1, 0.5)

        score = text_density * (1.0 - link_ratio) * boilerplate_penalty * p_boost * text_len
        candidates.append((score, tag))

    if not candidates:
        return ""

    candidates.sort(key=lambda pair: pair[0], reverse=True)
    best_tag = candidates[0][1]
    return _sanitize_extracted_text(best_tag.get_text("\n"))


# ---------------------------------------------------------------------------
# JSON and plain text extraction
# ---------------------------------------------------------------------------

def _extract_content_from_json(raw_body: str) -> dict[str, Any]:
    """Extract and validate JSON content."""
    try:
        parsed = json.loads(raw_body)
        pretty = json.dumps(parsed, indent=2, ensure_ascii=False, default=str)
        if len(pretty) > _MAX_CONTENT_EXTRACT_CHARS:
            pretty = pretty[:_MAX_CONTENT_EXTRACT_CHARS]
        return {
            "title": "",
            "content": pretty,
            "content_format": "json",
            "extraction_method": "json_parse",
            "content_length_chars": len(pretty),
        }
    except (json.JSONDecodeError, ValueError):
        return {
            "title": "",
            "content": raw_body[:_MAX_CONTENT_EXTRACT_CHARS],
            "content_format": "text",
            "extraction_method": "json_parse_failed",
            "content_length_chars": min(len(raw_body), _MAX_CONTENT_EXTRACT_CHARS),
        }


def _extract_content_from_plain_text(raw_body: str) -> dict[str, Any]:
    """Handle plain text responses."""
    content = _sanitize_extracted_text(raw_body)
    if len(content) > _MAX_CONTENT_EXTRACT_CHARS:
        content = content[:_MAX_CONTENT_EXTRACT_CHARS]
    return {
        "title": "",
        "content": content,
        "content_format": "text",
        "extraction_method": "plain_text",
        "content_length_chars": len(content),
    }
