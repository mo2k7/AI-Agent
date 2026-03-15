"""Handler for the unified ``read_document`` tool."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from agent_host.tools.executor import ToolExecutor

from agent_host.tools.executor import ToolExecutionError

logger = logging.getLogger(__name__)


def handle(executor: ToolExecutor, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Execute the unified read_document tool."""
    path_raw = str(arguments.get("path", ""))
    mode = str(arguments.get("mode", "text")).strip().lower()
    
    if mode not in {"text", "code", "pdf", "metadata"}:
        raise ToolExecutionError("read_document mode must be one of: text, code, pdf, metadata")

    path = executor._normalize_user_path(path_raw, must_exist=True)
    if not path.is_file():
        raise ToolExecutionError(f"Path is not a file: {path}")

    if mode == "metadata":
        return _handle_metadata(executor, path)

    if mode in {"text", "code"}:
        return _handle_text(executor, arguments, path, mode)

    if mode == "pdf":
        return _handle_pdf(executor, path)


def _handle_metadata(executor: ToolExecutor, path: Any) -> dict[str, Any]:
    stat_res = path.stat()
    return {
        "ok": True,
        "mode": "metadata",
        "path": str(path),
        "metadata": {
            "size_bytes": stat_res.st_size,
            "created_at": stat_res.st_ctime,
            "modified_at": stat_res.st_mtime,
        }
    }


def _handle_text(executor: ToolExecutor, arguments: Mapping[str, Any], path: Any, mode: str) -> dict[str, Any]:
    file_size = path.stat().st_size
    selected_start = 0
    selected_end = file_size

    byte_range = arguments.get("byte_range")
    if byte_range is not None:
        if (
            not isinstance(byte_range, list)
            or len(byte_range) != 2
            or not all(isinstance(value, int) and not isinstance(value, bool) for value in byte_range)
        ):
            raise ToolExecutionError("byte_range must be [start, end] integers")
        start, end = int(byte_range[0]), int(byte_range[1])
        if start < 0 or end < 0 or end < start:
            raise ToolExecutionError("byte_range must satisfy 0 <= start <= end")
        selected_start = min(start, file_size)
        selected_end = min(end, file_size)

    chunk_size = max(0, selected_end - selected_start)

    if chunk_size > executor._MAX_READ_BYTES:
        raise ToolExecutionError(
            f"Requested read segment ({chunk_size} bytes) exceeds maximum "
            f"({executor._MAX_READ_BYTES} bytes). Use byte_range to read in smaller chunks."
        )

    chunk = b""
    if chunk_size > 0:
        try:
            with path.open("rb") as fh:
                fh.seek(selected_start)
                chunk = fh.read(chunk_size)
        except OSError as exc:
            raise ToolExecutionError(f"Failed to read file '{path}': {exc}") from exc
            
    text = chunk.decode("utf-8", errors="replace")
    payload = {
        "ok": True,
        "mode": mode,
        "path": str(path),
        "encoding": "utf-8",
        "byte_range": [selected_start, selected_end],
        "content": text,
    }
    if mode == "code":
        payload["line_count"] = text.count("\n") + 1
    return payload


def _handle_pdf(executor: ToolExecutor, path: Any) -> dict[str, Any]:
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
        raise ToolExecutionError(f"extract_content(pdf) failed: {pdf_exc}") from pdf_exc

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
