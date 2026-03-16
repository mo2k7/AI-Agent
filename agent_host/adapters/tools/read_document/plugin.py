"""Tool plugin: read_document.

Reads a file in one of three modes:

- **text** / **code** -- raw UTF-8 content with optional byte-range slicing
- **pdf** -- text extraction via ``pypdf``
- **metadata** -- stat-level metadata (size, timestamps)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Mapping, Sequence

from agent_host.adapters.tools._path_security import normalize_user_path
from agent_host.contracts.types.errors import AgentError, ErrorCode
from agent_host.contracts.types.result import Failure, Result, Success

logger = logging.getLogger(__name__)


class ReadDocumentPlugin:
    """Self-contained plugin for the ``read_document`` tool."""

    _MAX_READ_BYTES: int = 10 * 1024 * 1024  # 10 MB

    _VALID_MODES: frozenset[str] = frozenset({"text", "code", "pdf", "metadata"})

    def __init__(self, *, allowed_roots: Sequence[Path]) -> None:
        self._allowed_roots: list[Path] = [
            root.expanduser().resolve(strict=False) for root in allowed_roots
        ]

    # ------------------------------------------------------------------
    # ToolPlugin protocol
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "read_document"

    @property
    def description(self) -> str:
        return "Read a document in text, code, pdf, or metadata mode"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or user-relative path to the file",
                },
                "mode": {
                    "type": "string",
                    "enum": ["text", "code", "pdf", "metadata"],
                    "description": "Read mode (default: text)",
                },
                "byte_range": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 2,
                    "maxItems": 2,
                    "description": (
                        "[start, end] byte offsets for text/code mode. "
                        "Omit to read the entire file."
                    ),
                },
            },
            "required": ["path"],
        }

    def execute(self, arguments: Mapping[str, Any]) -> Result[dict[str, Any]]:
        """Read the document, returning Success or Failure."""
        try:
            return self._execute_inner(arguments)
        except Exception as exc:
            return Failure(AgentError(
                code=ErrorCode.INTERNAL,
                message=f"Unexpected error in read_document: {exc}",
                source="read_document",
            ))

    def health_check(self) -> Result[bool]:
        return Success(True)

    # ------------------------------------------------------------------
    # Internal dispatch
    # ------------------------------------------------------------------

    def _execute_inner(self, arguments: Mapping[str, Any]) -> Result[dict[str, Any]]:
        # --- path ---
        path_raw = str(arguments.get("path", "")).strip()
        if not path_raw:
            return Failure(AgentError(
                code=ErrorCode.VALIDATION,
                message="read_document requires a non-empty 'path'",
                source="read_document",
            ))

        # --- mode ---
        mode = str(arguments.get("mode", "text")).strip().lower()
        if mode not in self._VALID_MODES:
            return Failure(AgentError(
                code=ErrorCode.VALIDATION,
                message=(
                    f"read_document mode must be one of: "
                    f"{', '.join(sorted(self._VALID_MODES))}"
                ),
                source="read_document",
            ))

        # --- normalize & security-check path ---
        path_result = normalize_user_path(
            path_raw,
            allowed_roots=self._allowed_roots,
            must_exist=True,
        )
        if not path_result.is_ok:
            return path_result  # type: ignore[return-value]

        path: Path = path_result.unwrap()

        if not path.is_file():
            return Failure(AgentError(
                code=ErrorCode.VALIDATION,
                message=f"Path is not a file: {path}",
                source="read_document",
            ))

        # --- dispatch ---
        if mode == "metadata":
            return self._handle_metadata(path)
        if mode in {"text", "code"}:
            return self._handle_text(arguments, path, mode)
        # mode == "pdf"
        return self._handle_pdf(path)

    # ------------------------------------------------------------------
    # Mode handlers
    # ------------------------------------------------------------------

    def _handle_metadata(self, path: Path) -> Result[dict[str, Any]]:
        try:
            stat_res = path.stat()
        except OSError as exc:
            return Failure(AgentError(
                code=ErrorCode.INTERNAL,
                message=f"Failed to stat '{path}': {exc}",
                source="read_document",
            ))
        return Success({
            "ok": True,
            "mode": "metadata",
            "path": str(path),
            "metadata": {
                "size_bytes": stat_res.st_size,
                "created_at": stat_res.st_ctime,
                "modified_at": stat_res.st_mtime,
            },
        })

    def _handle_text(
        self,
        arguments: Mapping[str, Any],
        path: Path,
        mode: str,
    ) -> Result[dict[str, Any]]:
        try:
            file_size = path.stat().st_size
        except OSError as exc:
            return Failure(AgentError(
                code=ErrorCode.INTERNAL,
                message=f"Failed to stat '{path}': {exc}",
                source="read_document",
            ))

        selected_start = 0
        selected_end = file_size

        # --- optional byte_range ---
        byte_range = arguments.get("byte_range")
        if byte_range is not None:
            validation_error = self._validate_byte_range(byte_range)
            if validation_error is not None:
                return Failure(validation_error)
            start, end = int(byte_range[0]), int(byte_range[1])
            selected_start = min(start, file_size)
            selected_end = min(end, file_size)

        chunk_size = max(0, selected_end - selected_start)

        if chunk_size > self._MAX_READ_BYTES:
            return Failure(AgentError(
                code=ErrorCode.VALIDATION,
                message=(
                    f"Requested read segment ({chunk_size} bytes) exceeds maximum "
                    f"({self._MAX_READ_BYTES} bytes). "
                    f"Use byte_range to read in smaller chunks."
                ),
                source="read_document",
            ))

        # --- read ---
        chunk = b""
        if chunk_size > 0:
            try:
                with path.open("rb") as fh:
                    fh.seek(selected_start)
                    chunk = fh.read(chunk_size)
            except OSError as exc:
                return Failure(AgentError(
                    code=ErrorCode.INTERNAL,
                    message=f"Failed to read file '{path}': {exc}",
                    source="read_document",
                ))

        text = chunk.decode("utf-8", errors="replace")
        payload: dict[str, Any] = {
            "ok": True,
            "mode": mode,
            "path": str(path),
            "encoding": "utf-8",
            "byte_range": [selected_start, selected_end],
            "content": text,
        }
        if mode == "code":
            payload["line_count"] = text.count("\n") + 1
        return Success(payload)

    def _handle_pdf(self, path: Path) -> Result[dict[str, Any]]:
        try:
            from pypdf import PdfReader  # type: ignore[import-untyped]
        except ImportError:
            return Failure(AgentError(
                code=ErrorCode.DEPENDENCY,
                message="read_document(pdf) requires the 'pypdf' dependency",
                source="read_document",
            ))

        try:
            reader = PdfReader(str(path))
        except Exception as exc:
            return Failure(AgentError(
                code=ErrorCode.INTERNAL,
                message=f"read_document(pdf) failed to open '{path}': {exc}",
                source="read_document",
            ))

        page_count = len(reader.pages)
        pages_text: list[str] = []
        page_errors: list[str] = []

        for i, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text()
                if page_text:
                    pages_text.append(page_text.strip())
            except Exception as page_exc:
                page_errors.append(f"Page {i + 1}: {page_exc}")

        text = "\n\n".join(pages_text).strip()
        extracted_page_count = len(pages_text)

        warnings_list: list[str] = []
        if not text:
            warnings_list.append("No extractable PDF text found")
        if page_errors:
            warnings_list.append(
                f"{len(page_errors)} page(s) failed extraction"
            )

        result: dict[str, Any] = {
            "ok": bool(text),
            "mode": "pdf",
            "path": str(path),
            "content": text,
            "extraction_method": "pypdf",
            "page_count": page_count,
            "extracted_pages": extracted_page_count,
            "warning": "; ".join(warnings_list) if warnings_list else "",
        }
        if page_errors:
            result["page_errors"] = page_errors
        return Success(result)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_byte_range(byte_range: Any) -> AgentError | None:
        """Return an ``AgentError`` if ``byte_range`` is invalid, else None."""
        if (
            not isinstance(byte_range, list)
            or len(byte_range) != 2
            or not all(
                isinstance(v, int) and not isinstance(v, bool)
                for v in byte_range
            )
        ):
            return AgentError(
                code=ErrorCode.VALIDATION,
                message="byte_range must be [start, end] integers",
                source="read_document",
            )
        start, end = int(byte_range[0]), int(byte_range[1])
        if start < 0 or end < 0 or end < start:
            return AgentError(
                code=ErrorCode.VALIDATION,
                message="byte_range must satisfy 0 <= start <= end",
                source="read_document",
            )
        return None
