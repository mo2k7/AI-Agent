"""Handler for the ``extract_content`` tool."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from agent_host.tools.executor import ToolExecutor

from agent_host.tools.executor import ToolExecutionError

logger = logging.getLogger(__name__)


def handle(executor: ToolExecutor, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Execute the extract_content tool."""
    path_raw = str(arguments.get("path", ""))
    mode = str(arguments.get("mode", "")).strip().lower()
    if mode not in {"text", "code", "pdf"}:
        raise ToolExecutionError("extract_content mode must be one of: text, code, pdf")

    path = executor._normalize_user_path(path_raw, must_exist=True)
    if not path.is_file():
        raise ToolExecutionError(f"Path is not a file: {path}")

    if mode in {"text", "code"}:
        content_result = executor._read_text({"path": str(path)})
        payload: dict[str, Any] = {
            "ok": True,
            "mode": mode,
            "path": str(path),
            "content": content_result["content"],
        }
        if mode == "code":
            payload["line_count"] = str(content_result["content"]).count("\n") + 1
        return payload

    text = ""
    extraction_method = "pypdf"
    page_errors: list[str] = []
    page_count = 0
    extracted_page_count = 0
    try:
        from pypdf import PdfReader  # type: ignore[import-untyped]
        reader = PdfReader(str(path))
        page_count = len(reader.pages)
        pages_text: list[str] = []
        for i, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text()
                if page_text:
                    pages_text.append(page_text.strip())
            except Exception as page_exc:
                page_errors.append(f"Page {i + 1}: {page_exc}")
        text = "\n\n".join(pages_text).strip()
        extracted_page_count = len(pages_text)
    except ImportError as exc:
        raise ToolExecutionError(
            "extract_content(pdf) requires the 'pypdf' dependency.",
            error_type="dependency",
        ) from exc
    except Exception as pdf_exc:
        logger.warning("pypdf extraction failed for %s: %s", path, pdf_exc)
        raise ToolExecutionError(
            f"extract_content(pdf) failed: {pdf_exc}",
        ) from pdf_exc

    warnings_list: list[str] = []
    if not text:
        warnings_list.append("No extractable PDF text found")
    if page_errors:
        warnings_list.append(f"{len(page_errors)} page(s) failed extraction")

    result: dict[str, Any] = {
        "ok": bool(text),
        "mode": "pdf",
        "path": str(path),
        "content": text,
        "extraction_method": extraction_method,
        "page_count": page_count,
        "extracted_pages": extracted_page_count,
        "warning": "; ".join(warnings_list) if warnings_list else "",
    }
    if page_errors:
        result["page_errors"] = page_errors
    return result
