"""Tool execution runtime for validated tool calls."""

from __future__ import annotations

import logging
import time
from typing import Any, Mapping, Sequence

logger = logging.getLogger(__name__)


# Canonical definition in contracts/types/errors.py; re-exported for backward compat.
from agent_host.contracts.types.errors import ToolExecutionError  # noqa: F401


class ToolExecutor:
    """Executes tool plugins via a formal registry.

    All plugins are injected via the constructor or :meth:`register`.
    This class has **zero** imports from ``agent_host.adapters`` —
    plugin creation is the responsibility of the composition root
    (``main.py``).
    """

    # Rate limiting: token-bucket style per tool
    # Limits set very high so the model can call tools as many times as needed.
    _RATE_LIMIT_WINDOW_SECONDS = 60.0
    _RATE_LIMIT_MAX_CALLS: dict[str, int] = {
        "search_files": 999999,
        "apply_ops": 999999,
        "planner": 999999,
        "plan_ops": 999999,
        "open_item": 999999,
        "create_directory": 999999,
        "read_document": 999999,
        "browse_web": 999999,
    }

    def __init__(
        self,
        *,
        plugins: Sequence[Any] = (),
        event_bus: Any | None = None,
    ) -> None:
        self._plugins: dict[str, Any] = {}
        self._event_bus = event_bus
        # Rate limiting state: tool_name -> list of call timestamps
        self._rate_limit_calls: dict[str, list[float]] = {}
        # Register each plugin with validation
        for plugin in plugins:
            self.register(plugin)

    # ------------------------------------------------------------------
    # Registry API
    # ------------------------------------------------------------------

    def register(self, plugin: Any) -> None:
        """Register a plugin.  Validates protocol conformance."""
        from agent_host.contracts.ports.tool import ToolPlugin

        if not isinstance(plugin, ToolPlugin):
            logger.warning(
                "Plugin %r does not satisfy ToolPlugin protocol, skipping",
                plugin,
            )
            return
        name = plugin.name
        if name in self._plugins:
            logger.warning("Overwriting plugin '%s'", name)
        self._plugins[name] = plugin
        logger.info("Registered plugin: %s", name)

    def unregister(self, name: str) -> bool:
        """Remove a plugin by name.  Returns True if it existed."""
        return self._plugins.pop(name, None) is not None

    def get(self, name: str) -> Any | None:
        """Look up a registered plugin by name."""
        return self._plugins.get(name)

    def list_plugins(self) -> list[str]:
        """Return the names of all registered plugins."""
        return list(self._plugins.keys())

    def get_health_status(self) -> dict[str, dict[str, Any]]:
        """Run health_check on every plugin and return a summary."""
        from agent_host.contracts.types.result import Success

        status: dict[str, dict[str, Any]] = {}
        for name, plugin in self._plugins.items():
            try:
                result = plugin.health_check()
                status[name] = {"ok": isinstance(result, Success), "error": None}
            except Exception as exc:
                status[name] = {"ok": False, "error": str(exc)}
        return status

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def _check_rate_limit(self, tool_name: str) -> None:
        """Enforce per-tool rate limiting using a sliding window."""
        max_calls = self._RATE_LIMIT_MAX_CALLS.get(tool_name)
        if max_calls is None:
            return
        now = time.time()
        window_start = now - self._RATE_LIMIT_WINDOW_SECONDS
        calls = self._rate_limit_calls.setdefault(tool_name, [])
        # Prune old entries
        calls[:] = [ts for ts in calls if ts > window_start]
        if len(calls) >= max_calls:
            raise ToolExecutionError(
                f"Rate limit exceeded for '{tool_name}': max {max_calls} calls "
                f"per {int(self._RATE_LIMIT_WINDOW_SECONDS)}s window"
            )
        calls.append(now)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self, tool_name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        plugin = self.get(tool_name)
        if plugin is None:
            raise ToolExecutionError(f"Unsupported tool: {tool_name}", error_type="not_found")
        if not isinstance(arguments, Mapping):
            raise ToolExecutionError(f"Tool '{tool_name}' arguments must be an object", error_type="validation")

        # Rate limiting
        self._check_rate_limit(tool_name)

        started_at = time.time()
        started_perf = time.perf_counter()

        if self._event_bus:
            from agent_host.contracts.types.events import ToolExecutionStarted
            self._event_bus.publish(ToolExecutionStarted(
                event_type="tool.execution.started",
                source="tool_executor",
                payload={"tool": tool_name},
            ))

        try:
            result = plugin.execute(arguments)
        except ToolExecutionError:
            if self._event_bus:
                from agent_host.contracts.types.events import ToolExecutionCompleted
                latency_ms = max(0.0, (time.perf_counter() - started_perf) * 1000.0)
                self._event_bus.publish(ToolExecutionCompleted(
                    event_type="tool.execution.completed",
                    source="tool_executor",
                    payload={
                        "tool": tool_name,
                        "ok": False,
                        "latency_ms": round(latency_ms, 3),
                    },
                ))
            raise
        except Exception as exc:  # pragma: no cover - defensive wrapper
            if self._event_bus:
                from agent_host.contracts.types.events import ToolExecutionCompleted
                latency_ms = max(0.0, (time.perf_counter() - started_perf) * 1000.0)
                self._event_bus.publish(ToolExecutionCompleted(
                    event_type="tool.execution.completed",
                    source="tool_executor",
                    payload={
                        "tool": tool_name,
                        "ok": False,
                        "latency_ms": round(latency_ms, 3),
                    },
                ))
            raise ToolExecutionError(self._format_unexpected_tool_error(tool_name, exc)) from exc

        # Unwrap Result type from plugin.
        from agent_host.contracts.types.result import Failure
        if isinstance(result, Failure):
            err = result.error
            if self._event_bus:
                from agent_host.contracts.types.events import ToolExecutionCompleted
                latency_ms = max(0.0, (time.perf_counter() - started_perf) * 1000.0)
                self._event_bus.publish(ToolExecutionCompleted(
                    event_type="tool.execution.completed",
                    source="tool_executor",
                    payload={
                        "tool": tool_name,
                        "ok": False,
                        "latency_ms": round(latency_ms, 3),
                    },
                ))
            raise ToolExecutionError(
                err.message if hasattr(err, "message") else str(err),
                error_type=err.code.value if hasattr(err, "code") else "internal",
                retryable=getattr(err, "retryable", False),
            )
        output = result.value if hasattr(result, "value") else result

        if not isinstance(output, Mapping):
            raise ToolExecutionError(f"Tool '{tool_name}' returned invalid output payload")

        finished_at = time.time()
        latency_ms = max(0.0, (time.perf_counter() - started_perf) * 1000.0)
        output_payload = dict(output)

        if self._event_bus:
            from agent_host.contracts.types.events import ToolExecutionCompleted
            self._event_bus.publish(ToolExecutionCompleted(
                event_type="tool.execution.completed",
                source="tool_executor",
                payload={
                    "tool": tool_name,
                    "ok": bool(output_payload.get("ok", True)),
                    "latency_ms": round(latency_ms, 3),
                },
            ))

        return {
            "tool": tool_name,
            "ok": bool(output_payload.get("ok", True)),
            "timestamp": finished_at,
            "started_at": started_at,
            "finished_at": finished_at,
            "latency_ms": round(latency_ms, 3),
            "output": output_payload,
        }

    @staticmethod
    def _format_unexpected_tool_error(tool_name: str, exc: BaseException) -> str:
        detail = str(exc).strip()
        if detail:
            return f"Tool '{tool_name}' failed with {exc.__class__.__name__}: {detail}"
        return f"Tool '{tool_name}' failed with {exc.__class__.__name__}"
