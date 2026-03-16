"""Prompt processing orchestrator.

Contains the main prompt processing pipeline, extracted from
``main.py``'s ``run_server()`` closure.  The :class:`PromptOrchestrator`
receives **all** dependencies via its constructor so there are zero
closure captures from the outer scope.
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Callable, Optional

from google.genai import types

from agent_host.contracts.types.domain import ExecutionMode
from agent_host.contracts.types.tool_context import (
    ImageToolContext,
    NoteToolContext,
    ScreenToolContext,
)
from agent_host.core.services.prompt_service import (
    _format_exception_message,
    _format_tool_execution_output,
)
from agent_host.contracts.types.errors import (
    GeminiAPIError,
    GeminiRateLimitError,
    MalformedResponseError,
    SchemaNotFoundError,
    ToolExecutionError,
    ValidationFailedError,
)
from agent_host.contracts.types.ipc_messages import (
    ErrorMessage,
    ResultMessage,
    StatusUpdate,
    SystemMessage,
    ToolCallNotification,
    ToolCallStatus,
)
from agent_host.contracts.types.domain import MemoryMode, NOTE_TOOL_NAMES
from agent_host.observability import (
    reset_request_context,
    set_request_context,
)
from agent_host.response_sanitizer import (
    looks_like_json_payload,
    sanitize_user_visible_response,
)
from agent_host.system_prompt import inject_model_identity
from agent_host.tool_parser import ToolCallParser
from agent_host.core.services.prompt_service import (
    _resolve_model_timeout_seconds,
)

logger = logging.getLogger(__name__)


class PromptOrchestrator:
    """Orchestrates the full prompt processing pipeline.

    Receives all dependencies via constructor.  Mutable state dicts are
    shared **by reference** with the composition root (``main.py``).
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        *,
        # Services
        gemini_client: Any,
        memory_manager: Any,
        tool_executor: Any,
        ipc_bridge: Any,
        audit_logger: Any,
        server: Any,
        validator: Any,
        config: Any,
        # Dependency-injected factories & modules (F2 — no adapter imports)
        mode_handler_factory: Callable,
        plan_mode_ops: Any,
        plan_mode_prompts: Any,
        teacher_completion_tools: frozenset,
        # Data
        tools: list,
        base_system_instruction: str,
        async_plugins: dict,
        # Shared mutable state (by reference — do NOT copy)
        plan_mode_clarification_states: dict,
        plan_mode_sessions_with_plan: dict,
        plan_mode_option_learning_by_session: dict,
        plan_mode_option_learning_global: dict,
        pending_tool_confirmations: dict,
        pending_screen_captures: dict,
        pending_tool_proxies: dict,
        active_prompt_tasks: dict,
        cancelled_prompt_requests: set,
        client_prompt_index: dict,
        device_registry: dict,
        # Config values
        confirmation_timeout_seconds: float,
        db_timeout_seconds: float,
        model_timeout_seconds: float,
        image_timeout_seconds: float,
        image_output_root: Path,
        image_model_override: str | None,
        deep_think_model_timeout_multiplier: float,
        teacher_model_timeout_multiplier: float,
        continuation_model_timeout_multiplier: float,
        model_timeout_max_seconds: float,
        tool_timeout_seconds: float,
        prompt_timeout_seconds: float,
        prompt_timeout_max_seconds: float,
        max_tool_chain_depth: int,
        read_screen_ocr_max_chars: int,
        read_screen_ocr_max_lines: int,
        destructive_tool_names: set,
        plan_mode_allowed_tools: set,
        # Closures from run_server
        run_blocking_with_timeout: Any,
        client_capabilities_for: Any,
        broadcast_session_refresh: Any,
        resolve_note_id: Any,
        # Exception class defined inside run_server()
        request_timeout_error_cls: type,
    ) -> None:
        # Services
        self._gemini_client = gemini_client
        self._memory_manager = memory_manager
        self._tool_executor = tool_executor
        self._ipc_bridge = ipc_bridge
        self._audit_logger = audit_logger
        self._server = server
        self._validator = validator
        self._config = config

        # Injected factories & modules (zero adapter imports in this file)
        self._mode_handler_factory = mode_handler_factory
        self._pm = plan_mode_ops       # plan mode state machine module
        self._pm_prompts = plan_mode_prompts  # plan mode prompts module
        self._teacher_completion_tools = teacher_completion_tools

        # Data
        self._tools = tools
        self._base_system_instruction = base_system_instruction
        self._async_plugins = async_plugins

        # Shared mutable state (by reference)
        self._plan_mode_clarification_states = plan_mode_clarification_states
        self._plan_mode_sessions_with_plan = plan_mode_sessions_with_plan
        self._plan_mode_option_learning_by_session = plan_mode_option_learning_by_session
        self._plan_mode_option_learning_global = plan_mode_option_learning_global
        self._pending_tool_confirmations = pending_tool_confirmations
        self._pending_screen_captures = pending_screen_captures
        self._pending_tool_proxies = pending_tool_proxies
        self._active_prompt_tasks = active_prompt_tasks
        self._cancelled_prompt_requests = cancelled_prompt_requests
        self._client_prompt_index = client_prompt_index
        self._device_registry = device_registry

        # Config values
        self._confirmation_timeout_seconds = confirmation_timeout_seconds
        self._db_timeout_seconds = db_timeout_seconds
        self._model_timeout_seconds = model_timeout_seconds
        self._image_timeout_seconds = image_timeout_seconds
        self._image_output_root = image_output_root
        self._image_model_override = image_model_override
        self._deep_think_model_timeout_multiplier = deep_think_model_timeout_multiplier
        self._teacher_model_timeout_multiplier = teacher_model_timeout_multiplier
        self._continuation_model_timeout_multiplier = continuation_model_timeout_multiplier
        self._model_timeout_max_seconds = model_timeout_max_seconds
        self._tool_timeout_seconds = tool_timeout_seconds
        self._prompt_timeout_seconds = prompt_timeout_seconds
        self._prompt_timeout_max_seconds = prompt_timeout_max_seconds
        self._max_tool_chain_depth = max_tool_chain_depth
        self._read_screen_ocr_max_chars = read_screen_ocr_max_chars
        self._read_screen_ocr_max_lines = read_screen_ocr_max_lines
        self._destructive_tool_names = destructive_tool_names
        self._plan_mode_allowed_tools = plan_mode_allowed_tools

        # Closures from run_server
        self._run_blocking = run_blocking_with_timeout
        self._client_capabilities_for = client_capabilities_for
        self._broadcast_session_refresh = broadcast_session_refresh
        self._resolve_note_id = resolve_note_id

        # Exception class
        self._RequestTimeoutError = request_timeout_error_cls

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def process_prompt(
        self,
        request: Any,
        client: Any,
        prompt: str,
        model: Optional[str],
        session_id: str,
        memory_mode: MemoryMode,
        execution_mode: ExecutionMode,
        input_paths: list[str],
        verbosity_level: int,
        presentation_style: str,
        stream_animation_style: str,
        browse_profile: str,
        deep_think: bool,
        correlation_id: str,
    ) -> None:
        """Process a prompt request without blocking the IPC event loop."""
        request_id = request.id
        context_tokens = set_request_context(
            correlation_id=correlation_id,
            request_id=request_id,
            method=request.method,
            browse_profile=browse_profile,
        )

        try:
            plan_mode_auto_execute = False

            async def _send_mode_status(detail: str) -> None:
                trimmed = detail.strip() or "Working on your request..."
                if plan_mode_auto_execute:
                    payload = StatusUpdate.executing_plan(
                        request_id, trimmed
                    ).to_bytes()
                elif execution_mode == ExecutionMode.PLAN:
                    payload = StatusUpdate.planning(
                        request_id, trimmed
                    ).to_bytes()
                else:
                    payload = StatusUpdate.thinking(
                        request_id, trimmed
                    ).to_bytes()
                await self._ipc_bridge.send_request_message(
                    client=client,
                    request_id=request_id,
                    payload=payload,
                    require_in_flight=True,
                )

            # Log the model selection for debugging
            if model:
                logger.info(f"Model Selection Debug: Using frontend-specified model '{model}'")
                logger.info(f"Received prompt with model '{model}': {prompt[:100]}...")
            else:
                logger.info("Model Selection Debug: No model specified, using client default")
                logger.info(f"Received prompt (default model): {prompt[:100]}...")
            logger.info(
                (
                    "Prompt context: session_id=%s memory_mode=%s execution_mode=%s verbosity=%s deep_think=%s "
                    "presentation_style=%s stream_animation=%s browse_profile=%s input_paths=%s"
                ),
                session_id,
                memory_mode.value,
                execution_mode.value,
                verbosity_level,
                deep_think,
                presentation_style,
                stream_animation_style,
                browse_profile,
                len(input_paths),
            )

            mode_handler = self._mode_handler_factory(ExecutionMode.DIRECT, {})  # default; overridden below if needed

            pre_gen_msg = mode_handler.get_pre_generation_status_message()
            if pre_gen_msg:
                await _send_mode_status(pre_gen_msg)

            prepared = await self._run_blocking(
                label="db.prepare_prompt_context",
                timeout_seconds=self._db_timeout_seconds,
                func=self._memory_manager.prepare_prompt_context,
                args=(),
                kwargs={
                    "session_id": session_id,
                    "prompt": prompt,
                    "memory_mode": memory_mode,
                },
                request_id=request_id,
                method=request.method,
            )
            prompt_for_model = prepared.augmented_prompt
            resolved_user_prompt = prompt
            clarification_context_block = ""
            unified_planning_context_block = ""
            plan_mode_discovery_budget = self._pm._parse_plan_mode_discovery_budget()
            plan_mode_clarification_required = self._pm._parse_plan_mode_clarification_required()
            latest_plan_clarification_state = None  # PlanClarificationState | None
            plan_mode_clarification_resolved_this_turn = False
            session_learning_for_ranking: dict[str, dict[str, float]] | None = None
            if memory_mode != MemoryMode.OFF:
                session_learning_for_ranking = self._plan_mode_option_learning_by_session.setdefault(
                    session_id,
                    {},
                )
            global_learning_for_ranking = self._plan_mode_option_learning_global if memory_mode != MemoryMode.OFF else None

            if execution_mode != ExecutionMode.PLAN:
                self._plan_mode_clarification_states.pop(session_id, None)
                self._plan_mode_sessions_with_plan.pop(session_id, None)

            # P4: Use TTL-based check (600s) instead of simple membership
            # to avoid stale follow-up detection after plans expire.
            _plan_ts = self._plan_mode_sessions_with_plan.get(session_id, 0)
            _session_has_live_plan = (time.time() - _plan_ts) < 600 if _plan_ts else False
            if not _session_has_live_plan:
                self._plan_mode_sessions_with_plan.pop(session_id, None)
            plan_mode_is_followup = (
                execution_mode == ExecutionMode.PLAN
                and self._pm._is_plan_mode_followup(prompt, _session_has_live_plan)
            )
            plan_mode_auto_execute = (
                plan_mode_is_followup
                and self._pm._is_plan_mode_execution_approval(prompt)
            )
            if plan_mode_auto_execute:
                execution_mode = ExecutionMode.DIRECT
                mode_handler = self._mode_handler_factory(ExecutionMode.DIRECT, {})
                logger.info(
                    "Plan Mode auto-switch to DIRECT for request %s (user approved execution)",
                    request_id,
                )
                await self._ipc_bridge.send_request_message(
                    client=client,
                    request_id=request_id,
                    payload=StatusUpdate.executing_plan(
                        request_id,
                        "Executing your approved plan...",
                    ).to_bytes(),
                    require_in_flight=True,
                )

            # Compute once using the effective root prompt (not a raw clarification reply).
            _effective_root_prompt = prompt
            if execution_mode == ExecutionMode.PLAN:
                clarification_state = self._plan_mode_clarification_states.get(session_id)
                if (
                    clarification_state is not None
                    and not self._pm._looks_like_plan_clarification_reply(prompt, clarification_state)
                ):
                    # User changed direction -> reset stale clarification flow.
                    self._plan_mode_clarification_states.pop(session_id, None)
                    clarification_state = None
                elif clarification_state is not None:
                    _effective_root_prompt = clarification_state.root_prompt

            plan_mode_requires_unified_planning = (
                execution_mode == ExecutionMode.PLAN
                and self._pm._prompt_has_actionable_file_operation_intent(_effective_root_prompt)
            )

            if execution_mode == ExecutionMode.PLAN and not plan_mode_is_followup and self._pm._should_run_plan_mode_clarification(
                    prompt=prompt,
                    clarification_required=plan_mode_clarification_required,
                    requires_unified_planning=plan_mode_requires_unified_planning,
                ):
                    if (
                        clarification_state is not None
                        and self._pm._looks_like_plan_clarification_reply(prompt, clarification_state)
                    ):
                        accepted = self._pm._update_clarification_state_from_reply(
                            state=clarification_state,
                            prompt=prompt,
                            session_learning=session_learning_for_ranking,
                            global_learning=global_learning_for_ranking,
                        )
                        if not accepted:
                            # P2: Count rejections toward the global max-rounds
                            # limit so the user cannot get stuck in an infinite
                            # "I couldn't parse your answer" loop.
                            clarification_state.asked_rounds += 1
                            max_rounds = self._pm._parse_plan_mode_clarification_max_rounds()
                            if clarification_state.asked_rounds >= max_rounds:
                                # Force-resolve: treat raw text as free-form
                                # answer for all unanswered dimensions.
                                for dim in (clarification_state.question_dimensions or []):
                                    if dim not in clarification_state.answered_dimensions:
                                        clarification_state.answered_dimensions[dim] = prompt.strip()
                                logger.info(
                                    "Plan clarification force-resolved after %d rounds (session %s)",
                                    clarification_state.asked_rounds,
                                    session_id,
                                )
                                # Fall through to the accepted path below (line 2741+)
                            else:
                                score = self._pm._compute_plan_mode_clarification_score(
                                    prompt=clarification_state.root_prompt,
                                    missing_dimensions=self._pm._plan_mode_missing_clarification_dimensions(
                                        clarification_state.root_prompt
                                    ),
                                    asked_rounds=clarification_state.asked_rounds,
                                )
                                clarification_text = self._pm._build_plan_mode_clarification_turn_response(
                                    state=clarification_state,
                                    session_learning=session_learning_for_ranking,
                                    global_learning=global_learning_for_ranking,
                                    score=score,
                                )
                                await self._ipc_bridge.send_request_message(
                                    client=client,
                                    request_id=request_id,
                                    payload=StatusUpdate.planning(
                                        request_id,
                                        "I couldn't confidently parse that answer. Quick retry:",
                                    ).to_bytes(),
                                    require_in_flight=True,
                                )
                                if self._ipc_bridge.is_request_in_flight(request_id) and self._ipc_bridge.client_is_connected(client):
                                    streamer = self._server.create_streaming_handler(client, request_id)
                                    await streamer.stream_words(clarification_text)
                                await self._ipc_bridge.send_request_message(
                                    client=client,
                                    request_id=request_id,
                                    payload=ResultMessage.create(request_id, clarification_text).to_bytes(),
                                    require_in_flight=True,
                                )
                                if self._ipc_bridge.is_request_in_flight(request_id):
                                    await self._run_blocking(
                                        label="db.record_interaction",
                                        timeout_seconds=self._db_timeout_seconds,
                                        func=self._memory_manager.record_interaction,
                                        args=(),
                                        kwargs={
                                            "session_id": session_id,
                                            "memory_mode": memory_mode,
                                            "user_prompt": prompt,
                                            "assistant_response": clarification_text,
                                            "model_name": model or self._config.model_name,
                                        },
                                        request_id=request_id,
                                        method=request.method,
                                    )
                                await self._ipc_bridge.send_request_message(
                                    client=client,
                                    request_id=request_id,
                                    payload=StatusUpdate.complete(request_id).to_bytes(),
                                    require_in_flight=True,
                                    )
                                return

                        for answered_dimension, selected_option in clarification_state.option_answers.items():
                            if not selected_option:
                                continue
                            if session_learning_for_ranking is not None:
                                self._pm._update_plan_option_learning(
                                    session_learning_for_ranking,
                                    dimension=answered_dimension,
                                    option_key=selected_option,
                                    weight=1.0,
                                )
                            if global_learning_for_ranking is not None:
                                self._pm._update_plan_option_learning(
                                    global_learning_for_ranking,
                                    dimension=answered_dimension,
                                    option_key=selected_option,
                                    weight=0.45,
                                )

                        resolved_user_prompt = clarification_state.root_prompt
                        clarification_context_block = self._pm._build_plan_clarification_context_block(
                            clarification_state,
                            session_learning=session_learning_for_ranking,
                            global_learning=global_learning_for_ranking,
                        )
                        latest_plan_clarification_state = clarification_state
                        plan_mode_clarification_resolved_this_turn = True
                        self._plan_mode_clarification_states.pop(session_id, None)
                        await self._ipc_bridge.send_request_message(
                            client=client,
                            request_id=request_id,
                            payload=StatusUpdate.planning(
                                request_id,
                                "Great, drafting a tailored plan from your answers...",
                            ).to_bytes(),
                            require_in_flight=True,
                        )
                    elif clarification_state is None and self._pm._prompt_requires_plan_mode_clarification(prompt):
                        self._plan_mode_sessions_with_plan.pop(session_id, None)
                        new_state = self._pm._initialize_plan_clarification_state(prompt)
                        if len(self._plan_mode_clarification_states) > 100:
                            _evict = list(self._plan_mode_clarification_states)[:20]
                            for _ek in _evict:
                                self._plan_mode_clarification_states.pop(_ek, None)
                        self._plan_mode_clarification_states[session_id] = new_state
                        score = self._pm._compute_plan_mode_clarification_score(
                            prompt=prompt,
                            missing_dimensions=self._pm._plan_mode_missing_clarification_dimensions(prompt),
                            asked_rounds=0,
                        )
                        clarification_text = self._pm._build_plan_mode_clarification_turn_response(
                            state=new_state,
                            session_learning=session_learning_for_ranking,
                            global_learning=global_learning_for_ranking,
                            score=score,
                        )
                        await self._ipc_bridge.send_request_message(
                            client=client,
                            request_id=request_id,
                            payload=StatusUpdate.planning(
                                request_id,
                                "Need a quick clarification before drafting.",
                            ).to_bytes(),
                            require_in_flight=True,
                        )
                        if self._ipc_bridge.is_request_in_flight(request_id) and self._ipc_bridge.client_is_connected(client):
                            streamer = self._server.create_streaming_handler(client, request_id)
                            await streamer.stream_words(clarification_text)
                        await self._ipc_bridge.send_request_message(
                            client=client,
                            request_id=request_id,
                            payload=ResultMessage.create(request_id, clarification_text).to_bytes(),
                            require_in_flight=True,
                        )
                        if self._ipc_bridge.is_request_in_flight(request_id):
                            await self._run_blocking(
                                label="db.record_interaction",
                                timeout_seconds=self._db_timeout_seconds,
                                func=self._memory_manager.record_interaction,
                                args=(),
                                kwargs={
                                    "session_id": session_id,
                                    "memory_mode": memory_mode,
                                    "user_prompt": prompt,
                                    "assistant_response": clarification_text,
                                    "model_name": model or self._config.model_name,
                                },
                                request_id=request_id,
                                method=request.method,
                            )
                        await self._ipc_bridge.send_request_message(
                            client=client,
                            request_id=request_id,
                            payload=StatusUpdate.complete(request_id).to_bytes(),
                            require_in_flight=True,
                        )
                        return

            if resolved_user_prompt != prompt:
                prepared = await self._run_blocking(
                    label="db.prepare_prompt_context",
                    timeout_seconds=self._db_timeout_seconds,
                    func=self._memory_manager.prepare_prompt_context,
                    args=(),
                    kwargs={
                        "session_id": session_id,
                        "prompt": resolved_user_prompt,
                        "memory_mode": memory_mode,
                    },
                    request_id=request_id,
                    method=request.method,
                )
                prompt_for_model = prepared.augmented_prompt

            if clarification_context_block:
                prompt_for_model = f"{prompt_for_model}\n\n{clarification_context_block}"

            if input_paths:
                lines = [
                    "[USER_SELECTED_PATHS]",
                    "The user explicitly dropped/selected these paths for this request:",
                ]
                lines.extend(f"- {path}" for path in input_paths)
                lines.append(
                    "Treat this list as trusted user intent context and prioritize these paths when planning."
                )
                prompt_for_model = f"{prompt_for_model}\n\n" + "\n".join(lines)

            if execution_mode == ExecutionMode.PLAN and not plan_mode_is_followup:
                await _send_mode_status("Preparing unified planner context...")
                planner_bootstrap_goal = self._pm._sanitize_planner_bootstrap_goal(resolved_user_prompt)
                planner_bootstrap_args = {"mode": "analyze", "goal": planner_bootstrap_goal}
                planner_bootstrap_execution: dict[str, object]
                try:
                    planner_bootstrap_execution = await self._run_blocking(
                        label="tool.execute.planner_bootstrap",
                        timeout_seconds=self._tool_timeout_seconds,
                        func=self._tool_executor.execute,
                        args=("planner", planner_bootstrap_args),
                        request_id=request_id,
                        method=request.method,
                    )
                except ToolExecutionError as exc:
                    bootstrap_error = (
                        "Plan mode requires unified-planning initialization before drafting. "
                        f"Planner bootstrap failed: {exc}"
                    )
                    await self._ipc_bridge.send_request_error(
                        client=client,
                        request_id=request_id,
                        code=ErrorMessage.INVALID_REQUEST,
                        message=bootstrap_error,
                        require_in_flight=True,
                    )
                    if self._ipc_bridge.is_request_in_flight(request_id):
                        await self._run_blocking(
                            label="db.record_interaction",
                            timeout_seconds=self._db_timeout_seconds,
                            func=self._memory_manager.record_interaction,
                            args=(),
                            kwargs={
                                "session_id": session_id,
                                "memory_mode": memory_mode,
                                "user_prompt": prompt,
                                "assistant_response": bootstrap_error,
                                "model_name": model or self._config.model_name,
                            },
                            request_id=request_id,
                            method=request.method,
                        )
                    return

                if not planner_bootstrap_execution.get("ok", False):
                    bootstrap_error = (
                        "Plan mode requires unified-planning initialization before drafting. "
                        "Planner bootstrap returned non-success status."
                    )
                    await self._ipc_bridge.send_request_error(
                        client=client,
                        request_id=request_id,
                        code=ErrorMessage.INVALID_REQUEST,
                        message=bootstrap_error,
                        require_in_flight=True,
                    )
                    if self._ipc_bridge.is_request_in_flight(request_id):
                        await self._run_blocking(
                            label="db.record_interaction",
                            timeout_seconds=self._db_timeout_seconds,
                            func=self._memory_manager.record_interaction,
                            args=(),
                            kwargs={
                                "session_id": session_id,
                                "memory_mode": memory_mode,
                                "user_prompt": prompt,
                                "assistant_response": bootstrap_error,
                                "model_name": model or self._config.model_name,
                            },
                            request_id=request_id,
                            method=request.method,
                        )
                    return

                unified_planning_context_block = self._pm._build_unified_planning_bootstrap_context(
                    planner_bootstrap_execution
                )
                if unified_planning_context_block:
                    prompt_for_model = f"{prompt_for_model}\n\n{unified_planning_context_block}"
                await _send_mode_status("Planner initialized, preparing model...")

            # Inject model identity into the cached base prompt for this request.
            effective_model = model or self._config.model_name
            system_instruction = inject_model_identity(
                self._base_system_instruction,
                effective_model,
                verbosity=verbosity_level,
                presentation_style=presentation_style,
                deep_think=deep_think,
            )
            # Inject device context so the AI knows which device is connected
            from agent_host.system_prompt import build_device_context_block
            _device_info = self._device_registry.get(client.address)
            _device_context = build_device_context_block(_device_info)
            if _device_context:
                system_instruction = f"{_device_context}\n\n{system_instruction}"

            # Modes Architecture: Route prompts and tool filters through the active handler.
            # Handlers are constructed with all context via constructor DI — no set_context().
            if execution_mode == ExecutionMode.PLAN:
                mode_handler = self._mode_handler_factory(ExecutionMode.PLAN, {
                    "is_followup": plan_mode_is_followup,
                    "requires_unified_planning": plan_mode_requires_unified_planning,
                    "discovery_budget": plan_mode_discovery_budget,
                    "allowed_tools": self._plan_mode_allowed_tools,
                })
            elif execution_mode == ExecutionMode.TEACHER:
                mode_handler = self._mode_handler_factory(ExecutionMode.TEACHER, {
                    "memory_manager": self._memory_manager,
                    "send_status": _send_mode_status,
                    "session_id": session_id,
                })
            else:
                mode_handler = self._mode_handler_factory(ExecutionMode.DIRECT, {})

            # System prompt override
            if plan_mode_auto_execute:
                system_instruction = f"{self._pm_prompts.get_auto_exec_header()}\n\n{system_instruction}"
            else:
                system_instruction = f"{mode_handler.get_system_prompt_addition()}\n\n{system_instruction}"

            active_tools = mode_handler.filter_active_tools(self._tools)

            def _decorate_mode_result(text: str) -> str:
                if execution_mode != ExecutionMode.PLAN:
                    return text
                stripped = text.lstrip()
                if stripped.startswith("PLAN MODE (Planning Only)") or stripped.startswith(
                    "PLAN MODE (Quick Clarification)"
                ):
                    return self._pm_prompts.normalize_plan_mode_banner(text)
                decorated = (
                    "PLAN MODE (Planning Only)\n"
                    "No destructive tools were executed in this response.\n"
                    "If assumptions look wrong, ask to revise and I will replan.\n\n"
                    f"{text}"
                )
                return self._pm_prompts.normalize_plan_mode_banner(decorated)

            parser_instance = ToolCallParser()
            conversation_history: list[types.Content] = [
                types.Content(role="user", parts=[types.Part.from_text(text=prompt_for_model)])
            ]
            active_tool_names = {
                str(tool.get("name", "")).strip()
                for tool in active_tools
                if isinstance(tool, dict) and str(tool.get("name", "")).strip()
            }
            browse_web_available = "browse_web" in active_tool_names
            chain_depth = 0
            final_assistant_response: str | None = None
            last_non_terminal_result: tuple[str, dict[str, object]] | None = None
            browse_web_called_this_turn = False
            live_web_audit_used = False
            # The planner bootstrap at line ~2364 already called `planner`
            # for Plan Mode requests, so mark it as used to avoid false
            # discovery budget enforcement in the tool chain loop.
            plan_mode_planner_used = execution_mode == ExecutionMode.PLAN
            # Tracks whether the model has called `plan_ops` (or `planner`)
            # to actually produce a plan.  Separate from planner_used because
            # the bootstrap pre-satisfies budget but doesn't produce the plan.
            plan_mode_plan_produced = False
            plan_mode_discovery_calls = 0
            plan_mode_alignment_retry_used = False
            plan_mode_post_clarification_retry_used = False
            plan_mode_nudge_used = False

            def _model_timeout_for_turn(*, continuation: bool) -> float:
                return _resolve_model_timeout_seconds(
                    base_timeout_seconds=self._model_timeout_seconds,
                    deep_think=deep_think,
                    execution_mode=execution_mode,
                    is_continuation=continuation,
                    deep_think_multiplier=self._deep_think_model_timeout_multiplier,
                    teacher_multiplier=mode_handler.get_timeout_multiplier(),
                    continuation_multiplier=self._continuation_model_timeout_multiplier,
                    max_timeout_seconds=self._model_timeout_max_seconds,
                )

            while chain_depth < self._max_tool_chain_depth:
                chain_depth += 1

                # Determine once per iteration whether to show tool call
                # cards in the frontend.  In Plan Mode the cards are hidden
                # and the status bar shows phase descriptions instead.
                show_tool_call_card = mode_handler.should_show_tool_call_card()

                if not self._ipc_bridge.is_request_in_flight(request_id):
                    logger.info("Skipping late prompt response for inactive request: %s", request_id)
                    return
                if not self._ipc_bridge.client_is_connected(client):
                    logger.info("Client disconnected mid-chain for request: %s", request_id)
                    return

                logger.info(
                    "Tool chain iteration %s/%s for request %s",
                    chain_depth,
                    self._max_tool_chain_depth,
                    request_id,
                )
                status_msg = mode_handler.get_chain_status_message(chain_depth)
                if status_msg:
                    await _send_mode_status(status_msg)

                if chain_depth == 1:
                    response = await self._run_blocking(
                        label="model.generate_content",
                        timeout_seconds=_model_timeout_for_turn(continuation=False),
                        func=self._gemini_client.send_prompt_with_tools,
                        args=(),
                        kwargs={
                            "prompt": prompt_for_model,
                            "tools": active_tools,
                            "system_instruction": system_instruction,
                            "model": model,
                            "deep_think": deep_think,
                        },
                        request_id=request_id,
                        method=request.method,
                    )
                else:
                    continuation_callable = getattr(self._gemini_client, "send_continuation", None)
                    if not callable(continuation_callable):
                        raise RuntimeError(
                            "Gemini client does not implement required continuation API"
                        )
                    response = await self._run_blocking(
                        label="model.generate_content.continuation",
                        timeout_seconds=_model_timeout_for_turn(continuation=True),
                        func=continuation_callable,
                        args=(),
                        kwargs={
                            "contents": conversation_history,
                            "tools": active_tools,
                            "system_instruction": system_instruction,
                            "model": model,
                            "deep_think": deep_think,
                        },
                        request_id=request_id,
                        method=request.method,
                    )

                if not self._ipc_bridge.is_request_in_flight(request_id):
                    logger.info("Skipping late model response for inactive request: %s", request_id)
                    return

                logger.info(
                    "[MODEL_VERIFICATION] Response received. Requested model: '%s'",
                    model or "default",
                )

                tool_call = parser_instance.parse_response(response)

                if tool_call is None:
                    if response.get("text"):
                        raw_text = str(response["text"])
                        continuation_callable = getattr(self._gemini_client, "send_continuation", None)
                        can_retry_with_continuation = callable(continuation_callable)
                        if (
                            browse_web_available
                            and not browse_web_called_this_turn
                            and not live_web_audit_used
                            and can_retry_with_continuation
                            and chain_depth < self._max_tool_chain_depth
                        ):
                            live_web_audit_used = True
                            conversation_history.append(
                                types.Content(
                                    role="model",
                                    parts=[types.Part.from_text(text=raw_text or "Draft answer prepared.")],
                                )
                            )
                            conversation_history.append(
                                types.Content(
                                    role="user",
                                    parts=[
                                        types.Part.from_text(
                                            text=self._pm._build_live_web_audit_instruction(
                                                root_prompt=resolved_user_prompt,
                                                draft_response=raw_text,
                                            )
                                        )
                                    ],
                                )
                            )
                            await _send_mode_status("Verifying whether live web lookup is needed...")
                            continue
                        text = (
                            sanitize_user_visible_response(raw_text)
                            if looks_like_json_payload(raw_text)
                            else raw_text
                        )
                        if text.startswith(self._pm._FINAL_ANSWER_READY_PREFIX):
                            text = text[len(self._pm._FINAL_ANSWER_READY_PREFIX):].lstrip()
                        if execution_mode == ExecutionMode.PLAN:
                            asks_structured_clarification = self._pm._plan_mode_text_requests_structured_clarification(
                                text
                            )

                            if asks_structured_clarification and plan_mode_clarification_resolved_this_turn:
                                if (
                                    not plan_mode_post_clarification_retry_used
                                    and can_retry_with_continuation
                                ):
                                    plan_mode_post_clarification_retry_used = True
                                    conversation_history.append(
                                        types.Content(
                                            role="model",
                                            parts=[types.Part.from_text(text=raw_text)],
                                        )
                                    )
                                    conversation_history.append(
                                        types.Content(
                                            role="user",
                                            parts=[
                                                types.Part.from_text(
                                                    text=self._pm._build_plan_mode_post_clarification_instruction(
                                                        root_prompt=resolved_user_prompt,
                                                        clarification_context_block=clarification_context_block,
                                                    )
                                                )
                                            ],
                                        )
                                    )
                                    await _send_mode_status(
                                        "Using your clarification answers to finalize the plan..."
                                    )
                                    continue
                                # P3: Post-clarification retry exhausted — prevent
                                # re-entering the followup clarification branch below.
                                asks_structured_clarification = False

                            if asks_structured_clarification:
                                # Reset retry flag so a new clarification round can use it.
                                plan_mode_post_clarification_retry_used = False
                                existing_followup_state = (
                                    self._plan_mode_clarification_states.get(session_id)
                                    or latest_plan_clarification_state
                                )
                                should_continue = (
                                    existing_followup_state is None
                                    or self._pm._should_continue_plan_clarification(
                                        state=existing_followup_state,
                                        max_rounds=self._pm._parse_plan_mode_clarification_max_rounds(),
                                        confidence_target=self._pm._parse_plan_mode_clarification_confidence_target(),
                                    )
                                )
                                if not should_continue:
                                    self._plan_mode_clarification_states.pop(session_id, None)
                                    # P1-A: Redirect to planning instead of sending
                                    # the model's stale clarification text.
                                    conversation_history.append(
                                        types.Content(
                                            role="model",
                                            parts=[types.Part.from_text(text=raw_text)],
                                        )
                                    )
                                    conversation_history.append(
                                        types.Content(
                                            role="user",
                                            parts=[
                                                types.Part.from_text(
                                                    text=self._pm._build_plan_mode_post_clarification_instruction(
                                                        root_prompt=resolved_user_prompt,
                                                        clarification_context_block=clarification_context_block,
                                                    )
                                                )
                                            ],
                                        )
                                    )
                                    await _send_mode_status(
                                        "Clarification complete — building your plan..."
                                    )
                                    continue
                                else:
                                    followup_state = self._pm._prepare_plan_mode_followup_clarification_state(
                                        root_prompt=resolved_user_prompt,
                                        state=existing_followup_state,
                                    )
                                    if followup_state.question_dimensions:
                                        if len(self._plan_mode_clarification_states) > 100:
                                            oldest_key = next(iter(self._plan_mode_clarification_states))
                                            self._plan_mode_clarification_states.pop(oldest_key, None)
                                        self._plan_mode_clarification_states[session_id] = followup_state
                                        followup_score = self._pm._compute_plan_mode_clarification_score(
                                            prompt=followup_state.root_prompt,
                                            missing_dimensions=self._pm._plan_mode_missing_clarification_dimensions(
                                                followup_state.root_prompt
                                            ),
                                            asked_rounds=followup_state.asked_rounds,
                                        )
                                        text = self._pm._build_plan_mode_clarification_turn_response(
                                            state=followup_state,
                                            session_learning=session_learning_for_ranking,
                                            global_learning=global_learning_for_ranking,
                                            score=followup_score,
                                        )
                                    else:
                                        self._plan_mode_clarification_states.pop(session_id, None)
                                        # P1-B: No more dimensions — redirect to
                                        # planning instead of sending clarification text.
                                        conversation_history.append(
                                            types.Content(
                                                role="model",
                                                parts=[types.Part.from_text(text=raw_text)],
                                            )
                                        )
                                        conversation_history.append(
                                            types.Content(
                                                role="user",
                                                parts=[
                                                    types.Part.from_text(
                                                        text=self._pm._build_plan_mode_post_clarification_instruction(
                                                            root_prompt=resolved_user_prompt,
                                                            clarification_context_block=clarification_context_block,
                                                        )
                                                    )
                                                ],
                                            )
                                        )
                                        await _send_mode_status(
                                            "Clarification complete — building your plan..."
                                        )
                                        continue
                            else:
                                alignment_score = self._pm._compute_plan_mode_alignment_score(
                                    root_prompt=resolved_user_prompt,
                                    response_text=text,
                                    clarification_context_block=clarification_context_block,
                                )
                                alignment_threshold = self._pm._dynamic_plan_mode_alignment_threshold(
                                    resolved_user_prompt
                                )
                                if (
                                    alignment_score < alignment_threshold
                                    and not plan_mode_alignment_retry_used
                                    and can_retry_with_continuation
                                ):
                                    plan_mode_alignment_retry_used = True
                                    conversation_history.append(
                                        types.Content(
                                            role="model",
                                            parts=[types.Part.from_text(text=raw_text)],
                                        )
                                    )
                                    conversation_history.append(
                                        types.Content(
                                            role="user",
                                            parts=[
                                                types.Part.from_text(
                                                    text=self._pm._build_plan_mode_alignment_repair_instruction(
                                                        root_prompt=resolved_user_prompt,
                                                        clarification_context_block=clarification_context_block,
                                                    )
                                                )
                                            ],
                                        )
                                    )
                                    await _send_mode_status(
                                        "Refining plan alignment to your request..."
                                    )
                                    continue
                        text = _decorate_mode_result(text)
                        await mode_handler.post_generation_hook(response_text=text)
                        await _send_mode_status("Drafting response...")
                        if self._ipc_bridge.is_request_in_flight(request_id) and self._ipc_bridge.client_is_connected(client):
                            streamer = self._server.create_streaming_handler(client, request_id)
                            await streamer.stream_words(text)
                        result_tool_calls: list[dict[str, object]] | None = None
                        if last_non_terminal_result is not None:
                            _, prior_tool_call_payload = last_non_terminal_result
                            if prior_tool_call_payload:
                                result_tool_calls = [prior_tool_call_payload]
                        await self._ipc_bridge.send_request_message(
                            client=client,
                            request_id=request_id,
                            payload=ResultMessage.create(
                                request_id,
                                text,
                                result_tool_calls,
                            ).to_bytes(),
                            require_in_flight=True,
                        )
                        final_assistant_response = text
                    else:
                        # Plan Mode planner nudge: if the model returned no actionable
                        # output without having produced a plan, re-prompt it to call
                        # plan_ops.  Uses plan_mode_plan_produced (not planner_used)
                        # because the bootstrap pre-satisfies planner_used for budget
                        # enforcement but doesn't produce the actual plan.
                        continuation_callable = getattr(self._gemini_client, "send_continuation", None)
                        can_retry_with_continuation = callable(continuation_callable)
                        if (
                            execution_mode == ExecutionMode.PLAN
                            and not plan_mode_plan_produced
                            and not plan_mode_nudge_used
                            and can_retry_with_continuation
                            and chain_depth < self._max_tool_chain_depth
                        ):
                            plan_mode_nudge_used = True
                            # Insert a minimal model turn so the Gemini API sees
                            # proper user/model alternation in the history.
                            conversation_history.append(
                                types.Content(
                                    role="model",
                                    parts=[
                                        types.Part.from_text(
                                            text="I have the planning context. Let me build the plan now."
                                        )
                                    ],
                                )
                            )
                            nudge_text = (
                                "You MUST now call the `plan_ops` tool to produce a structured, "
                                "phased execution plan. The planner context is already loaded. "
                                "Do not return text — call `plan_ops` with your plan now."
                            ) if last_non_terminal_result is None else (
                                "You gathered discovery information but returned no plan. "
                                "You MUST now call the `plan_ops` tool to produce a structured, "
                                "phased execution plan based on the discovery results above. "
                                "Do not call more discovery tools. Produce the plan now."
                            )
                            conversation_history.append(
                                types.Content(
                                    role="user",
                                    parts=[types.Part.from_text(text=nudge_text)],
                                )
                            )
                            await _send_mode_status("Assembling plan from discovery results...")
                            continue
                        if execution_mode == ExecutionMode.PLAN:
                            fallback_text = (
                                "I analyzed your request but couldn't produce a structured plan. "
                                "This can happen when the planning engine needs more specific guidance. "
                                "Try rephrasing with: what you want organized, a timeline, and any constraints."
                            )
                        elif execution_mode == ExecutionMode.TEACHER:
                            failure_text = (
                                "Teacher mode could not produce a valid teaching response in this turn."
                            )
                            await self._ipc_bridge.send_request_error(
                                client=client,
                                request_id=request_id,
                                code=ErrorMessage.INTERNAL_ERROR,
                                message=failure_text,
                                require_in_flight=True,
                            )
                            if self._ipc_bridge.is_request_in_flight(request_id):
                                await self._run_blocking(
                                    label="db.record_interaction",
                                    timeout_seconds=self._db_timeout_seconds,
                                    func=self._memory_manager.record_interaction,
                                    args=(),
                                    kwargs={
                                        "session_id": session_id,
                                        "memory_mode": memory_mode,
                                        "user_prompt": prompt,
                                        "assistant_response": failure_text,
                                        "model_name": model or self._config.model_name,
                                    },
                                    request_id=request_id,
                                    method=request.method,
                                )
                            return
                        else:
                            fallback_text = (
                                "I wasn't able to generate a response for that request. This might happen if "
                                "the question is outside my capabilities (like weather forecasts or web "
                                "searches). Feel free to ask me about file management or other tasks I can "
                                "help with on your Mac!"
                            )
                        fallback_text = _decorate_mode_result(fallback_text)
                        await mode_handler.post_generation_hook(response_text=fallback_text)
                        await _send_mode_status("Drafting response...")
                        if self._ipc_bridge.is_request_in_flight(request_id) and self._ipc_bridge.client_is_connected(client):
                            streamer = self._server.create_streaming_handler(client, request_id)
                            await streamer.stream_words(fallback_text)
                        await self._ipc_bridge.send_request_message(
                            client=client,
                            request_id=request_id,
                            payload=ResultMessage.create(request_id, fallback_text).to_bytes(),
                            require_in_flight=True,
                        )
                        final_assistant_response = fallback_text
                    break

                if execution_mode == ExecutionMode.PLAN and tool_call.name not in self._plan_mode_allowed_tools:
                    allowed_tool_list = ", ".join(sorted(self._plan_mode_allowed_tools))
                    rejection = (
                        "Plan mode is planning-only. This tool is disabled in plan mode: "
                        f"`{tool_call.name}`. Allowed tools: {allowed_tool_list}. "
                        "Switch to Direct mode to execute operations."
                    )
                    if show_tool_call_card:
                        await self._ipc_bridge.send_request_message(
                            client=client,
                            request_id=request_id,
                            payload=ToolCallNotification.failed(
                                request_id,
                                tool_call.name,
                                tool_call.arguments,
                                rejection,
                            ).to_bytes(),
                            require_in_flight=True,
                        )
                    await self._ipc_bridge.send_request_error(
                        client=client,
                        request_id=request_id,
                        code=ErrorMessage.INVALID_REQUEST,
                        message=rejection,
                        require_in_flight=True,
                    )
                    if self._ipc_bridge.is_request_in_flight(request_id):
                        await self._run_blocking(
                            label="db.record_interaction",
                            timeout_seconds=self._db_timeout_seconds,
                            func=self._memory_manager.record_interaction,
                            args=(),
                            kwargs={
                                "session_id": session_id,
                                "memory_mode": memory_mode,
                                "user_prompt": prompt,
                                "assistant_response": rejection,
                                "model_name": model or self._config.model_name,
                            },
                            request_id=request_id,
                            method=request.method,
                        )
                    return

                if tool_call.name == "browse_web":
                    browse_web_called_this_turn = True

                if execution_mode == ExecutionMode.PLAN and tool_call.name in self._pm._PLAN_MODE_PLANNER_TOOLS:
                    plan_mode_planner_used = True
                    # Only mark plan as produced for plan_ops or planner
                    # in create/replan mode (analyze mode is advisory only).
                    if tool_call.name == "plan_ops" or (
                        tool_call.name == "planner"
                        and tool_call.arguments.get("mode") in ("create", "replan")
                    ):
                        plan_mode_plan_produced = True
                        self._plan_mode_sessions_with_plan[session_id] = time.time()
                    if len(self._plan_mode_sessions_with_plan) > 100:
                        _evict_sp = list(self._plan_mode_sessions_with_plan)[:20]
                        for _ek_sp in _evict_sp:
                            self._plan_mode_sessions_with_plan.pop(_ek_sp, None)
                elif (
                    execution_mode == ExecutionMode.PLAN
                    and plan_mode_requires_unified_planning
                    and not plan_mode_planner_used
                    and tool_call.name in self._pm._PLAN_MODE_DISCOVERY_TOOLS
                ):
                    plan_mode_discovery_calls += 1
                    if plan_mode_discovery_calls > plan_mode_discovery_budget:
                        rejection = (
                            "Plan mode requires unified planning for actionable file operations. "
                            "Call `planner` or `plan_ops` now before additional discovery tools. "
                            f"Discovery budget before planning: {plan_mode_discovery_budget}."
                        )
                        if show_tool_call_card:
                            await self._ipc_bridge.send_request_message(
                                client=client,
                                request_id=request_id,
                                payload=ToolCallNotification.failed(
                                    request_id,
                                    tool_call.name,
                                    tool_call.arguments,
                                    rejection,
                                ).to_bytes(),
                                require_in_flight=True,
                            )
                        await self._ipc_bridge.send_request_error(
                            client=client,
                            request_id=request_id,
                            code=ErrorMessage.INVALID_REQUEST,
                            message=rejection,
                            require_in_flight=True,
                        )
                        if self._ipc_bridge.is_request_in_flight(request_id):
                            await self._run_blocking(
                                label="db.record_interaction",
                                timeout_seconds=self._db_timeout_seconds,
                                func=self._memory_manager.record_interaction,
                                args=(),
                                kwargs={
                                    "session_id": session_id,
                                    "memory_mode": memory_mode,
                                    "user_prompt": prompt,
                                    "assistant_response": rejection,
                                    "model_name": model or self._config.model_name,
                                },
                                request_id=request_id,
                                method=request.method,
                            )
                        return

                if show_tool_call_card:
                    await self._ipc_bridge.send_request_message(
                        client=client,
                        request_id=request_id,
                        payload=StatusUpdate.calling_tool(request_id, tool_call.name).to_bytes(),
                        require_in_flight=True,
                    )
                else:
                    # Plan Mode: tool cards are hidden, so send a user-friendly
                    # phase description so the status bar stays dynamic.
                    _tool_phase_labels = {
                        "search_files": "Scanning your files...",
                        "read_document": "Reading document contents...",
                        "planner": "Initializing the planner...",
                        "plan_ops": "Building the execution plan...",
                        "apply_ops": "Executing the plan...",
                        "read_screen": "Reading screen contents...",
                        "manage_notes": "Managing your notes...",
                        "generate_image": "Generating an image...",
                        "browse_web": "Fetching live web sources...",
                    }
                    _phase = _tool_phase_labels.get(
                        tool_call.name,
                        f"Running {tool_call.name}...",
                    )
                    await _send_mode_status(_phase)

                try:
                    self._validator.validate_tool_call(tool_call.name, tool_call.arguments)
                except (SchemaNotFoundError, ValidationFailedError) as e:
                    validation_error_text = f"Tool call validation failed: {e}"
                    logger.warning(
                        "Schema validation error for %s (request %s): %s",
                        tool_call.name,
                        request_id,
                        e,
                    )
                    if show_tool_call_card:
                        await self._ipc_bridge.send_request_message(
                            client=client,
                            request_id=request_id,
                            payload=ToolCallNotification.failed(
                                request_id,
                                tool_call.name,
                                tool_call.arguments,
                                str(e),
                            ).to_bytes(),
                            require_in_flight=True,
                        )
                    # Feed the validation error back to the model as a
                    # function response so it can self-correct, rather than
                    # terminating the request outright.
                    validation_model_content = types.Content(
                        role="model",
                        parts=[
                            types.Part.from_function_call(
                                name=tool_call.name,
                                args=tool_call.arguments,
                            )
                        ],
                    )
                    conversation_history.append(validation_model_content)
                    conversation_history.append(
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_function_response(
                                    name=tool_call.name,
                                    response={
                                        "ok": False,
                                        "output": {"error": validation_error_text},
                                    },
                                )
                            ],
                        )
                    )
                    last_non_terminal_result = (
                        f"I couldn't complete `{tool_call.name}`.\n\n"
                        f"- Error: {validation_error_text}\n"
                        "- Suggested fix: review the input arguments and retry.",
                        {},
                    )
                    continue

                raw_response = response.get("raw_response")
                model_content: types.Content | None = None
                if raw_response is not None and hasattr(raw_response, "candidates"):
                    candidates = getattr(raw_response, "candidates", None)
                    if candidates:
                        candidate_content = getattr(candidates[0], "content", None)
                        if isinstance(candidate_content, types.Content):
                            model_content = candidate_content
                if model_content is None:
                    model_content = types.Content(
                        role="model",
                        parts=[
                            types.Part.from_function_call(
                                name=tool_call.name,
                                args=tool_call.arguments,
                            )
                        ],
                    )

                if tool_call.name in self._destructive_tool_names:
                    confirmation_future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
                    self._pending_tool_confirmations[request_id] = (client.address, confirmation_future)
                    await self._ipc_bridge.send_request_message(
                        client=client,
                        request_id=request_id,
                        payload=StatusUpdate.awaiting_approval(
                            request_id,
                            f"Awaiting approval for {tool_call.name}",
                        ).to_bytes(),
                        require_in_flight=True,
                    )
                    if show_tool_call_card:
                        await self._ipc_bridge.send_request_message(
                            client=client,
                            request_id=request_id,
                            payload=ToolCallNotification.create(
                                request_id,
                                tool_call.name,
                                tool_call.arguments,
                                status=ToolCallStatus.PENDING,
                                result="Awaiting confirmation for destructive operation",
                            ).to_bytes(),
                            require_in_flight=True,
                        )
                    try:
                        approved = await asyncio.wait_for(
                            confirmation_future,
                            timeout=self._confirmation_timeout_seconds,
                        )
                    except asyncio.TimeoutError:
                        timeout_text = "Tool execution confirmation timed out"
                        if show_tool_call_card:
                            await self._ipc_bridge.send_request_message(
                                client=client,
                                request_id=request_id,
                                payload=ToolCallNotification.failed(
                                    request_id,
                                    tool_call.name,
                                    tool_call.arguments,
                                    "Confirmation timed out",
                                ).to_bytes(),
                                require_in_flight=True,
                            )
                        await self._ipc_bridge.send_request_error(
                            client=client,
                            request_id=request_id,
                            code=ErrorMessage.INVALID_REQUEST,
                            message=timeout_text,
                            require_in_flight=True,
                        )
                        if self._ipc_bridge.is_request_in_flight(request_id):
                            await self._run_blocking(
                                label="db.record_interaction",
                                timeout_seconds=self._db_timeout_seconds,
                                func=self._memory_manager.record_interaction,
                                args=(),
                                kwargs={
                                    "session_id": session_id,
                                    "memory_mode": memory_mode,
                                    "user_prompt": prompt,
                                    "assistant_response": timeout_text,
                                    "model_name": model or self._config.model_name,
                                },
                                request_id=request_id,
                                method=request.method,
                            )
                        return
                    finally:
                        self._pending_tool_confirmations.pop(request_id, None)

                    if not approved:
                        denied_text = "Tool execution denied by user"
                        if show_tool_call_card:
                            await self._ipc_bridge.send_request_message(
                                client=client,
                                request_id=request_id,
                                payload=ToolCallNotification.failed(
                                    request_id,
                                    tool_call.name,
                                    tool_call.arguments,
                                    denied_text,
                                ).to_bytes(),
                                require_in_flight=True,
                            )
                        await self._ipc_bridge.send_request_error(
                            client=client,
                            request_id=request_id,
                            code=ErrorMessage.INVALID_REQUEST,
                            message=denied_text,
                            require_in_flight=True,
                        )
                        if self._ipc_bridge.is_request_in_flight(request_id):
                            await self._run_blocking(
                                label="db.record_interaction",
                                timeout_seconds=self._db_timeout_seconds,
                                func=self._memory_manager.record_interaction,
                                args=(),
                                kwargs={
                                    "session_id": session_id,
                                    "memory_mode": memory_mode,
                                    "user_prompt": prompt,
                                    "assistant_response": denied_text,
                                    "model_name": model or self._config.model_name,
                                },
                                request_id=request_id,
                                method=request.method,
                            )
                        return

                # ── read_screen: delegate to frontend via IPC ──
                if tool_call.name == "read_screen":
                    async def _screen_send_status(rid: str) -> None:
                        await self._ipc_bridge.send_request_message(
                            client=client,
                            request_id=rid,
                            payload=StatusUpdate.capturing_screen(rid).to_bytes(),
                            require_in_flight=True,
                        )

                    async def _screen_send_capture_request(rid: str) -> None:
                        await self._ipc_bridge.send_request_message(
                            client=client,
                            request_id=rid,
                            payload=SystemMessage.lifecycle_event(
                                rid,
                                domain="device",
                                action="screen_capture_requested",
                                payload={"request_id": rid},
                            ).to_bytes(),
                            require_in_flight=True,
                        )

                    _screen_ctx = ScreenToolContext(
                        request_id=request_id,
                        client_address=client.address,
                        pending_screen_captures=self._pending_screen_captures,
                        send_status=_screen_send_status,
                        send_capture_request=_screen_send_capture_request,
                        client_capabilities=self._client_capabilities_for,
                        resolved_user_prompt=resolved_user_prompt,
                        read_screen_ocr_max_chars=self._read_screen_ocr_max_chars,
                        read_screen_ocr_max_lines=self._read_screen_ocr_max_lines,
                    )
                    _screen_plugin = self._async_plugins.get("read_screen")
                    if _screen_plugin is None:
                        raise RuntimeError("No async plugin for tool: read_screen")
                    _screen_result, screen_image_bytes = await _screen_plugin.execute(
                        tool_call.arguments, ctx=_screen_ctx,
                    )
                    from agent_host.contracts.types.result import Failure as _SF
                    if isinstance(_screen_result, _SF):
                        execution = {
                            "ok": False,
                            "output": _screen_result.error.message
                            if hasattr(_screen_result.error, "message")
                            else str(_screen_result.error),
                        }
                    else:
                        execution = _screen_result.value

                    # Build function response + optional image part
                    conversation_history.append(model_content)
                    _fn_response = types.Part.from_function_response(
                        name=tool_call.name,
                        response={
                            "ok": bool(execution.get("ok")),
                            "output": execution.get("output"),
                        },
                    )
                    _parts: list[types.Part] = [_fn_response]
                    if screen_image_bytes:
                        _parts.append(
                            types.Part.from_bytes(
                                data=screen_image_bytes,
                                mime_type="image/jpeg",
                            )
                        )
                    conversation_history.append(
                        types.Content(role="user", parts=_parts)
                    )

                    # Send tool card to frontend
                    if show_tool_call_card:
                        _card_status = (
                            ToolCallStatus.SUCCESS
                            if execution.get("ok")
                            else ToolCallStatus.FAILED
                        )
                        _result_preview = str(
                            execution.get("output", "")
                        )[:200]
                        await self._ipc_bridge.send_request_message(
                            client=client,
                            request_id=request_id,
                            payload=ToolCallNotification.create(
                                request_id,
                                tool_call.name,
                                tool_call.arguments,
                                status=_card_status,
                                result=_result_preview,
                            ).to_bytes(),
                            require_in_flight=True,
                        )

                    last_non_terminal_result = (
                        str(execution.get("output", "")),
                        {
                            "name": tool_call.name,
                            "arguments": tool_call.arguments,
                            "status": "success" if execution.get("ok") else "failed",
                            "result": str(execution.get("output", ""))[:200],
                        },
                    )
                    continue

                # ── note tools (dispatched via registry) ──
                if tool_call.name in NOTE_TOOL_NAMES:
                    note_execution: dict[str, object]
                    try:
                        if tool_call.name == "generate_image":
                            _note_ctx: NoteToolContext = ImageToolContext(
                                session_id=session_id,
                                memory_manager=self._memory_manager,
                                db_timeout_seconds=self._db_timeout_seconds,
                                request_id=request_id,
                                method=request.method,
                                execution_mode=execution_mode,
                                resolved_user_prompt=resolved_user_prompt,
                                run_blocking=self._run_blocking,
                                resolve_note_id=self._resolve_note_id,
                                gemini_client=self._gemini_client,
                                image_output_root=self._image_output_root,
                                image_timeout_seconds=self._image_timeout_seconds,
                                image_model_override=self._image_model_override,
                                config_allowed_roots=list(self._config.allowed_roots),
                            )
                        else:
                            _note_ctx = NoteToolContext(
                                session_id=session_id,
                                memory_manager=self._memory_manager,
                                db_timeout_seconds=self._db_timeout_seconds,
                                request_id=request_id,
                                method=request.method,
                                execution_mode=execution_mode,
                                resolved_user_prompt=resolved_user_prompt,
                                run_blocking=self._run_blocking,
                                resolve_note_id=self._resolve_note_id,
                            )
                        _note_plugin = self._async_plugins.get(tool_call.name)
                        if _note_plugin is None:
                            raise RuntimeError(f"No async plugin for tool: {tool_call.name}")
                        _note_result = await _note_plugin.execute(
                            tool_call.arguments, ctx=_note_ctx,
                        )
                        from agent_host.contracts.types.result import Failure as _NF
                        if isinstance(_note_result, _NF):
                            note_execution = {
                                "ok": False,
                                "output": _note_result.error.message
                                if hasattr(_note_result.error, "message")
                                else str(_note_result.error),
                            }
                        else:
                            note_execution = _note_result.value
                    except TimeoutError as te:
                        logger.warning("Note tool %s timed out: %s", tool_call.name, te)
                        note_execution = {
                            "ok": False,
                            "output": (
                                f"Note operation timed out ({tool_call.name}): {te}. "
                                "The database may be busy — try again."
                            ),
                        }
                    except Exception as exc:
                        logger.warning("Note tool %s failed: %s", tool_call.name, exc)
                        note_execution = {
                            "ok": False,
                            "output": f"Note operation failed: {exc}",
                        }
                    if (
                        execution_mode == ExecutionMode.TEACHER
                        and bool(note_execution.get("ok"))
                        and tool_call.name in self._teacher_completion_tools
                    ):
                        try:
                            if mode_handler.name == "teacher":
                                mode_handler.record_tool_call(tool_call.name)
                        except Exception as e:
                            logger.error(f"Failed to record manual teacher note completion: {e}")

                    # Feed result back into conversation
                    conversation_history.append(model_content)
                    conversation_history.append(
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_function_response(
                                    name=tool_call.name,
                                    response={
                                        "ok": bool(note_execution.get("ok")),
                                        "output": note_execution.get("output"),
                                    },
                                )
                            ],
                        )
                    )

                    # Send tool card to frontend
                    if show_tool_call_card:
                        _note_card_status = (
                            ToolCallStatus.SUCCESS
                            if note_execution.get("ok")
                            else ToolCallStatus.FAILED
                        )
                        await self._ipc_bridge.send_request_message(
                            client=client,
                            request_id=request_id,
                            payload=ToolCallNotification.create(
                                request_id,
                                tool_call.name,
                                tool_call.arguments,
                                status=_note_card_status,
                                result=str(note_execution.get("output", ""))[:200],
                            ).to_bytes(),
                            require_in_flight=True,
                        )

                    last_non_terminal_result = (
                        str(note_execution.get("output", "")),
                        {
                            "name": tool_call.name,
                            "arguments": tool_call.arguments,
                            "status": "success" if note_execution.get("ok") else "failed",
                            "result": str(note_execution.get("output", ""))[:200],
                        },
                    )
                    continue

                if tool_call.name == "apply_ops":
                    await self._ipc_bridge.send_request_message(
                        client=client,
                        request_id=request_id,
                        payload=StatusUpdate.executing_plan(
                            request_id,
                            f"Executing plan: {tool_call.arguments.get('plan_id', '')}",
                        ).to_bytes(),
                        require_in_flight=True,
                    )

                if show_tool_call_card:
                    await self._ipc_bridge.send_request_message(
                        client=client,
                        request_id=request_id,
                        payload=ToolCallNotification.executing(
                            request_id,
                            tool_call.name,
                            tool_call.arguments,
                        ).to_bytes(),
                        require_in_flight=True,
                    )

                # execution: dict[str, object]  <-- reused variable
                execution_content: str
                execution_summary: str
                plan_mode_result_override: str | None = None
                try:
                    # Device-aware routing: proxy to mobile or execute locally
                    from agent_host.ipc.device_tool_router import DeviceToolRouter as _DTR
                    _device_info = self._device_registry.get(client.address)
                    _is_mobile_client = (
                        isinstance(_device_info, dict)
                        and _device_info.get("platform", "").lower() in {"ios", "ipados"}
                    )
                    _device_supported = set(
                        _device_info.get("supported_tools", [])
                        if isinstance(_device_info, dict) else []
                    )

                    if _is_mobile_client and tool_call.name in _device_supported:
                        # Proxy tool to iOS device
                        _proxy_key = f"{request_id}:{tool_call.name}:{time.monotonic_ns()}"
                        _proxy_future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
                        self._pending_tool_proxies[_proxy_key] = (client.address, _proxy_future)

                        await self._ipc_bridge.send_request_message(
                            client=client,
                            request_id=request_id,
                            payload=SystemMessage.lifecycle_event(
                                request_id,
                                domain="device",
                                action="tool_execute_request",
                                payload={
                                    "proxy_key": _proxy_key,
                                    "tool_name": tool_call.name,
                                    "arguments": dict(tool_call.arguments) if tool_call.arguments else {},
                                },
                            ).to_bytes(),
                            require_in_flight=True,
                        )

                        try:
                            execution = await asyncio.wait_for(_proxy_future, timeout=30.0)
                        except asyncio.TimeoutError:
                            self._pending_tool_proxies.pop(_proxy_key, None)
                            execution = {
                                "tool": tool_call.name,
                                "ok": False,
                                "output": {"error": "Device tool execution timed out after 30s", "status": "failed"},
                            }
                    else:
                        # Local execution on Mac backend
                        execution = await self._run_blocking(
                            label="tool.execute",
                            timeout_seconds=self._tool_timeout_seconds,
                            func=self._tool_executor.execute,
                            args=(tool_call.name, tool_call.arguments),
                            request_id=request_id,
                            method=request.method,
                        )
                    if not self._ipc_bridge.is_request_in_flight(request_id):
                        logger.info(
                            "Skipping late tool execution response for inactive request: %s",
                            request_id,
                        )
                        return
                except ToolExecutionError as e:
                    error_text = str(e)
                    execution = {
                        "tool": tool_call.name,
                        "ok": False,
                        "output": {"error": error_text},
                        "error": error_text,
                    }
                    execution_content = (
                        f"I couldn't complete `{tool_call.name}`.\n\n"
                        f"- Error: {error_text}\n"
                        "- Suggested fix: review the input arguments and retry."
                    )
                    execution_summary = error_text or "execution failed"
                    if show_tool_call_card:
                        await self._ipc_bridge.send_request_message(
                            client=client,
                            request_id=request_id,
                            payload=ToolCallNotification.failed(
                                request_id,
                                tool_call.name,
                                tool_call.arguments,
                                execution_summary,
                            ).to_bytes(),
                            require_in_flight=True,
                        )
                else:
                    execution_content, execution_summary = _format_tool_execution_output(
                        tool_call.name,
                        execution,
                    )
                    if (
                        execution_mode == ExecutionMode.PLAN
                        and tool_call.name == "plan_ops"
                        and execution.get("ok")
                    ):
                        planned_id = ""
                        output_payload = execution.get("output", {})
                        if isinstance(output_payload, dict):
                            planned_id_raw = output_payload.get("plan_id")
                            if isinstance(planned_id_raw, str) and planned_id_raw.strip():
                                planned_id = planned_id_raw.strip()
                                await self._ipc_bridge.send_request_message(
                                    client=client,
                                    request_id=request_id,
                                    payload=StatusUpdate.plan_ready(
                                        request_id,
                                        f"Plan ready: {planned_id}",
                                    ).to_bytes(),
                                    require_in_flight=True,
                                )
                        if not planned_id:
                            planned_id = "unknown-plan-id"
                        plan_mode_result_override = (
                            f"{execution_content}\n\n"
                            "Plan mode is ON: no filesystem changes were executed.\n"
                            "To execute this plan, switch to Direct mode and ask to apply "
                            f"`plan_id={planned_id}`."
                        )
                    if execution.get("ok"):
                        if show_tool_call_card:
                            await self._ipc_bridge.send_request_message(
                                client=client,
                                request_id=request_id,
                                payload=ToolCallNotification.success(
                                    request_id,
                                    tool_call.name,
                                    tool_call.arguments,
                                    execution_summary,
                                ).to_bytes(),
                                require_in_flight=True,
                            )
                    else:
                        failure_reason = execution_summary or "execution failed"
                        if show_tool_call_card:
                            await self._ipc_bridge.send_request_message(
                                client=client,
                                request_id=request_id,
                                payload=ToolCallNotification.failed(
                                    request_id,
                                    tool_call.name,
                                    tool_call.arguments,
                                    failure_reason,
                                ).to_bytes(),
                                require_in_flight=True,
                            )

                tool_call_payload: dict[str, object] = (
                    {
                        "name": tool_call.name,
                        "arguments": tool_call.arguments,
                    }
                    if show_tool_call_card
                    else {}
                )
                if plan_mode_result_override is not None:
                    await mode_handler.post_generation_hook(response_text=plan_mode_result_override)
                    await self._ipc_bridge.send_request_message(
                        client=client,
                        request_id=request_id,
                        payload=ResultMessage.create(
                            request_id,
                            plan_mode_result_override,
                            [tool_call_payload] if tool_call_payload else None,
                        ).to_bytes(),
                        require_in_flight=True,
                    )
                    final_assistant_response = plan_mode_result_override
                    break
                if tool_call.name in self._destructive_tool_names:
                    await mode_handler.post_generation_hook(response_text=execution_content)
                    await self._ipc_bridge.send_request_message(
                        client=client,
                        request_id=request_id,
                        payload=ResultMessage.create(
                            request_id,
                            execution_content,
                            [tool_call_payload] if tool_call_payload else None,
                        ).to_bytes(),
                        require_in_flight=True,
                    )
                    final_assistant_response = execution_content
                    break

                last_non_terminal_result = (execution_content, tool_call_payload)
                conversation_history.append(model_content)

                # Sanitize the function response for Gemini API compatibility
                _fn_output = execution.get("output")
                if isinstance(_fn_output, dict):
                    # Deep-convert to ensure JSON-primitives only
                    import json as _json
                    try:
                        _serialized = _json.dumps(_fn_output, default=str)
                        _fn_output = _json.loads(_serialized)
                        _sz = len(_serialized)
                        if _sz > 5000:
                            logger.info("Function response payload: %d bytes for %s", _sz, tool_call.name)
                    except Exception as _ser_err:
                        logger.warning("Function response serialization failed: %s", _ser_err)
                        _fn_output = {"status": "success", "note": "Results available but could not be serialized"}

                function_response = types.Part.from_function_response(
                    name=tool_call.name,
                    response={
                        "ok": bool(execution.get("ok")),
                        "output": _fn_output,
                    },
                )
                conversation_history.append(
                    types.Content(role="user", parts=[function_response])
                )

            if final_assistant_response is None:
                if last_non_terminal_result is not None:
                    final_assistant_response, tool_call_payload = last_non_terminal_result
                    if chain_depth >= self._max_tool_chain_depth:
                        final_assistant_response = (
                            f"{final_assistant_response}\n\n"
                            f"Stopped after reaching tool-chain depth limit "
                            f"({self._max_tool_chain_depth}) before a final model answer."
                        )
                    final_assistant_response = _decorate_mode_result(final_assistant_response)
                    await mode_handler.post_generation_hook(response_text=final_assistant_response)
                    await self._ipc_bridge.send_request_message(
                        client=client,
                        request_id=request_id,
                        payload=ResultMessage.create(
                            request_id,
                            final_assistant_response,
                            [tool_call_payload] if tool_call_payload else None,
                        ).to_bytes(),
                        require_in_flight=True,
                    )
                elif chain_depth >= self._max_tool_chain_depth:
                    final_assistant_response = (
                        f"I reached the maximum tool-chain depth ({self._max_tool_chain_depth}) "
                        "before producing a final response."
                    )
                    final_assistant_response = _decorate_mode_result(final_assistant_response)
                    await mode_handler.post_generation_hook(response_text=final_assistant_response)
                    await self._ipc_bridge.send_request_message(
                        client=client,
                        request_id=request_id,
                        payload=ResultMessage.create(request_id, final_assistant_response).to_bytes(),
                        require_in_flight=True,
                    )

            if final_assistant_response is not None and self._ipc_bridge.is_request_in_flight(request_id):
                await self._run_blocking(
                    label="db.record_interaction",
                    timeout_seconds=self._db_timeout_seconds,
                    func=self._memory_manager.record_interaction,
                    args=(),
                    kwargs={
                        "session_id": session_id,
                        "memory_mode": memory_mode,
                        "user_prompt": prompt,
                        "assistant_response": final_assistant_response,
                        "model_name": model or self._config.model_name,
                    },
                    request_id=request_id,
                    method=request.method,
                )
                updated_session = await self._run_blocking(
                    label="db.get_session",
                    timeout_seconds=self._db_timeout_seconds,
                    func=self._memory_manager.get_session,
                    args=(session_id,),
                    request_id=request_id,
                    method=request.method,
                )
                if updated_session is not None:
                    await self._ipc_bridge.broadcast_session_event(
                        action="activity",
                        session=self._ipc_bridge.session_payload(updated_session),
                    )

            # Send complete status
            await self._ipc_bridge.send_request_message(
                client=client,
                request_id=request_id,
                payload=StatusUpdate.complete(request_id).to_bytes(),
                require_in_flight=True,
            )

        except asyncio.CancelledError:
            logger.info(f"Prompt request cancelled: {request_id}")
            await self._ipc_bridge.send_request_error(
                client=client,
                request_id=request_id,
                code=-32800,
                message="Request cancelled by user",
            )
            raise
        except self._RequestTimeoutError as e:
            timeout_data = dict(getattr(e, "error_data", {}) or {})
            timeout_message = str(timeout_data.get("user_message", "")).strip() or _format_exception_message(
                e,
                fallback="Request timed out",
            )
            await self._ipc_bridge.send_request_error(
                client=client,
                request_id=request_id,
                code=ErrorMessage.REQUEST_TIMEOUT,
                message=timeout_message,
                data=timeout_data or None,
                require_in_flight=True,
            )
        except GeminiRateLimitError as e:
            await self._ipc_bridge.send_request_error(
                client=client,
                request_id=request_id,
                code=-32000,
                message=f"Rate limit: {_format_exception_message(e, fallback='Rate limit exceeded')}",
                require_in_flight=True,
            )
        except GeminiAPIError as e:
            await self._ipc_bridge.send_request_error(
                client=client,
                request_id=request_id,
                code=-32001,
                message=f"API error: {_format_exception_message(e, fallback='Gemini API request failed')}",
                require_in_flight=True,
            )
        except MalformedResponseError as e:
            await self._ipc_bridge.send_request_error(
                client=client,
                request_id=request_id,
                code=-32002,
                message=f"Parse error: {_format_exception_message(e, fallback='Malformed Gemini response')}",
                require_in_flight=True,
            )
        except Exception as e:
            logger.exception(f"Error handling prompt: {e}")
            message = _format_exception_message(e)
            await self._ipc_bridge.send_request_error(
                client=client,
                request_id=request_id,
                code=ErrorMessage.INTERNAL_ERROR,
                message=message,
                require_in_flight=True,
            )
        finally:
            reset_request_context(context_tokens)
