"""Infrastructure IPC handlers (prompt, cancel, confirm, etc.).

Thin handler methods that delegate to RuntimeServices,
PromptOrchestrator, and other services.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
from typing import Any

from agent_host.core.services.prompt_service import (
    _format_exception_message,
    _model_supports_native_deep_think,
    _normalize_session_id,
    _parse_browse_profile_strict,
    _parse_deep_think_flag_strict,
    _parse_execution_mode_strict,
    _parse_memory_mode_strict,
    _parse_presentation_style_strict,
    _parse_stream_animation_style_strict,
    _parse_verbosity_level_strict,
    _resolve_model_timeout_seconds,
    _resolve_prompt_timeout_seconds,
    _VERBOSITY_LEVEL_BY_NAME,
)
from agent_host.contracts.types.domain import ExecutionMode, MemoryMode
from agent_host.observability import (
    reset_request_context,
    set_request_context,
)

logger = logging.getLogger(__name__)


class InfrastructureHandlers:
    """Infrastructure IPC handlers (prompt, cancel, confirm, etc.).

    Thin handler methods that delegate to RuntimeServices,
    PromptOrchestrator, and other services.
    """

    def __init__(
        self,
        *,
        runtime: Any,               # RuntimeServices
        orchestrator: Any,           # PromptOrchestrator
        tool_executor: Any,          # ToolExecutor
        gemini_client: Any,          # GeminiClient
        audit_logger: Any,           # AuditLogger
        config: Any,                 # Config
        server: Any,                 # IPCServer
        ipc_bridge: Any,             # IPCBridge
        memory_manager: Any,         # MemoryManager
        tools: list,                 # tool schemas
        base_system_instruction: str,
        # Shared mutable state
        active_prompt_tasks: dict,
        cancelled_prompt_requests: set,
        client_prompt_index: dict,
        pending_tool_confirmations: dict,
        pending_screen_captures: dict,
        pending_tool_proxies: dict,
        device_registry: dict,
        # Config values needed by handlers
        db_timeout_seconds: float,
        confirmation_timeout_seconds: float,
        tool_timeout_seconds: float,
        model_timeout_seconds: float,
        deep_think_model_timeout_multiplier: float,
        teacher_model_timeout_multiplier: float,
        continuation_model_timeout_multiplier: float,
        model_timeout_max_seconds: float,
        prompt_timeout_seconds: float,
        prompt_timeout_max_seconds: float,
        # Plan mode state — mutable dict shared by reference
        plan_mode_nlp_state: dict,  # {"ready": bool, "error": str|None}
        # Injected path normalizer (avoids core→adapter import)
        normalize_path_fn: Any = None,
        # The background preload task — set after construction
    ):
        self._runtime = runtime
        self._orchestrator = orchestrator
        self._tool_executor = tool_executor
        self._gemini_client = gemini_client
        self._audit_logger = audit_logger
        self._config = config
        self._server = server
        self._ipc_bridge = ipc_bridge
        self._memory_manager = memory_manager
        self._tools = tools
        self._base_system_instruction = base_system_instruction

        # Shared mutable state (by reference)
        self._active_prompt_tasks = active_prompt_tasks
        self._cancelled_prompt_requests = cancelled_prompt_requests
        self._client_prompt_index = client_prompt_index
        self._pending_tool_confirmations = pending_tool_confirmations
        self._pending_screen_captures = pending_screen_captures
        self._pending_tool_proxies = pending_tool_proxies
        self._device_registry = device_registry

        # Config values
        self._db_timeout_seconds = db_timeout_seconds
        self._confirmation_timeout_seconds = confirmation_timeout_seconds
        self._tool_timeout_seconds = tool_timeout_seconds
        self._model_timeout_seconds = model_timeout_seconds
        self._deep_think_model_timeout_multiplier = deep_think_model_timeout_multiplier
        self._teacher_model_timeout_multiplier = teacher_model_timeout_multiplier
        self._continuation_model_timeout_multiplier = continuation_model_timeout_multiplier
        self._model_timeout_max_seconds = model_timeout_max_seconds
        self._prompt_timeout_seconds = prompt_timeout_seconds
        self._prompt_timeout_max_seconds = prompt_timeout_max_seconds

        # Plan mode state
        self._plan_mode_nlp_state = plan_mode_nlp_state
        # Injected path normalizer (avoids core→adapter import)
        self._normalize_path = normalize_path_fn
        # Will be set after construction via set_nlp_preload_task()
        self._plan_mode_nlp_preload_task: asyncio.Task[None] | None = None

    def set_nlp_preload_task(self, task: asyncio.Task[None] | None) -> None:
        """Set the NLP preload task reference (created after handler construction)."""
        self._plan_mode_nlp_preload_task = task

    # ------------------------------------------------------------------
    # handle_prompt
    # ------------------------------------------------------------------

    async def handle_prompt(self, request: Any, client: Any) -> None:
        """Handle prompt requests from the SwiftUI frontend."""
        from agent_host.contracts.types.ipc_messages import ErrorMessage, StatusUpdate, ResultMessage

        correlation_id = self._runtime.extract_correlation_id(request)
        request_id = request.id
        context_tokens = set_request_context(
            correlation_id=correlation_id,
            request_id=request_id,
            method=request.method,
        )
        try:
            prompt_raw = request.params.get("prompt")
            model = request.params.get("model")
            raw_session_id = request.params.get("session_id")
            session_id_provided = "session_id" in request.params
            memory_mode_provided = "memory_mode" in request.params
            execution_mode_provided = "execution_mode" in request.params
            verbosity_provided = "verbosity" in request.params
            presentation_style_provided = "presentation_style" in request.params
            stream_animation_style_provided = "stream_animation" in request.params
            deep_think_provided = "deep_think" in request.params
            browse_profile_provided = "browse_profile" in request.params
            input_paths_raw = request.params.get("input_paths")

            if not isinstance(prompt_raw, str) or not prompt_raw.strip():
                error = ErrorMessage.invalid_request(
                    request_id,
                    "Missing 'prompt' parameter (must be a non-empty string)",
                )
                await client.send(error.to_bytes())
                return
            prompt = prompt_raw

            if session_id_provided:
                if not isinstance(raw_session_id, str) or not raw_session_id.strip():
                    await client.send(
                        ErrorMessage.invalid_request(request_id, "Invalid session_id").to_bytes()
                    )
                    return
                session_id = _normalize_session_id(raw_session_id, fallback="")
                if not session_id:
                    await client.send(
                        ErrorMessage.invalid_request(request_id, "Invalid session_id").to_bytes()
                    )
                    return
                existing_session = await self._runtime.run_blocking_with_timeout(
                    label="db.get_session",
                    timeout_seconds=self._db_timeout_seconds,
                    func=self._memory_manager.get_session,
                    args=(session_id,),
                    request_id=request_id,
                    method=request.method,
                )
                if existing_session is None:
                    await client.send(
                        ErrorMessage.invalid_request(
                            request_id,
                            f"Unknown session_id: {session_id}",
                        ).to_bytes()
                    )
                    return
            else:
                logger.warning(
                    "Prompt request missing session_id from client %s (request_id=%s)",
                    client.address,
                    request_id,
                )
                await client.send(
                    ErrorMessage.invalid_request(
                        request_id,
                        "Missing required 'session_id' parameter. "
                        "Create a session via 'session.create' first.",
                    ).to_bytes()
                )
                return

            if memory_mode_provided:
                parsed_mode = _parse_memory_mode_strict(request.params.get("memory_mode"))
                if parsed_mode is None:
                    await client.send(
                        ErrorMessage.invalid_request(
                            request_id,
                            f"Invalid memory_mode: {request.params.get('memory_mode')}",
                        ).to_bytes()
                    )
                    return
                memory_mode = parsed_mode
            elif existing_session is not None:
                # Respect persisted session mode unless request explicitly overrides it.
                memory_mode = existing_session.memory_mode
            else:
                memory_mode = MemoryMode.ON

            if verbosity_provided:
                verbosity_level = _parse_verbosity_level_strict(request.params.get("verbosity"))
                if verbosity_level is None:
                    await client.send(
                        ErrorMessage.invalid_request(
                            request_id,
                            (
                                f"Invalid verbosity: {request.params.get('verbosity')} "
                                "(expected: low, medium, high, extra_high)"
                            ),
                        ).to_bytes()
                    )
                    return
            else:
                verbosity_level = _VERBOSITY_LEVEL_BY_NAME["medium"]

            if execution_mode_provided:
                execution_mode = _parse_execution_mode_strict(request.params.get("execution_mode"))
                if execution_mode is None:
                    await client.send(
                        ErrorMessage.invalid_request(
                            request_id,
                            (
                                f"Invalid execution_mode: {request.params.get('execution_mode')} "
                                "(expected: direct, plan, teacher)"
                            ),
                        ).to_bytes()
                    )
                    return
            else:
                execution_mode = ExecutionMode.DIRECT

            plan_mode_nlp_ready = self._plan_mode_nlp_state.get("ready", False)
            plan_mode_nlp_error = self._plan_mode_nlp_state.get("error")
            plan_mode_nlp_preload_task = self._plan_mode_nlp_preload_task

            if execution_mode == ExecutionMode.PLAN and not plan_mode_nlp_ready:
                if plan_mode_nlp_preload_task is not None and not plan_mode_nlp_preload_task.done():
                    try:
                        await asyncio.wait_for(
                            asyncio.shield(plan_mode_nlp_preload_task),
                            timeout=8.0,
                        )
                    except asyncio.TimeoutError:
                        await client.send(
                            ErrorMessage.invalid_request(
                                request_id,
                                "Plan mode is unavailable: NLP classifier is still initializing.",
                            ).to_bytes()
                        )
                        return
                # Re-read after potential wait
                plan_mode_nlp_ready = self._plan_mode_nlp_state.get("ready", False)
                plan_mode_nlp_error = self._plan_mode_nlp_state.get("error")
                if not plan_mode_nlp_ready:
                    reason = plan_mode_nlp_error or "plan clarification classifier failed to initialize"
                    await client.send(
                        ErrorMessage.invalid_request(
                            request_id,
                            (
                                "Plan mode is unavailable because NLP classifier startup failed: "
                                f"{reason}"
                            ),
                        ).to_bytes()
                    )
                    return

            if presentation_style_provided:
                presentation_style = _parse_presentation_style_strict(
                    request.params.get("presentation_style")
                )
                if presentation_style is None:
                    await client.send(
                        ErrorMessage.invalid_request(
                            request_id,
                            (
                                f"Invalid presentation_style: {request.params.get('presentation_style')} "
                                "(expected: readable_pro, glass_editorial, dense_technical)"
                            ),
                        ).to_bytes()
                    )
                    return
            else:
                presentation_style = "readable_pro"

            if stream_animation_style_provided:
                stream_animation_style = _parse_stream_animation_style_strict(
                    request.params.get("stream_animation")
                )
                if stream_animation_style is None:
                    await client.send(
                        ErrorMessage.invalid_request(
                            request_id,
                            (
                                f"Invalid stream_animation: {request.params.get('stream_animation')} "
                                "(expected: wave_reveal, typewriter_luxe, minimal_motion)"
                            ),
                        ).to_bytes()
                    )
                    return
            else:
                stream_animation_style = "wave_reveal"

            if deep_think_provided:
                deep_think = _parse_deep_think_flag_strict(request.params.get("deep_think"))
                if deep_think is None:
                    await client.send(
                        ErrorMessage.invalid_request(
                            request_id,
                            "Invalid deep_think: expected boolean true or false",
                        ).to_bytes()
                    )
                    return
            else:
                deep_think = False

            if browse_profile_provided:
                browse_profile = _parse_browse_profile_strict(request.params.get("browse_profile"))
                if browse_profile is None:
                    await client.send(
                        ErrorMessage.invalid_request(
                            request_id,
                            (
                                f"Invalid browse_profile: {request.params.get('browse_profile')} "
                                "(expected: strict, standard, flexible)"
                            ),
                        ).to_bytes()
                    )
                    return
            else:
                browse_profile = "standard"

            if deep_think:
                requested_model = model if isinstance(model, str) and model.strip() else self._config.model_name
                if not _model_supports_native_deep_think(requested_model):
                    await client.send(
                        ErrorMessage.invalid_request(
                            request_id,
                            (
                                "Deep-think mode requires a reasoning-enabled model with native "
                                f"thinking controls (got '{requested_model}'). "
                                "Use Gemini 3 or Gemini 2.5."
                            ),
                        ).to_bytes()
                    )
                    return

            input_paths: list[str] = []
            if input_paths_raw is not None:
                if not isinstance(input_paths_raw, list):
                    await client.send(
                        ErrorMessage.invalid_request(
                            request_id,
                            "Invalid input_paths: expected array of path strings",
                        ).to_bytes()
                    )
                    return
                if len(input_paths_raw) > 100:
                    await client.send(
                        ErrorMessage.invalid_request(
                            request_id,
                            "Too many input_paths: maximum is 100",
                        ).to_bytes()
                    )
                    return
                seen_paths: set[str] = set()
                for idx, raw_path in enumerate(input_paths_raw):
                    if not isinstance(raw_path, str) or not raw_path.strip():
                        await client.send(
                            ErrorMessage.invalid_request(
                                request_id,
                                f"Invalid input_paths[{idx}] (must be non-empty string)",
                            ).to_bytes()
                        )
                        return
                    _path_result = self._normalize_path(
                        raw_path,
                        allowed_roots=list(self._config.allowed_roots),
                        must_exist=True,
                    )
                    if not _path_result.is_ok:
                        await client.send(
                            ErrorMessage.invalid_request(
                                request_id,
                                f"Invalid input_paths[{idx}]: {_path_result.error.message}",
                            ).to_bytes()
                        )
                        return
                    normalized = _path_result.unwrap()
                    normalized_str = str(normalized)
                    if normalized_str in seen_paths:
                        continue
                    seen_paths.add(normalized_str)
                    input_paths.append(normalized_str)

            effective_model_timeout = _resolve_model_timeout_seconds(
                base_timeout_seconds=self._model_timeout_seconds,
                deep_think=deep_think,
                execution_mode=execution_mode,
                is_continuation=True,
                deep_think_multiplier=self._deep_think_model_timeout_multiplier,
                teacher_multiplier=self._teacher_model_timeout_multiplier,
                continuation_multiplier=self._continuation_model_timeout_multiplier,
                max_timeout_seconds=self._model_timeout_max_seconds,
            )
            effective_prompt_timeout_seconds = _resolve_prompt_timeout_seconds(
                base_timeout_seconds=self._prompt_timeout_seconds,
                model_timeout_seconds=effective_model_timeout,
                tool_timeout_seconds=self._tool_timeout_seconds,
                deep_think=deep_think,
                execution_mode=execution_mode,
                max_timeout_seconds=self._prompt_timeout_max_seconds,
            )

            # Reject duplicate in-flight request ids to avoid ambiguous cancellation/routing.
            if request_id in self._active_prompt_tasks and not self._active_prompt_tasks[request_id].done():
                await client.send(
                    ErrorMessage.invalid_request(
                        request_id, "A request with this id is already in progress"
                    ).to_bytes()
                )
                return

            task_start_gate = asyncio.Event()
            orchestrator = self._orchestrator
            ipc_bridge = self._ipc_bridge

            async def _run_prompt_with_timeout() -> None:
                # Prevent a startup race where the task runs before it is indexed
                # as in-flight for request-scoped status/result routing.
                await task_start_gate.wait()
                try:
                    await asyncio.wait_for(
                        orchestrator.process_prompt(
                            request,
                            client,
                            prompt,
                            model,
                            session_id,
                            memory_mode,
                            execution_mode,
                            input_paths,
                            verbosity_level,
                            presentation_style,
                            stream_animation_style,
                            browse_profile,
                            deep_think,
                            correlation_id,
                        ),
                        timeout=effective_prompt_timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    timeout_data = {
                        "code": "prompt_timeout",
                        "request_id": request_id,
                        "phase": "prompt",
                        "operation": "prompt",
                        "timeout_seconds": round(float(effective_prompt_timeout_seconds), 3),
                        "elapsed_seconds": round(float(effective_prompt_timeout_seconds), 3),
                        "user_message": (
                            "The request exceeded the overall prompt timeout budget. "
                            "Your backend connection is still active, so you can retry."
                        ),
                    }
                    await ipc_bridge.send_request_error(
                        client=client,
                        request_id=request_id,
                        code=ErrorMessage.REQUEST_TIMEOUT,
                        message=str(timeout_data["user_message"]),
                        data=timeout_data,
                    )

            task = asyncio.create_task(_run_prompt_with_timeout())
            self._runtime.track_prompt_task(request_id, client, task)
            task_start_gate.set()
        finally:
            reset_request_context(context_tokens)

    # ------------------------------------------------------------------
    # handle_cancel
    # ------------------------------------------------------------------

    async def handle_cancel(self, request: Any, client: Any) -> None:
        """Handle cancel requests from the SwiftUI frontend."""
        from agent_host.contracts.types.ipc_messages import ErrorMessage, StatusUpdate, ResultMessage

        target_request_id = request.params.get("request_id")
        cancelled_request_ids: list[str] = []

        def _cancel_request(request_id: str) -> None:
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
                cancelled_request_ids.append(request_id)

        if isinstance(target_request_id, str) and target_request_id:
            owned_requests = self._client_prompt_index.get(client.address, set())
            if target_request_id not in owned_requests:
                await client.send(
                    ErrorMessage.invalid_request(
                        request.id,
                        "Request is not active for this client",
                    ).to_bytes()
                )
                await client.send(StatusUpdate.complete(request.id).to_bytes())
                return
            _cancel_request(target_request_id)
        else:
            for request_id in list(self._client_prompt_index.get(client.address, set())):
                _cancel_request(request_id)

        if not cancelled_request_ids:
            await client.send(
                ErrorMessage.invalid_request(request.id, "No active request to cancel").to_bytes()
            )
            await client.send(StatusUpdate.complete(request.id).to_bytes())
            return

        result = ResultMessage.create(
            request.id,
            f"Cancellation requested for {len(cancelled_request_ids)} active request(s).",
        )
        await client.send(result.to_bytes())
        await client.send(StatusUpdate.complete(request.id).to_bytes())

    # ------------------------------------------------------------------
    # handle_tool_confirm
    # ------------------------------------------------------------------

    async def handle_tool_confirm(self, request: Any, client: Any) -> None:
        """Handle explicit confirmation/denial for pending destructive tool execution."""
        from agent_host.contracts.types.ipc_messages import ErrorMessage, StatusUpdate, ResultMessage

        target_request_id = request.params.get("request_id")
        approved_value = request.params.get("approved")
        if not isinstance(target_request_id, str) or not target_request_id:
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing request_id").to_bytes()
            )
            await client.send(StatusUpdate.complete(request.id).to_bytes())
            return
        if not isinstance(approved_value, bool):
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing approved boolean").to_bytes()
            )
            await client.send(StatusUpdate.complete(request.id).to_bytes())
            return

        pending = self._pending_tool_confirmations.get(target_request_id)
        if pending is None:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    f"No pending confirmation for request: {target_request_id}",
                ).to_bytes()
            )
            await client.send(StatusUpdate.complete(request.id).to_bytes())
            return

        owner_client_id, pending_future = pending
        if owner_client_id != client.address:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    "Confirmation must be sent by the same client that initiated the request",
                ).to_bytes()
            )
            await client.send(StatusUpdate.complete(request.id).to_bytes())
            return

        if not pending_future.done():
            pending_future.set_result(approved_value)

        acknowledgement = ResultMessage.create(
            request.id,
            (
                f"Confirmation {'approved' if approved_value else 'denied'} "
                f"for request {target_request_id}."
            ),
        )
        await client.send(acknowledgement.to_bytes())
        await client.send(StatusUpdate.complete(request.id).to_bytes())

    # ------------------------------------------------------------------
    # handle_screen_capture
    # ------------------------------------------------------------------

    async def handle_screen_capture(self, request: Any, client: Any) -> None:
        """Handle screen capture response from the frontend."""
        from agent_host.contracts.types.ipc_messages import ErrorMessage, StatusUpdate, ResultMessage

        target_request_id = request.params.get("request_id")
        if not isinstance(target_request_id, str) or not target_request_id:
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing request_id").to_bytes()
            )
            await client.send(StatusUpdate.complete(request.id).to_bytes())
            return

        pending = self._pending_screen_captures.get(target_request_id)
        if pending is None:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    f"No pending screen capture for request: {target_request_id}",
                ).to_bytes()
            )
            await client.send(StatusUpdate.complete(request.id).to_bytes())
            return

        owner_client_id, capture_future = pending
        if owner_client_id != client.address:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    "Capture response must come from the requesting client",
                ).to_bytes()
            )
            await client.send(StatusUpdate.complete(request.id).to_bytes())
            return

        if not capture_future.done():
            capture_future.set_result({
                "image_data": request.params.get("image_data") or "",
                "ocr_text": request.params.get("ocr_text") or "",
                "width": request.params.get("width") or 0,
                "height": request.params.get("height") or 0,
                "error": request.params.get("error") or "",
            })

        acknowledgement = ResultMessage.create(
            request.id, "Screen capture received."
        )
        await client.send(acknowledgement.to_bytes())
        await client.send(StatusUpdate.complete(request.id).to_bytes())

    # ------------------------------------------------------------------
    # handle_device_register
    # ------------------------------------------------------------------

    async def handle_device_register(self, request: Any, client: Any) -> None:
        """Register the connected device manifest for capability-aware tool routing."""
        from agent_host.contracts.types.ipc_messages import ErrorMessage, StatusUpdate, ResultMessage

        device_id = request.params.get("device_id")
        platform = request.params.get("platform")
        device_name = request.params.get("device_name")
        app_version = request.params.get("app_version")
        raw_capabilities = request.params.get("capabilities", [])

        if not isinstance(device_id, str) or not device_id.strip():
            await client.send(
                ErrorMessage.invalid_request(request.id, "device_id is required").to_bytes()
            )
            await client.send(StatusUpdate.complete(request.id).to_bytes())
            return
        if not isinstance(platform, str) or not platform.strip():
            await client.send(
                ErrorMessage.invalid_request(request.id, "platform is required").to_bytes()
            )
            await client.send(StatusUpdate.complete(request.id).to_bytes())
            return
        if not isinstance(device_name, str) or not device_name.strip():
            await client.send(
                ErrorMessage.invalid_request(request.id, "device_name is required").to_bytes()
            )
            await client.send(StatusUpdate.complete(request.id).to_bytes())
            return
        if not isinstance(app_version, str) or not app_version.strip():
            await client.send(
                ErrorMessage.invalid_request(request.id, "app_version is required").to_bytes()
            )
            await client.send(StatusUpdate.complete(request.id).to_bytes())
            return
        if not isinstance(raw_capabilities, list):
            await client.send(
                ErrorMessage.invalid_request(request.id, "capabilities must be a list").to_bytes()
            )
            await client.send(StatusUpdate.complete(request.id).to_bytes())
            return

        capabilities = sorted(
            {
                capability.strip()
                for capability in raw_capabilities
                if isinstance(capability, str) and capability.strip()
            }
        )
        raw_supported_tools = request.params.get("supported_tools", [])
        supported_tools = sorted(
            {
                t.strip()
                for t in (raw_supported_tools if isinstance(raw_supported_tools, list) else [])
                if isinstance(t, str) and t.strip()
            }
        )
        payload = {
            "device_id": device_id.strip(),
            "platform": platform.strip(),
            "device_name": device_name.strip(),
            "app_version": app_version.strip(),
            "capabilities": capabilities,
            "supported_tools": supported_tools,
            "registered_at": time.time(),
        }
        self._device_registry[client.address] = payload
        await client.send(
            ResultMessage.create(request.id, json.dumps(payload)).to_bytes()
        )
        await client.send(StatusUpdate.complete(request.id).to_bytes())

    # ------------------------------------------------------------------
    # handle_ping
    # ------------------------------------------------------------------

    async def handle_ping(self, request: Any, client: Any) -> None:
        """Handles ping requests for health check."""
        from agent_host.contracts.types.ipc_messages import ResultMessage

        result = ResultMessage.create(request.id, "pong")
        await client.send(result.to_bytes())

    # ------------------------------------------------------------------
    # handle_system_diagnostics
    # ------------------------------------------------------------------

    async def handle_system_diagnostics(self, request: Any, client: Any) -> None:
        """Handles comprehensive end-to-end system diagnostics checks."""
        from agent_host.contracts.types.ipc_messages import ResultMessage

        diagnostics: dict[str, Any] = {
            "status": "ok",
            "api_key_valid": False,
            "db_connected": False,
            "tools_ready": False,
            "errors": []
        }

        # 1. Check API Key
        api_key = os.environ.get("GEMINI_API_KEY", "").strip() or os.environ.get("GOOGLE_API_KEY", "").strip()
        if api_key and len(api_key) > 10:
            diagnostics["api_key_valid"] = True
        else:
            diagnostics["status"] = "error"
            diagnostics["errors"].append("GEMINI_API_KEY or GOOGLE_API_KEY environment variable is missing or invalid.")

        # 2. Check Database Connection
        try:
            if self._memory_manager is not None:
                await asyncio.to_thread(self._memory_manager.list_sessions, limit=1)
                diagnostics["db_connected"] = True
            else:
                diagnostics["status"] = "error"
                diagnostics["errors"].append("MemoryManager is not initialized.")
        except Exception as e:
            diagnostics["status"] = "error"
            diagnostics["errors"].append(f"Database connection failed: {e}")

        # 3. Check Tools Readiness
        try:
            core_tools = ["search_files", "browse_web"]
            registered_tools = self._tool_executor.list_plugins()
            missing_tools = [t for t in core_tools if t not in registered_tools]
            if not missing_tools:
                diagnostics["tools_ready"] = True
            else:
                diagnostics["status"] = "error"
                diagnostics["errors"].append(f"Core tools missing: {', '.join(missing_tools)}")
        except Exception as e:
            diagnostics["status"] = "error"
            diagnostics["errors"].append(f"Tool registry check failed: {e}")

        # Per-plugin health status
        try:
            plugin_health = self._tool_executor.get_health_status()
            diagnostics["plugin_health"] = plugin_health
        except Exception as exc:
            diagnostics["plugin_health_error"] = str(exc)

        result = ResultMessage.create(request.id, json.dumps(diagnostics))
        await client.send(result.to_bytes())

    # ------------------------------------------------------------------
    # handle_tool_execute_response
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_proxy_result(obj: Any) -> Any:
        """Recursively sanitize proxy result to ensure JSON-serializable values."""
        if obj is None:
            return ""
        if isinstance(obj, bool):
            return obj
        if isinstance(obj, (int, float)):
            if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
                return 0
            return obj
        if isinstance(obj, str):
            return obj
        if isinstance(obj, dict):
            return {str(k): InfrastructureHandlers._sanitize_proxy_result(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [InfrastructureHandlers._sanitize_proxy_result(item) for item in obj]
        # Fallback: convert to string
        return str(obj)

    async def handle_tool_execute_response(self, request: Any, client: Any) -> None:
        """Handle tool execution result proxied back from the mobile device."""
        from agent_host.contracts.types.ipc_messages import ErrorMessage, StatusUpdate, ResultMessage

        proxy_key = request.params.get("proxy_key", "")
        result = request.params.get("result", {})
        if not isinstance(proxy_key, str) or not proxy_key.strip():
            await client.send(
                ErrorMessage.invalid_request(request.id, "proxy_key is required").to_bytes()
            )
            await client.send(StatusUpdate.complete(request.id).to_bytes())
            return

        pending = self._pending_tool_proxies.pop(proxy_key, None)
        if pending is None:
            logger.warning("No pending tool proxy for key: %s", proxy_key)
            await client.send(StatusUpdate.complete(request.id).to_bytes())
            return

        owner_addr, proxy_future = pending
        if owner_addr != client.address:
            logger.warning(
                "Tool proxy response from wrong client: expected %s, got %s",
                owner_addr, client.address,
            )
            # Re-insert so the correct client can still resolve it
            self._pending_tool_proxies[proxy_key] = pending
            await client.send(StatusUpdate.complete(request.id).to_bytes())
            return

        if not proxy_future.done():
            # Normalize result to match ToolExecutor output format
            if not isinstance(result, dict):
                result = {"status": "failed", "error": "Invalid result from device"}
            # Sanitize the result to remove non-JSON-serializable values
            result = self._sanitize_proxy_result(result)
            tool_name = proxy_key.split(":")[1] if ":" in proxy_key else "unknown"
            try:
                _payload_size = len(json.dumps(result, default=str))
                logger.info("Proxy result payload size: %d bytes for %s", _payload_size, proxy_key)
            except Exception:
                pass
            proxy_future.set_result({
                "tool": tool_name,
                "ok": result.get("status") == "success",
                "timestamp": time.time(),
                "started_at": time.time(),
                "finished_at": time.time(),
                "latency_ms": 0,
                "output": result,
            })
            logger.info("Resolved tool proxy %s ok=%s", proxy_key, result.get("status") == "success")

        await client.send(
            ResultMessage.create(request.id, "Tool execution result received.").to_bytes()
        )
        await client.send(StatusUpdate.complete(request.id).to_bytes())

    # ------------------------------------------------------------------
    # handle_client_disconnect
    # ------------------------------------------------------------------

    async def handle_client_disconnect(self, disconnected_client: Any) -> None:
        cancelled = self._runtime.cancel_requests_for_client(disconnected_client.address)
        self._device_registry.pop(disconnected_client.address, None)
        if cancelled > 0:
            logger.info(
                "Cancelled %s in-flight request(s) after client disconnect: %s",
                cancelled,
                disconnected_client.address,
            )
