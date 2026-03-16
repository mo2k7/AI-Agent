#!/usr/bin/env python3
"""CLI entrypoint for the Personal macOS AI Agent.

This module provides the command-line interface for interacting with
the AI agent. It integrates all core modules to process natural language
prompts and determine appropriate tool calls.

It also provides IPC server mode for communication with the SwiftUI frontend.
"""

import argparse
import asyncio
import json
import logging
import os
import time
import sys
from pathlib import Path
from typing import Any, NoReturn

from dotenv import load_dotenv

from agent_host.audit_logger import AuditLogger, AuditLogError, EventType
from agent_host.config import Config, ConfigurationError
from agent_host.gemini_client import (
    GeminiClient,
    GeminiAPIError,
    GeminiClientError,
    GeminiRateLimitError,
    GeminiServerError,
)
from agent_host.schema_validator import (
    SchemaValidator,
    SchemaLoadError,
    SchemaNotFoundError,
    ValidationFailedError,
)
from agent_host.tool_parser import ToolCallParser, MalformedResponseError
from agent_host.system_prompt import build_system_prompt, inject_model_identity
from agent_host.system_prompt import SystemPromptLoadError
from agent_host.memory.embeddings import EmbeddingService
from agent_host.memory.manager import MemoryManager
from agent_host.memory.migration import MemoryMigrationError, run_preflight_migration
from agent_host.memory.store import get_db_metrics_snapshot
from agent_host.observability import configure_logging
from agent_host.response_sanitizer import (
    looks_like_json_payload,
    sanitize_user_visible_response,
)
from agent_host.tools.executor import ToolExecutionError, ToolExecutor

logger = logging.getLogger(__name__)

# Exit codes
EXIT_SUCCESS = 0
EXIT_CONFIG_ERROR = 1
EXIT_API_ERROR = 2
EXIT_VALIDATION_ERROR = 3


from agent_host.core.services.prompt_service import (  # noqa: E402
    _format_exception_message,
    _format_tool_execution_output,
    _parse_memory_mode,
    _safe_env_float,
    _safe_env_int,
)

# ---------------------------------------------------------------------------
# Plan-mode logic (co-located in adapters/modes/plan/state_machine.py)
# ---------------------------------------------------------------------------
from agent_host.adapters.modes.plan.state_machine import (  # noqa: E402
    PlanClarificationState,
    _preload_plan_mode_nlp_classifier,
)

# Canonical definition lives in contracts.types.domain; re-exported here
# for backward compatibility with all existing references.
from agent_host.contracts.types.domain import ExecutionMode  # noqa: E402,F811


def setup_logging(verbose: bool) -> None:
    """Configure logging based on verbosity setting.
    
    Args:
        verbose: If True, enable DEBUG level logging. Otherwise INFO.
    """
    configure_logging(verbose=verbose)


def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser.
    
    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        prog="ai-agent",
        description="Personal macOS AI Agent - Process natural language prompts to determine tool calls",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ai-agent "Find all Python files in my Documents folder"
  ai-agent --verbose "Get metadata for ~/Desktop/report.pdf"
  ai-agent --dry-run "Open the Notes app"
  ai-agent --server  # Run IPC server for SwiftUI frontend

Exit Codes:
  0 - Success
  1 - Configuration error (missing API key, invalid config)
  2 - API error (rate limit, network issues)
  3 - Validation error (invalid tool call arguments)
        """,
    )
    
    parser.add_argument(
        "prompt",
        type=str,
        nargs="?",
        default=None,
        help="Natural language prompt describing the desired action",
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output with debug logging",
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't call API, just show configuration",
    )
    
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output",
    )
    
    parser.add_argument(
        "--server",
        action="store_true",
        help="Run IPC server for SwiftUI frontend communication",
    )
    
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="WebSocket host/interface for IPC server",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="WebSocket TCP port for IPC server",
    )
    
    return parser


def print_error(message: str, no_color: bool = False) -> None:
    """Print an error message to stderr.
    
    Args:
        message: Error message to print.
        no_color: If True, don't use ANSI colors.
    """
    if no_color:
        print(f"Error: {message}", file=sys.stderr)
    else:
        print(f"\033[91mError:\033[0m {message}", file=sys.stderr)


def print_success(message: str, no_color: bool = False) -> None:
    """Print a success message to stdout.
    
    Args:
        message: Success message to print.
        no_color: If True, don't use ANSI colors.
    """
    if no_color:
        print(f"Success: {message}")
    else:
        print(f"\033[92mSuccess:\033[0m {message}")


def print_info(message: str, no_color: bool = False) -> None:
    """Print an info message to stdout.
    
    Args:
        message: Info message to print.
        no_color: If True, don't use ANSI colors.
    """
    if no_color:
        print(f"Info: {message}")
    else:
        print(f"\033[94mInfo:\033[0m {message}")


def run_dry_run(config: Config, no_color: bool = False) -> None:
    """Execute a dry run showing configuration without calling API.
    
    Args:
        config: Configuration instance.
        no_color: If True, don't use ANSI colors.
    """
    print_info("Dry run mode - showing configuration:", no_color)
    print()
    print(f"Model: {config.model_name or '<auto-resolve from live catalog>'}")
    print(f"Require No-Training: {config.require_no_training}")
    print(f"Use Vertex AI: {config.use_vertexai}")
    if config.use_vertexai:
        print(f"Vertex Project: {config.vertex_project}")
        print(f"Vertex Location: {config.vertex_location}")
    print(f"Schemas Directory: {config.schemas_dir}")
    print(f"Audit Log Path: {config.audit_log_path}")
    print(f"Audit Include Prompt: {bool(getattr(config, 'audit_include_prompt', False))}")
    print(f"Memory Root: {config.memory_root}")
    print(f"Max Retries: {config.max_retries}")
    print(f"Retry Delay: {config.retry_delay}s")
    
    # Check schemas directory
    if config.validate_schemas_dir():
        schema_files = list(config.schemas_dir.glob("*.json"))
        print(f"Schemas Found: {len(schema_files)}")
        for schema_file in schema_files:
            print(f"  - {schema_file.name}")
    else:
        print("Schemas Status: NOT FOUND or empty")


async def run_server(
    config: Config,
    host: str = "127.0.0.1",
    port: int = 8765,
    verbose: bool = False,
) -> int:
    """Run the IPC server for SwiftUI frontend communication.
    
    Args:
        config: Configuration instance.
        host: WebSocket host/interface to bind.
        port: WebSocket TCP port to bind.
        verbose: Whether verbose mode is enabled.
    Returns:
        Exit code (0 for success, non-zero for errors).
    """
    from agent_host.ipc.server import IPCServer, ClientConnection
    from agent_host.ipc.protocol import (
        PROTOCOL_VERSION,
        IncomingRequest,
        ErrorMessage,
        SystemMessage,
    )
    from agent_host.ipc.hot_reload import init_reload_manager, is_hot_reload_enabled, ReloadEvent
    
    logger = logging.getLogger(__name__)
    if verbose:
        logger.info("IPC server running with verbose mode enabled")
    try:
        audit_logger = AuditLogger(config.audit_log_path)
        audit_logger.log_event(
            EventType.STARTUP,
            {
                "mode": "ipc_server",
                "model": config.model_name or "<auto-resolve-from-live-catalog>",
                "endpoint": f"ws://{host}:{port}",
            },
        )
    except AuditLogError as e:
        logger.error("Audit logging initialization failed: %s", e)
        return EXIT_CONFIG_ERROR
    
    # Initialize components
    try:
        validator = SchemaValidator(config.schemas_dir)
        tools = validator.get_all_tools_for_gemini()
        logger.info(f"Loaded {len(tools)} tool schemas")
    except SchemaLoadError as e:
        logger.error(f"Schema loading error: {e}")
        return EXIT_CONFIG_ERROR
    
    if not tools:
        logger.error("No tool schemas found in schemas directory")
        return EXIT_CONFIG_ERROR

    try:
        migration_result = run_preflight_migration(config.memory_root)
        if migration_result.already_migrated:
            logger.info(
                "Memory preflight migration already completed (marker=%s)",
                migration_result.marker_path,
            )
        else:
            logger.info(
                "Memory preflight migration completed (upgraded_hmac_rows=%s removed_ghost_sessions=%s backup=%s marker=%s)",
                migration_result.upgraded_hmac_rows,
                migration_result.removed_ghost_sessions,
                migration_result.backup_path,
                migration_result.marker_path,
            )
    except MemoryMigrationError as exc:
        logger.error("Strict memory migration failed: %s", exc)
        return EXIT_CONFIG_ERROR

    # Initialize secure session memory manager
    try:
        memory_manager = MemoryManager(config.memory_root)
        logger.info("Memory manager initialized at %s", config.memory_root)
    except Exception as e:
        logger.error("Failed to initialize memory manager: %s", e)
        return EXIT_CONFIG_ERROR

    # ------------------------------------------------------------------
    # Event bus (optional, decoupled pub/sub for audit & cross-cutting)
    # ------------------------------------------------------------------
    from agent_host.adapters.event_bus import InMemoryEventBus
    event_bus = InMemoryEventBus()

    # Build tool plugins with graceful degradation (composition root).
    try:
        from agent_host.adapters.tools.create_directory import CreateDirectoryPlugin
        from agent_host.adapters.tools.open_item import OpenItemPlugin
        from agent_host.adapters.tools.read_document import ReadDocumentPlugin
        from agent_host.adapters.tools.planner import PlannerPlugin
        from agent_host.adapters.tools.plan_ops import PlanOpsPlugin
        from agent_host.adapters.tools.apply_ops import ApplyOpsPlugin
        from agent_host.adapters.tools.browse_web import BrowseWebPlugin
        from agent_host.adapters.tools.search_files import SearchFilesPlugin
        from agent_host.adapters.storage.in_memory_plan_store import InMemoryPlanStore
        from agent_host.planning import (
            UnifiedPlanningEngine,
            UnifiedPlanningSecurityError,
            UnifiedPlanningUnavailableError,
        )

        plan_store = InMemoryPlanStore()
        try:
            planner_engine = UnifiedPlanningEngine()
        except (UnifiedPlanningUnavailableError, UnifiedPlanningSecurityError) as exc:
            logger.error(
                "Secure unified-planning engine initialization failed: %s", exc
            )
            return EXIT_CONFIG_ERROR

        roots_list = [
            root.expanduser().resolve(strict=False) for root in config.allowed_roots
        ]
        # Deduplicate while preserving order
        roots_list = list(dict.fromkeys(roots_list))

        _tool_plugins = []
        for plugin_cls, kwargs in [
            (CreateDirectoryPlugin, {"allowed_roots": roots_list}),
            (OpenItemPlugin, {"allowed_roots": roots_list, "enable": config.enable_open_item}),
            (ReadDocumentPlugin, {"allowed_roots": roots_list}),
            (PlannerPlugin, {"planner_engine": planner_engine, "plan_store": plan_store, "allowed_roots": roots_list}),
            (PlanOpsPlugin, {"planner_engine": planner_engine, "plan_store": plan_store, "allowed_roots": roots_list}),
            (ApplyOpsPlugin, {"plan_store": plan_store, "allowed_roots": roots_list, "enable_open_item": config.enable_open_item}),
            (BrowseWebPlugin, {}),
            (SearchFilesPlugin, {"allowed_roots": roots_list, "search_scan_limit": max(200, int(config.search_scan_limit))}),
        ]:
            try:
                _tool_plugins.append(plugin_cls(**kwargs))
            except Exception as exc:
                logger.error("Failed to create plugin %s: %s", plugin_cls.__name__, exc)

        tool_executor = ToolExecutor(plugins=_tool_plugins, event_bus=event_bus)
        logger.info(
            "Tool executor initialized (roots=%s, plugins=%s)",
            [str(root) for root in roots_list],
            tool_executor.list_plugins(),
        )

        # Verify plugin health at startup
        _plugin_health = tool_executor.get_health_status()
        for _pname, _pstatus in _plugin_health.items():
            if _pstatus["ok"]:
                logger.info("Plugin '%s' healthy", _pname)
            else:
                logger.warning("Plugin '%s' health check failed: %s", _pname, _pstatus.get("error"))
    except Exception as e:
        logger.error("Failed to initialize tool executor: %s", e)
        return EXIT_CONFIG_ERROR

    # Async tool plugins (note/image/screen — dispatched per-request with context).
    from agent_host.adapters.tools.manage_notes import ManageNotesPlugin
    from agent_host.adapters.tools.generate_image import GenerateImagePlugin
    from agent_host.adapters.tools.read_screen import ReadScreenPlugin
    _async_plugins: dict[str, Any] = {}
    for _ap in [ManageNotesPlugin(), GenerateImagePlugin(), ReadScreenPlugin()]:
        _async_plugins[_ap.name] = _ap

    # Initialize Gemini client
    try:
        gemini_client = GeminiClient(
            api_key=config.gemini_api_key,
            model_name=config.model_name,
            max_retries=config.max_retries,
            retry_delay=config.retry_delay,
            require_no_training=config.require_no_training,
            use_vertexai=config.use_vertexai,
            vertex_project=config.vertex_project,
            vertex_location=config.vertex_location,
        )
        config.model_name = gemini_client.resolve_text_model(config.model_name or None)
        logger.info("Gemini client initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Gemini client: {e}")
        return EXIT_CONFIG_ERROR

    # Wire semantic embedding service (uses Gemini text-embedding-004)
    try:
        embedding_client = getattr(gemini_client, "_client", gemini_client)
        embedding_service = EmbeddingService(embedding_client)
        memory_manager.set_embedding_service(embedding_service)
        logger.info("Semantic embedding service initialized")
    except Exception as e:
        logger.error("Embedding service initialization failed: %s", e)
        return EXIT_CONFIG_ERROR

    ipc_auth_token = os.environ.get("AI_AGENT_IPC_AUTH_TOKEN", "").strip()
    if not ipc_auth_token:
        if os.environ.get("PYTEST_CURRENT_TEST"):
            ipc_auth_token = "test-ipc-auth-token"
            logger.warning(
                "AI_AGENT_IPC_AUTH_TOKEN missing under pytest; using deterministic test token."
            )
        else:
            logger.error(
                "Missing required AI_AGENT_IPC_AUTH_TOKEN. Refusing to start unauthenticated IPC server."
            )
            return EXIT_CONFIG_ERROR

    # Create IPC server
    server_max_clients = max(1, _safe_env_int("AI_AGENT_IPC_MAX_CLIENTS", 128))
    server = IPCServer(
        host=host,
        port=port,
        max_clients=server_max_clients,
        require_auth=True,
        auth_token=ipc_auth_token,
        required_protocol_version=PROTOCOL_VERSION,
    )
    
    # Build base system prompt once at startup (cached for all requests).
    # Model identity is injected per-request via inject_model_identity().
    try:
        base_system_instruction = build_system_prompt(tools)
        logger.info(
            "Base system prompt loaded (%s chars, %s tools injected)",
            len(base_system_instruction),
            len(tools),
        )
    except SystemPromptLoadError as e:
        logger.error("System prompt load error: %s", e)
        return EXIT_CONFIG_ERROR

    # Track active prompt tasks for cancellation and lifecycle management
    active_prompt_tasks: dict[str, asyncio.Task[None]] = {}
    cancelled_prompt_requests: set[str] = set()

    from agent_host.core.services.ipc_bridge import IPCBridge
    ipc_bridge = IPCBridge(
        server=server,
        active_tasks=active_prompt_tasks,
        cancelled_requests=cancelled_prompt_requests,
    )

    client_prompt_index: dict[str, set[str]] = {}
    device_registry: dict[str, dict[str, Any]] = {}
    pending_tool_confirmations: dict[str, tuple[str, asyncio.Future[bool]]] = {}
    pending_screen_captures: dict[str, tuple[str, asyncio.Future[dict | None]]] = {}
    pending_tool_proxies: dict[str, tuple[str, asyncio.Future[dict[str, Any]]]] = {}
    plan_mode_clarification_states: dict[str, PlanClarificationState] = {}
    plan_mode_sessions_with_plan: dict[str, float] = {}  # session_id → timestamp
    # Runtime-only planner preference learning. Not persisted to memory DB.
    plan_mode_option_learning_by_session: dict[str, dict[str, dict[str, float]]] = {}
    plan_mode_option_learning_global: dict[str, dict[str, float]] = {}
    destructive_tool_names = {"apply_ops"}
    plan_mode_allowed_tools = {
        "planner",
        "plan_ops",
        "search_files",
        "read_document",
        "read_screen",
        "manage_notes",
        "generate_image",
        "browse_web",
    }
    confirmation_timeout_seconds = 60.0
    db_timeout_seconds = _safe_env_float("AI_AGENT_DB_TIMEOUT_SECONDS", 20.0)
    model_timeout_seconds = _safe_env_float("AI_AGENT_MODEL_TIMEOUT_SECONDS", 180.0)
    image_timeout_seconds = max(
        1.0,
        _safe_env_float("AI_AGENT_IMAGE_TIMEOUT_SECONDS", config.image_timeout_seconds),
    )
    image_output_root = config.image_output_root.expanduser().resolve(strict=False)
    image_model_override = config.image_model_override
    deep_think_model_timeout_multiplier = _safe_env_float(
        "AI_AGENT_DEEP_THINK_MODEL_TIMEOUT_MULTIPLIER",
        1.25,
    )
    teacher_model_timeout_multiplier = _safe_env_float(
        "AI_AGENT_TEACHER_MODEL_TIMEOUT_MULTIPLIER",
        1.10,
    )
    continuation_model_timeout_multiplier = _safe_env_float(
        "AI_AGENT_CONTINUATION_MODEL_TIMEOUT_MULTIPLIER",
        1.15,
    )
    model_timeout_max_seconds = _safe_env_float("AI_AGENT_MODEL_TIMEOUT_MAX_SECONDS", 300.0)
    tool_timeout_seconds = _safe_env_float("AI_AGENT_TOOL_TIMEOUT_SECONDS", 120.0)
    prompt_timeout_seconds = _safe_env_float("AI_AGENT_PROMPT_TIMEOUT_SECONDS", 300.0)
    prompt_timeout_max_seconds = _safe_env_float("AI_AGENT_PROMPT_TIMEOUT_MAX_SECONDS", 900.0)
    max_tool_chain_depth = _safe_env_int("AI_AGENT_MAX_TOOL_CHAIN_DEPTH", 100)
    read_screen_ocr_max_chars = max(800, _safe_env_int("AI_AGENT_READ_SCREEN_OCR_MAX_CHARS", 12000))
    read_screen_ocr_max_lines = max(20, _safe_env_int("AI_AGENT_READ_SCREEN_OCR_MAX_LINES", 220))
    db_metrics_interval_seconds = _safe_env_float(
        "AI_AGENT_DEBUG_DB_METRICS_INTERVAL_SECONDS", 15.0
    )
    db_metrics_enabled = os.environ.get("AI_AGENT_DEBUG_DB_METRICS", "0").strip() == "1"
    db_metrics_task: asyncio.Task[None] | None = None
    plan_mode_nlp_preload_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Runtime services (shared utilities for handlers and orchestrator)
    # ------------------------------------------------------------------
    from agent_host.core.services.runtime_services import RuntimeServices

    runtime = RuntimeServices(
        ipc_bridge=ipc_bridge,
        memory_manager=memory_manager,
        db_timeout_seconds=db_timeout_seconds,
        active_prompt_tasks=active_prompt_tasks,
        cancelled_prompt_requests=cancelled_prompt_requests,
        client_prompt_index=client_prompt_index,
        device_registry=device_registry,
        pending_tool_confirmations=pending_tool_confirmations,
        pending_screen_captures=pending_screen_captures,
    )

    # ------------------------------------------------------------------
    # Mode handler factory + plan mode module injection (F2: DI)
    # ------------------------------------------------------------------
    from agent_host.adapters.modes.direct import DirectModeHandler
    from agent_host.adapters.modes.plan import PlanModeHandler
    from agent_host.adapters.modes.teacher import TeacherModeHandler
    from agent_host.adapters.modes.plan import state_machine as plan_mode_ops  # noqa: E501
    from agent_host.adapters.modes.plan import prompts as plan_mode_prompts
    from agent_host.adapters.modes.teacher.config import TEACHER_NOTE_COMPLETION_TOOLS

    def _create_mode_handler(execution_mode: ExecutionMode, context: dict) -> Any:
        if execution_mode == ExecutionMode.PLAN:
            return PlanModeHandler(**{
                k: v for k, v in context.items()
                if k in ("is_followup", "requires_unified_planning", "discovery_budget", "allowed_tools")
            })
        elif execution_mode == ExecutionMode.TEACHER:
            return TeacherModeHandler(**{
                k: v for k, v in context.items()
                if k in ("memory_manager", "send_status", "session_id")
            })
        else:
            return DirectModeHandler()

    # ------------------------------------------------------------------
    # Prompt orchestrator
    # ------------------------------------------------------------------
    from agent_host.core.orchestrator import PromptOrchestrator

    orchestrator = PromptOrchestrator(
        gemini_client=gemini_client,
        memory_manager=memory_manager,
        tool_executor=tool_executor,
        ipc_bridge=ipc_bridge,
        audit_logger=audit_logger,
        server=server,
        validator=validator,
        config=config,
        mode_handler_factory=_create_mode_handler,
        plan_mode_ops=plan_mode_ops,
        plan_mode_prompts=plan_mode_prompts,
        teacher_completion_tools=TEACHER_NOTE_COMPLETION_TOOLS,
        tools=tools,
        base_system_instruction=base_system_instruction,
        async_plugins=_async_plugins,
        plan_mode_clarification_states=plan_mode_clarification_states,
        plan_mode_sessions_with_plan=plan_mode_sessions_with_plan,
        plan_mode_option_learning_by_session=plan_mode_option_learning_by_session,
        plan_mode_option_learning_global=plan_mode_option_learning_global,
        pending_tool_confirmations=pending_tool_confirmations,
        pending_screen_captures=pending_screen_captures,
        pending_tool_proxies=pending_tool_proxies,
        active_prompt_tasks=active_prompt_tasks,
        cancelled_prompt_requests=cancelled_prompt_requests,
        client_prompt_index=client_prompt_index,
        device_registry=device_registry,
        confirmation_timeout_seconds=confirmation_timeout_seconds,
        db_timeout_seconds=db_timeout_seconds,
        model_timeout_seconds=model_timeout_seconds,
        image_timeout_seconds=image_timeout_seconds,
        image_output_root=image_output_root,
        image_model_override=image_model_override,
        deep_think_model_timeout_multiplier=deep_think_model_timeout_multiplier,
        teacher_model_timeout_multiplier=teacher_model_timeout_multiplier,
        continuation_model_timeout_multiplier=continuation_model_timeout_multiplier,
        model_timeout_max_seconds=model_timeout_max_seconds,
        tool_timeout_seconds=tool_timeout_seconds,
        prompt_timeout_seconds=prompt_timeout_seconds,
        prompt_timeout_max_seconds=prompt_timeout_max_seconds,
        max_tool_chain_depth=max_tool_chain_depth,
        read_screen_ocr_max_chars=read_screen_ocr_max_chars,
        read_screen_ocr_max_lines=read_screen_ocr_max_lines,
        destructive_tool_names=destructive_tool_names,
        plan_mode_allowed_tools=plan_mode_allowed_tools,
        run_blocking_with_timeout=runtime.run_blocking_with_timeout,
        client_capabilities_for=runtime.client_capabilities_for,
        broadcast_session_refresh=runtime.broadcast_session_refresh,
        resolve_note_id=runtime.resolve_note_id,
        request_timeout_error_cls=RuntimeServices.RequestTimeoutError,
    )

    # ------------------------------------------------------------------
    # Infrastructure handlers
    # ------------------------------------------------------------------
    plan_mode_nlp_state: dict[str, Any] = {
        "ready": False,
        "error": None,
    }

    from agent_host.core.handlers.infrastructure import InfrastructureHandlers
    from agent_host.adapters.tools._path_security import normalize_user_path

    infra = InfrastructureHandlers(
        runtime=runtime,
        orchestrator=orchestrator,
        tool_executor=tool_executor,
        gemini_client=gemini_client,
        audit_logger=audit_logger,
        config=config,
        server=server,
        ipc_bridge=ipc_bridge,
        memory_manager=memory_manager,
        tools=tools,
        base_system_instruction=base_system_instruction,
        active_prompt_tasks=active_prompt_tasks,
        cancelled_prompt_requests=cancelled_prompt_requests,
        client_prompt_index=client_prompt_index,
        pending_tool_confirmations=pending_tool_confirmations,
        pending_screen_captures=pending_screen_captures,
        pending_tool_proxies=pending_tool_proxies,
        device_registry=device_registry,
        db_timeout_seconds=db_timeout_seconds,
        confirmation_timeout_seconds=confirmation_timeout_seconds,
        tool_timeout_seconds=tool_timeout_seconds,
        model_timeout_seconds=model_timeout_seconds,
        deep_think_model_timeout_multiplier=deep_think_model_timeout_multiplier,
        teacher_model_timeout_multiplier=teacher_model_timeout_multiplier,
        continuation_model_timeout_multiplier=continuation_model_timeout_multiplier,
        model_timeout_max_seconds=model_timeout_max_seconds,
        prompt_timeout_seconds=prompt_timeout_seconds,
        prompt_timeout_max_seconds=prompt_timeout_max_seconds,
        plan_mode_nlp_state=plan_mode_nlp_state,
        normalize_path_fn=normalize_user_path,
    )

    # ------------------------------------------------------------------
    # Use case instances (session / memory / notes / models handlers)
    # ------------------------------------------------------------------
    from agent_host.core.use_cases.manage_session import SessionUseCases
    from agent_host.core.use_cases.manage_notes import NotesUseCases
    from agent_host.core.use_cases.manage_memory import MemoryUseCases
    from agent_host.core.use_cases.manage_models import ModelsUseCases

    session_uc = SessionUseCases(
        memory_manager=memory_manager,
        ipc_bridge=ipc_bridge,
        run_blocking=runtime.run_blocking_with_timeout,
        db_timeout_seconds=db_timeout_seconds,
        audit_logger=audit_logger,
        event_bus=event_bus,
    )
    notes_uc = NotesUseCases(
        memory_manager=memory_manager,
        ipc_bridge=ipc_bridge,
        run_blocking=runtime.run_blocking_with_timeout,
        db_timeout_seconds=db_timeout_seconds,
        broadcast_session_refresh=runtime.broadcast_session_refresh,
        event_bus=event_bus,
    )
    memory_uc = MemoryUseCases(
        memory_manager=memory_manager,
        ipc_bridge=ipc_bridge,
        run_blocking=runtime.run_blocking_with_timeout,
        db_timeout_seconds=db_timeout_seconds,
        broadcast_session_refresh=runtime.broadcast_session_refresh,
        event_bus=event_bus,
    )
    models_uc = ModelsUseCases(
        gemini_client=gemini_client,
        format_exception_message=_format_exception_message,
    )

    # ------------------------------------------------------------------
    # Audit event subscriber (event bus → audit trail)
    # ------------------------------------------------------------------
    from agent_host.core.subscribers.audit_subscriber import AuditEventSubscriber
    audit_subscriber = AuditEventSubscriber(audit_logger)
    audit_subscriber.register(event_bus)

    # ------------------------------------------------------------------
    # Hot reload manager
    # ------------------------------------------------------------------
    reload_manager = init_reload_manager(
        watch_dir=Path(__file__).parent,
        poll_interval=2.0,
        auto_watch=True,
    )

    def on_reload_complete(event: ReloadEvent) -> None:
        """Callback when hot reload completes - notify all clients."""
        logger.info(f"Hot reload event: {event.trigger}, success={event.success}")

    reload_manager.on_reload(on_reload_complete)

    # ------------------------------------------------------------------
    # Client disconnect handler
    # ------------------------------------------------------------------
    server.set_disconnect_handler(infra.handle_client_disconnect)

    # ------------------------------------------------------------------
    # Reload and version handlers (depend on reload_manager, kept as closures)
    # ------------------------------------------------------------------
    async def handle_reload(request: IncomingRequest, client: ClientConnection) -> None:
        """Handles reload requests from the SwiftUI frontend."""
        request_id = request.id
        trigger = request.params.get("trigger", "ipc")

        logger.info(f"Reload requested via IPC (trigger: {trigger})")

        if not is_hot_reload_enabled():
            await client.send(
                ErrorMessage.invalid_request(
                    request_id,
                    "Hot reload is disabled in this environment",
                ).to_bytes()
            )
            return

        started_msg = SystemMessage.reload_started(request_id, trigger)
        await client.send(started_msg.to_bytes())

        event = reload_manager.reload_modules(trigger=trigger)

        complete_msg = SystemMessage.reload_complete(
            request_id,
            success=event.success,
            new_version=reload_manager.version,
            error=event.error,
        )
        await client.send(complete_msg.to_bytes())

        if event.success:
            logger.info(f"Reload complete. New version: {reload_manager.version}")
        else:
            logger.error(f"Reload failed: {event.error}")

    async def handle_version(request: IncomingRequest, client: ClientConnection) -> None:
        """Handles version requests - returns protocol and code version."""
        version_msg = SystemMessage.version_info(
            request.id,
            protocol_version=PROTOCOL_VERSION,
            code_version=reload_manager.version,
            features=[
                "auth.hello",
                "device.register",
                "prompt",
                "prompt.execution_mode",
                "prompt.input_paths",
                "cancel",
                "tool.confirm",
                "tool.execute_response",
                "screen.capture_response",
                "ping",
                "reload",
                "version",
                "session.create",
                "session.list",
                "session.list_since",
                "session.history",
                "session.history_page",
                "models.list",
                "session.set_mode",
                "session.rename",
                "session.delete",
                "session.delete_many",
                "memory.list",
                "memory.delete",
                "notes.list",
                "notes.create",
                "notes.update",
                "notes.delete",
                "notes.get_image",
                "notes.list_versions",
                "system.session_events",
                "system.notes_events",
                "system.memory_events",
            ],
        )
        await client.send(version_msg.to_bytes())

    # ------------------------------------------------------------------
    # Register all handlers
    # ------------------------------------------------------------------
    server.register_handler("prompt", infra.handle_prompt)
    server.register_handler("cancel", infra.handle_cancel)
    server.register_handler("tool.confirm", infra.handle_tool_confirm)
    server.register_handler("screen.capture_response", infra.handle_screen_capture)
    server.register_handler("device.register", infra.handle_device_register)
    server.register_handler("tool.execute_response", infra.handle_tool_execute_response)
    server.register_handler("ping", infra.handle_ping)
    server.register_handler("system.diagnostics", infra.handle_system_diagnostics)
    server.register_handler("session.create", session_uc.handle_create)
    server.register_handler("session.list", session_uc.handle_list)
    server.register_handler("session.list_since", session_uc.handle_list_since)
    server.register_handler("session.history", session_uc.handle_history)
    server.register_handler("session.history_page", session_uc.handle_history_page)
    server.register_handler("models.list", models_uc.handle_list)
    server.register_handler("session.set_mode", session_uc.handle_set_mode)
    server.register_handler("session.rename", session_uc.handle_rename)
    server.register_handler("session.delete", session_uc.handle_delete)
    server.register_handler("session.delete_many", session_uc.handle_delete_many)
    server.register_handler("memory.list", memory_uc.handle_list)
    server.register_handler("memory.delete", memory_uc.handle_delete)
    server.register_handler("notes.list", notes_uc.handle_list)
    server.register_handler("notes.create", notes_uc.handle_create)
    server.register_handler("notes.update", notes_uc.handle_update)
    server.register_handler("notes.delete", notes_uc.handle_delete)
    server.register_handler("notes.get_image", notes_uc.handle_get_image)
    server.register_handler("notes.list_versions", notes_uc.handle_list_versions)
    server.register_handler("reload", handle_reload)
    server.register_handler("version", handle_version)

    async def _db_metrics_reporter() -> None:
        while True:
            await asyncio.sleep(max(1.0, db_metrics_interval_seconds))
            snapshot = get_db_metrics_snapshot()
            logger.info(
                "sqlite_metrics",
                extra={
                    "component": "db.metrics",
                    "method": "sqlite",
                    "duration_ms": None,
                    "error_type": None,
                    "error_message": None,
                    "metrics": snapshot,
                },
            )

    async def _plan_mode_nlp_preload_worker() -> None:
        started = time.perf_counter()
        try:
            model_name = await asyncio.to_thread(_preload_plan_mode_nlp_classifier, logger)
            plan_mode_nlp_state["ready"] = True
            plan_mode_nlp_state["error"] = None
            logger.info(
                "Plan clarification classifier warmup complete",
                extra={
                    "component": "plan_mode_nlp_preload",
                    "method": "startup",
                    "duration_ms": None,
                    "error_type": None,
                    "error_message": None,
                    "model_name": model_name,
                },
            )
        except Exception as exc:
            plan_mode_nlp_state["ready"] = False
            plan_mode_nlp_state["error"] = _format_exception_message(
                exc,
                fallback="plan clarification classifier unavailable",
            )
            logger.error(
                "Plan clarification classifier warmup failed: %s",
                plan_mode_nlp_state["error"],
            )
        finally:
            preload_ms = (time.perf_counter() - started) * 1000.0
            logger.info(
                "plan_mode_nlp_preload_complete",
                extra={
                    "component": "plan_mode_nlp_preload",
                    "method": "startup",
                    "duration_ms": round(preload_ms, 3),
                    "error_type": None if plan_mode_nlp_state["ready"] else "RuntimeError",
                    "error_message": plan_mode_nlp_state["error"],
                },
            )

    # Start server
    try:
        socket_bind_started = time.perf_counter()
        await server.start()
        socket_bind_ms = (time.perf_counter() - socket_bind_started) * 1000.0
        logger.info(
            "ipc_socket_bound",
            extra={
                "component": "ipc.server",
                "method": "startup",
                "duration_ms": round(socket_bind_ms, 3),
                "error_type": None,
                "error_message": None,
            },
        )
        plan_mode_nlp_preload_task = asyncio.create_task(_plan_mode_nlp_preload_worker())
        infra.set_nlp_preload_task(plan_mode_nlp_preload_task)
        if db_metrics_enabled:
            db_metrics_task = asyncio.create_task(_db_metrics_reporter())
        
        # Start hot reload file watcher
        await reload_manager.start()
        
        print_info(f"IPC Server started on {server.endpoint_url}")
        print_info(f"Protocol version: {PROTOCOL_VERSION}")
        print_info(f"Code version: {reload_manager.version}")
        print_info("Hot reload enabled - code changes will be auto-detected")
        print_info("Press Ctrl+C to stop...")
        
        # Wait for shutdown signal
        try:
            await server.serve_forever()
        except asyncio.CancelledError:
            pass
    
    finally:
        # Cancel any in-flight prompt tasks before shutdown.
        if plan_mode_nlp_preload_task is not None:
            plan_mode_nlp_preload_task.cancel()
            await asyncio.gather(plan_mode_nlp_preload_task, return_exceptions=True)
        if db_metrics_task is not None:
            db_metrics_task.cancel()
            await asyncio.gather(db_metrics_task, return_exceptions=True)
        for task in list(active_prompt_tasks.values()):
            if not task.done():
                task.cancel()
        if active_prompt_tasks:
            await asyncio.gather(*active_prompt_tasks.values(), return_exceptions=True)
        await reload_manager.stop()
        await server.stop()
        if audit_logger:
            try:
                audit_logger.log_event(
                    EventType.SHUTDOWN,
                    {
                        "mode": "ipc_server",
                    },
                )
            except AuditLogError as e:
                logger.warning("Failed to write audit shutdown event: %s", e)
        print_info("IPC Server stopped")
    
    return EXIT_SUCCESS


def main(args: list[str] | None = None) -> int:
    """Main entry point for the CLI.
    
    Args:
        args: Command line arguments. If None, uses sys.argv.
    
    Returns:
        Exit code (0 for success, non-zero for errors).
    """
    # Load environment variables from .env file (if exists)
    load_dotenv()
    
    parser = create_argument_parser()
    parsed_args = parser.parse_args(args)
    
    # Setup logging
    setup_logging(parsed_args.verbose)
    logger = logging.getLogger(__name__)
    
    no_color = parsed_args.no_color
    
    # Step 1: Load configuration from environment
    try:
        config = Config.from_env()
        logger.debug("Configuration loaded successfully")
    except ConfigurationError as e:
        print_error(f"Configuration error: {e}", no_color)
        return EXIT_CONFIG_ERROR
    
    # Handle dry run mode
    if parsed_args.dry_run:
        run_dry_run(config, no_color)
        return EXIT_SUCCESS
    
    # Handle server mode
    if parsed_args.server:
        return asyncio.run(
            run_server(
                config,
                host=parsed_args.host,
                port=parsed_args.port,
                verbose=parsed_args.verbose,
            )
        )
    
    # For CLI mode, prompt is required
    if not parsed_args.prompt:
        print_error("prompt is required for CLI mode. Use --server for IPC mode.", no_color)
        return EXIT_CONFIG_ERROR
    
    # Step 2: Load schemas and create validator
    try:
        validator = SchemaValidator(config.schemas_dir)
        tools = validator.get_all_tools_for_gemini()
        logger.debug(f"Loaded {len(tools)} tool schemas")
    except SchemaLoadError as e:
        print_error(f"Schema loading error: {e}", no_color)
        return EXIT_CONFIG_ERROR
    
    if not tools:
        print_error("No tool schemas found in schemas directory", no_color)
        return EXIT_CONFIG_ERROR

    try:
        migration_result = run_preflight_migration(config.memory_root)
        if migration_result.already_migrated:
            logger.info(
                "Memory preflight migration already completed (marker=%s)",
                migration_result.marker_path,
            )
        else:
            logger.info(
                "Memory preflight migration completed (upgraded_hmac_rows=%s removed_ghost_sessions=%s backup=%s marker=%s)",
                migration_result.upgraded_hmac_rows,
                migration_result.removed_ghost_sessions,
                migration_result.backup_path,
                migration_result.marker_path,
            )
    except MemoryMigrationError as e:
        print_error(f"Strict memory migration failed: {e}", no_color)
        return EXIT_CONFIG_ERROR

    try:
        memory_manager = MemoryManager(config.memory_root)
        logger.debug("Memory manager initialized")
    except Exception as e:
        print_error(f"Memory manager initialization failed: {e}", no_color)
        return EXIT_CONFIG_ERROR

    try:
        from agent_host.adapters.tools.create_directory import CreateDirectoryPlugin
        from agent_host.adapters.tools.open_item import OpenItemPlugin
        from agent_host.adapters.tools.read_document import ReadDocumentPlugin
        from agent_host.adapters.tools.planner import PlannerPlugin
        from agent_host.adapters.tools.plan_ops import PlanOpsPlugin
        from agent_host.adapters.tools.apply_ops import ApplyOpsPlugin
        from agent_host.adapters.tools.browse_web import BrowseWebPlugin
        from agent_host.adapters.tools.search_files import SearchFilesPlugin
        from agent_host.adapters.storage.in_memory_plan_store import InMemoryPlanStore
        from agent_host.planning import UnifiedPlanningEngine

        cli_plan_store = InMemoryPlanStore()
        cli_planner_engine = UnifiedPlanningEngine()
        cli_roots = [root.expanduser().resolve(strict=False) for root in config.allowed_roots]
        cli_roots = list(dict.fromkeys(cli_roots))

        cli_plugins = []
        for pcls, pkw in [
            (CreateDirectoryPlugin, {"allowed_roots": cli_roots}),
            (OpenItemPlugin, {"allowed_roots": cli_roots, "enable": config.enable_open_item}),
            (ReadDocumentPlugin, {"allowed_roots": cli_roots}),
            (PlannerPlugin, {"planner_engine": cli_planner_engine, "plan_store": cli_plan_store, "allowed_roots": cli_roots}),
            (PlanOpsPlugin, {"planner_engine": cli_planner_engine, "plan_store": cli_plan_store, "allowed_roots": cli_roots}),
            (ApplyOpsPlugin, {"plan_store": cli_plan_store, "allowed_roots": cli_roots, "enable_open_item": config.enable_open_item}),
            (BrowseWebPlugin, {}),
            (SearchFilesPlugin, {"allowed_roots": cli_roots, "search_scan_limit": max(200, int(config.search_scan_limit))}),
        ]:
            try:
                cli_plugins.append(pcls(**pkw))
            except Exception as exc:
                logger.error("Failed to create CLI plugin %s: %s", pcls.__name__, exc)

        tool_executor = ToolExecutor(plugins=cli_plugins)
        logger.debug("Tool executor initialized")
    except Exception as e:
        print_error(f"Tool executor initialization failed: {e}", no_color)
        return EXIT_CONFIG_ERROR
    
    # Step 3: Initialize audit logger
    try:
        audit_logger = AuditLogger(config.audit_log_path)
        audit_include_prompt = bool(getattr(config, "audit_include_prompt", False))
        startup_payload: dict[str, object] = {
            "model": config.model_name or "<auto-resolve-from-live-catalog>",
            "tools_count": len(tools),
            "mode": "cli",
            "prompt_present": bool(parsed_args.prompt),
            "prompt_chars": len(parsed_args.prompt),
        }
        if audit_include_prompt:
            startup_payload["prompt"] = parsed_args.prompt
        audit_logger.log_event(EventType.STARTUP, startup_payload)
        logger.debug("Audit logger initialized")
    except AuditLogError as e:
        print_error(f"Audit logging initialization failed: {e}", no_color)
        return EXIT_CONFIG_ERROR
    
    # Step 4: Initialize Gemini client and send prompt
    try:
        client = GeminiClient(
            api_key=config.gemini_api_key,
            model_name=config.model_name,
            max_retries=config.max_retries,
            retry_delay=config.retry_delay,
            require_no_training=config.require_no_training,
            use_vertexai=config.use_vertexai,
            vertex_project=config.vertex_project,
            vertex_location=config.vertex_location,
        )
        config.model_name = client.resolve_text_model(config.model_name or None)
        logger.debug("Gemini client initialized")

        # Wire semantic embedding service (second init site — CLI mode)
        try:
            embedding_client = getattr(client, "_client", client)
            embedding_service = EmbeddingService(embedding_client)
            memory_manager.set_embedding_service(embedding_service)
            logger.debug("Semantic embedding service initialized")
        except Exception as e:
            print_error(f"Embedding service initialization failed: {e}", no_color)
            if audit_logger:
                audit_logger.log_error("EMBEDDING_INIT_ERROR", str(e))
            return EXIT_CONFIG_ERROR

        base_system_instruction = build_system_prompt(tools)
        system_instruction = inject_model_identity(
            base_system_instruction, config.model_name
        )
        logger.debug(
            "System prompt loaded (%s chars, %s tools injected)",
            len(system_instruction),
            len(tools),
        )
        
        cli_session_id = os.environ.get("AI_AGENT_SESSION_ID", "cli-default")
        cli_memory_mode = _parse_memory_mode(os.environ.get("AI_AGENT_MEMORY_MODE"))
        prepared = memory_manager.prepare_prompt_context(
            session_id=cli_session_id,
            prompt=parsed_args.prompt,
            memory_mode=cli_memory_mode,
        )

        response = client.send_prompt_with_tools(
            prompt=prepared.augmented_prompt,
            tools=tools,
            system_instruction=system_instruction,
        )
        logger.debug("Received response from Gemini")
        
    except GeminiRateLimitError as e:
        print_error(f"Rate limit exceeded: {e}", no_color)
        if audit_logger:
            audit_logger.log_error("RATE_LIMIT", str(e))
        return EXIT_API_ERROR
    except GeminiServerError as e:
        print_error(f"Server error: {e}", no_color)
        if audit_logger:
            audit_logger.log_error("SERVER_ERROR", str(e))
        return EXIT_API_ERROR
    except GeminiAPIError as e:
        print_error(f"API error: {e}", no_color)
        if audit_logger:
            audit_logger.log_error("API_ERROR", str(e))
        return EXIT_API_ERROR
    except GeminiClientError as e:
        print_error(f"Client error: {e}", no_color)
        if audit_logger:
            audit_logger.log_error("CLIENT_ERROR", str(e))
        return EXIT_API_ERROR
    except SystemPromptLoadError as e:
        print_error(f"System prompt load error: {e}", no_color)
        if audit_logger:
            audit_logger.log_error("PROMPT_LOAD_ERROR", str(e))
        return EXIT_CONFIG_ERROR
    
    # Step 5: Parse response for function call
    parser_instance = ToolCallParser()
    
    try:
        tool_call = parser_instance.parse_response(response)
    except MalformedResponseError as e:
        print_error(f"Failed to parse response: {e}", no_color)
        if audit_logger:
            audit_logger.log_error("PARSE_ERROR", str(e))
        return EXIT_VALIDATION_ERROR
    
    if tool_call is None:
        # No function call in response - might be a text response
        if response.get("text"):
            raw_text = str(response["text"])
            rendered_text = (
                sanitize_user_visible_response(raw_text)
                if looks_like_json_payload(raw_text)
                else raw_text
            )
            memory_manager.record_interaction(
                session_id=cli_session_id,
                memory_mode=cli_memory_mode,
                user_prompt=parsed_args.prompt,
                assistant_response=rendered_text,
                model_name=config.model_name,
            )
            print_info("Gemini responded with text instead of a tool call:", no_color)
            print(rendered_text)
            if audit_logger:
                audit_logger.log_event(EventType.API_RESPONSE, {
                    "type": "text",
                    "text": rendered_text[:500],  # Truncate for log
                })
            return EXIT_SUCCESS
        else:
            print_error("No tool call or text response received", no_color)
            if audit_logger:
                audit_logger.log_error("NO_RESPONSE", "Empty response from Gemini")
            return EXIT_VALIDATION_ERROR
    
    # Step 6: Validate tool call against schema
    try:
        validator.validate_tool_call(tool_call.name, tool_call.arguments)
        logger.debug(f"Validation passed for tool: {tool_call.name}")
    except SchemaNotFoundError as e:
        print_error(f"Unknown tool: {e}", no_color)
        if audit_logger:
            audit_logger.log_error("UNKNOWN_TOOL", str(e), {
                "tool": tool_call.name,
                "arguments": tool_call.arguments,
            })
        return EXIT_VALIDATION_ERROR
    except ValidationFailedError as e:
        print_error(f"Validation failed: {e}", no_color)
        if audit_logger:
            audit_logger.log_validation_fail(
                tool_call.name,
                tool_call.arguments,
                e.errors,
            )
        return EXIT_VALIDATION_ERROR
    
    # Step 7: Log to audit log
    if audit_logger:
        audit_include_prompt = bool(getattr(config, "audit_include_prompt", False))
        audit_logger.log_tool_call(
            tool_name=tool_call.name,
            arguments=tool_call.arguments,
            user_prompt=parsed_args.prompt if audit_include_prompt else None,
            validated=True,
        )

    # Step 8: Execute tool call
    try:
        execution = tool_executor.execute(tool_call.name, tool_call.arguments)
    except ToolExecutionError as e:
        message = str(e)
        print_error(f"Tool execution failed: {message}", no_color)
        if audit_logger:
            audit_logger.log_error(
                "TOOL_EXECUTION_FAILED",
                message,
                {
                    "tool": tool_call.name,
                    "arguments": tool_call.arguments,
                },
            )
        memory_manager.record_interaction(
            session_id=cli_session_id,
            memory_mode=cli_memory_mode,
            user_prompt=parsed_args.prompt,
            assistant_response=f"Tool execution failed: {message}",
            model_name=config.model_name,
        )
        return EXIT_VALIDATION_ERROR

    if audit_logger:
        tool_result_summary: dict[str, Any] = {
            "tool": tool_call.name,
            "ok": bool(execution.get("ok")) if isinstance(execution, dict) else True,
        }
        if isinstance(execution, dict):
            for key in (
                "url",
                "final_url",
                "error_class",
                "status_code",
                "redirect_count",
                "compliance_policy_version",
                "anti_bot_provider",
                "anti_bot_confidence",
            ):
                if key in execution:
                    tool_result_summary[key] = execution.get(key)
            if "security_checks" in execution:
                tool_result_summary["security_checks"] = execution.get("security_checks")
            if "prompt_injection_risk" in execution:
                risk = execution.get("prompt_injection_risk") or {}
                if isinstance(risk, dict):
                    tool_result_summary["prompt_injection_risk_level"] = risk.get("risk_level")
                    tool_result_summary["prompt_injection_risk_score"] = risk.get("risk_score")
        audit_logger.log_event(EventType.TOOL_RESULT, tool_result_summary)

    execution_text, _ = _format_tool_execution_output(tool_call.name, execution)
    execution_json = json.dumps(execution, ensure_ascii=False)
    memory_manager.record_interaction(
        session_id=cli_session_id,
        memory_mode=cli_memory_mode,
        user_prompt=parsed_args.prompt,
        assistant_response=execution_text,
        model_name=config.model_name,
    )

    # Step 9: Display results
    print_success(f"Tool call executed: {tool_call.name}", no_color)
    print()
    print("Tool: " + tool_call.name)
    print("Arguments:")
    print(json.dumps(tool_call.arguments, indent=2))
    print("Execution:")
    print(execution_text)
    if execution_text != execution_json:
        print()
        print("Execution (JSON):")
        print(json.dumps(execution, indent=2, ensure_ascii=False))
    
    return EXIT_SUCCESS if execution.get("ok") else EXIT_VALIDATION_ERROR


def cli_main() -> NoReturn:
    """Entry point for CLI that exits with appropriate code.
    
    This function is intended for use as a console script entry point.
    """
    sys.exit(main())


if __name__ == "__main__":
    cli_main()
