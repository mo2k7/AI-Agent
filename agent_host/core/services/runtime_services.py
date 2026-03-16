"""Shared runtime utilities for IPC handlers and orchestrator.

Manages request lifecycle, timeout handling, device capabilities,
and session broadcasting. All shared mutable state dicts are received
by reference via constructor.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


class RequestTimeoutError(TimeoutError):
    """Raised when a blocking operation exceeds timeout for a single request."""

    def __init__(self, message: str, *, error_data: dict[str, Any]):
        super().__init__(message)
        self.error_data = error_data


def _build_timeout_error_data(
    *,
    request_id: str,
    label: str,
    timeout_seconds: float,
    elapsed_seconds: float,
) -> dict[str, Any]:
    operation = label.strip() or "unknown"
    if operation.startswith("model.generate_content.continuation"):
        timeout_code = "model_timeout"
        phase = "model_continuation"
        user_message = (
            "The model exceeded its continuation timeout. "
            "Your backend connection is still active, so you can retry this request."
        )
    elif operation.startswith("model.generate_content"):
        timeout_code = "model_timeout"
        phase = "model_generation"
        user_message = (
            "The model took too long to respond. "
            "Your backend connection is still active, so you can retry this request."
        )
    elif operation.startswith("tool."):
        timeout_code = "tool_timeout"
        phase = "tool_execution"
        user_message = (
            "A tool execution exceeded its timeout budget for this request. "
            "Your backend connection is still active."
        )
    elif operation.startswith("db."):
        timeout_code = "database_timeout"
        phase = "database"
        user_message = (
            "A database operation exceeded its timeout budget for this request. "
            "Your backend connection is still active."
        )
    else:
        timeout_code = "request_timeout"
        phase = "request"
        user_message = (
            "This request exceeded its timeout budget. "
            "Your backend connection is still active."
        )
    return {
        "code": timeout_code,
        "request_id": request_id,
        "phase": phase,
        "operation": operation,
        "timeout_seconds": round(float(timeout_seconds), 3),
        "elapsed_seconds": round(max(0.0, float(elapsed_seconds)), 3),
        "user_message": user_message,
    }


class RuntimeServices:
    """Shared runtime utilities for IPC handlers and orchestrator.

    Manages request lifecycle, timeout handling, device capabilities,
    and session broadcasting. All shared mutable state dicts are received
    by reference via constructor.
    """

    # Expose as class-level attribute so consumers can reference the type.
    RequestTimeoutError = RequestTimeoutError

    def __init__(
        self,
        *,
        ipc_bridge: Any,
        memory_manager: Any,
        db_timeout_seconds: float,
        active_prompt_tasks: dict,
        cancelled_prompt_requests: set,
        client_prompt_index: dict,
        device_registry: dict,
        pending_tool_confirmations: dict,
        pending_screen_captures: dict,
    ):
        self._ipc_bridge = ipc_bridge
        self._memory_manager = memory_manager
        self._db_timeout_seconds = db_timeout_seconds
        self._active_prompt_tasks = active_prompt_tasks
        self._cancelled_prompt_requests = cancelled_prompt_requests
        self._client_prompt_index = client_prompt_index
        self._device_registry = device_registry
        self._pending_tool_confirmations = pending_tool_confirmations
        self._pending_screen_captures = pending_screen_captures

    # ------------------------------------------------------------------
    # Device capabilities
    # ------------------------------------------------------------------

    def client_capabilities_for(self, client_address: str) -> set[str]:
        entry = self._device_registry.get(client_address)
        if not isinstance(entry, dict):
            return set()
        raw_capabilities = entry.get("capabilities", [])
        if not isinstance(raw_capabilities, list):
            return set()
        return {
            capability.strip()
            for capability in raw_capabilities
            if isinstance(capability, str) and capability.strip()
        }

    # ------------------------------------------------------------------
    # Timeout helpers
    # ------------------------------------------------------------------

    @staticmethod
    def build_timeout_error_data(
        *,
        request_id: str,
        label: str,
        timeout_seconds: float,
        elapsed_seconds: float,
    ) -> dict[str, Any]:
        return _build_timeout_error_data(
            request_id=request_id,
            label=label,
            timeout_seconds=timeout_seconds,
            elapsed_seconds=elapsed_seconds,
        )

    async def run_blocking_with_timeout(
        self,
        *,
        label: str,
        timeout_seconds: float,
        func: Callable[..., Any],
        request_id: str,
        method: str,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        started = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(func, *args, **(kwargs or {})),
                timeout=timeout_seconds,
            )
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            logger.info(
                "%s complete",
                label,
                extra={
                    "component": label,
                    "request_id": request_id,
                    "method": method,
                    "duration_ms": round(elapsed_ms, 3),
                    "error_type": None,
                    "error_message": None,
                },
            )
            return result
        except asyncio.TimeoutError as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            elapsed_seconds = elapsed_ms / 1000.0
            timeout_data = _build_timeout_error_data(
                request_id=request_id,
                label=label,
                timeout_seconds=timeout_seconds,
                elapsed_seconds=elapsed_seconds,
            )
            logger.error(
                "%s timeout; request will fail without backend shutdown",
                label,
                extra={
                    "component": label,
                    "request_id": request_id,
                    "method": method,
                    "duration_ms": round(elapsed_ms, 3),
                    "error_type": "TimeoutError",
                    "error_message": f"{label} timed out after {timeout_seconds}s",
                    "timeout_code": timeout_data["code"],
                    "timeout_phase": timeout_data["phase"],
                },
            )
            raise RequestTimeoutError(
                f"{label} timed out after {timeout_seconds}s",
                error_data=timeout_data,
            ) from exc

    # ------------------------------------------------------------------
    # Note ID resolution
    # ------------------------------------------------------------------

    async def resolve_note_id(
        self,
        session_id: str,
        raw_id: str,
        mgr: Any,
        timeout: float,
        request_id: str,
        method: str,
        *,
        notes_cache: list[dict[str, object]] | None = None,
    ) -> str | None:
        """Resolve a full or prefix note_id to the full UUID.

        The agent may provide an 8-char prefix from [SESSION_NOTES] context.
        We list notes and match by prefix.  Returns None if no match found.

        Pass *notes_cache* to avoid repeated list_notes calls in batch operations.
        """
        raw_id = raw_id.strip() if isinstance(raw_id, str) else ""
        if not raw_id:
            return None
        if raw_id.lower() in {"session_pad", "default", "default_tab"}:
            pad = await self.run_blocking_with_timeout(
                label="notes.resolve_session_pad",
                timeout_seconds=timeout,
                func=mgr.get_or_create_session_pad,
                args=(session_id,),
                request_id=request_id,
                method=method,
            )
            return str(pad.get("note_id", "") or "")
        if notes_cache is not None:
            notes = notes_cache
        else:
            notes = await self.run_blocking_with_timeout(
                label="notes.list_for_resolve",
                timeout_seconds=timeout,
                func=mgr.list_notes,
                args=(session_id,),
                kwargs={"limit": 200},
                request_id=request_id,
                method=method,
            )
        prefix_matches: list[str] = []
        for note in notes:
            nid = note.get("note_id", "")
            if nid == raw_id:
                return nid  # Exact match always wins.
            if nid.startswith(raw_id):
                prefix_matches.append(nid)
        if len(prefix_matches) == 1:
            return prefix_matches[0]
        if len(prefix_matches) > 1:
            logger.warning(
                "Ambiguous note ID prefix '%s' matches %d notes",
                raw_id,
                len(prefix_matches),
            )
        return None

    # ------------------------------------------------------------------
    # Prompt task lifecycle
    # ------------------------------------------------------------------

    def track_prompt_task(
        self,
        request_id: str,
        client: Any,
        task: asyncio.Task[None],
    ) -> None:
        """Track an active prompt task and clean up indexes on completion."""
        self._active_prompt_tasks[request_id] = task
        self._client_prompt_index.setdefault(client.address, set()).add(request_id)

        # Capture references for the callback closure
        active_prompt_tasks = self._active_prompt_tasks
        cancelled_prompt_requests = self._cancelled_prompt_requests
        pending_tool_confirmations = self._pending_tool_confirmations
        pending_screen_captures = self._pending_screen_captures
        client_prompt_index = self._client_prompt_index
        client_address = client.address

        def _cleanup(_completed_task: asyncio.Task[None]) -> None:
            active_prompt_tasks.pop(request_id, None)
            cancelled_prompt_requests.discard(request_id)
            pending_confirmation = pending_tool_confirmations.pop(request_id, None)
            if pending_confirmation is not None:
                pending_future = pending_confirmation[1]
                if not pending_future.done():
                    pending_future.set_result(False)
            pending_capture = pending_screen_captures.pop(request_id, None)
            if pending_capture is not None:
                _, capture_future = pending_capture
                if not capture_future.done():
                    capture_future.set_result(None)
            request_ids = client_prompt_index.get(client_address)
            if not request_ids:
                return
            request_ids.discard(request_id)
            if not request_ids:
                client_prompt_index.pop(client_address, None)

        task.add_done_callback(_cleanup)

    # ------------------------------------------------------------------
    # Client-scoped cancellation
    # ------------------------------------------------------------------

    def cancel_requests_for_client(self, client_address: str) -> int:
        cancelled_count = 0
        for request_id in list(self._client_prompt_index.get(client_address, set())):
            task = self._active_prompt_tasks.get(request_id)
            if task and not task.done():
                self._cancelled_prompt_requests.add(request_id)
                pending_confirmation = self._pending_tool_confirmations.pop(request_id, None)
                if pending_confirmation is not None:
                    _, pending_future = pending_confirmation
                    if not pending_future.done():
                        pending_future.set_result(False)
                pending_capture = self._pending_screen_captures.pop(request_id, None)
                if pending_capture is not None:
                    _, capture_future = pending_capture
                    if not capture_future.done():
                        capture_future.set_result(None)
                task.cancel()
                cancelled_count += 1
        return cancelled_count

    # ------------------------------------------------------------------
    # Session broadcast
    # ------------------------------------------------------------------

    async def broadcast_session_refresh(
        self,
        *,
        session_id: str,
        request_id: str,
        method: str,
    ) -> None:
        updated_session = await self.run_blocking_with_timeout(
            label="db.get_session",
            timeout_seconds=self._db_timeout_seconds,
            func=self._memory_manager.get_session,
            args=(session_id,),
            request_id=request_id,
            method=method,
        )
        if updated_session is not None:
            await self._ipc_bridge.broadcast_session_event(
                action="updated",
                session=self._ipc_bridge.session_payload(updated_session),
            )

    # ------------------------------------------------------------------
    # Correlation ID extraction
    # ------------------------------------------------------------------

    @staticmethod
    def extract_correlation_id(request: Any) -> str:
        from agent_host.observability import generate_correlation_id

        raw = request.params.get("correlation_id")
        if isinstance(raw, str):
            trimmed = raw.strip()
            if trimmed:
                return trimmed[:128]
        return generate_correlation_id()
