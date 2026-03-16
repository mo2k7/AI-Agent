"""Architectural boundary enforcement tests.

These tests verify the concentric ring dependency rules:
- Ring 1 (contracts/): ZERO imports from any other ring
- Ring 2 (core/): imports ONLY from contracts/
- Ring 3 (adapters/): imports from contracts/ and existing infrastructure,
  but NOT from sibling adapter packages
- Ring 4 (main.py): may import from everything

Also verifies protocol conformance and structural invariants that
prevent integration errors when scaling.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# Project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AGENT_HOST = PROJECT_ROOT / "agent_host"


def _get_python_files(directory: Path) -> list[Path]:
    """Collect all .py files in a directory tree."""
    return [f for f in directory.rglob("*.py") if "__pycache__" not in str(f)]


def _extract_imports(filepath: Path) -> list[str]:
    """Extract all import module paths from a Python file."""
    try:
        source = filepath.read_text()
        tree = ast.parse(source)
    except SyntaxError:
        return []
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.append(node.module)
    return modules


# =========================================================================
# Ring 1: Contracts — ZERO external imports
# =========================================================================


class TestContractsImportRules:
    """Contracts layer must not import from core/, adapters/, or main.py."""

    def test_no_imports_from_outer_rings(self):
        violations = []
        for filepath in _get_python_files(AGENT_HOST / "contracts"):
            for mod in _extract_imports(filepath):
                if mod.startswith("agent_host.") and not mod.startswith("agent_host.contracts"):
                    rel = filepath.relative_to(AGENT_HOST / "contracts")
                    violations.append(f"{rel} imports {mod}")
        assert violations == [], f"Contracts import violations:\n" + "\n".join(violations)

    def test_no_external_framework_imports(self):
        forbidden = {"google", "spacy", "bs4", "beautifulsoup4", "websockets", "cryptography", "httpx"}
        violations = []
        for filepath in _get_python_files(AGENT_HOST / "contracts"):
            for mod in _extract_imports(filepath):
                if mod.split(".")[0] in forbidden:
                    rel = filepath.relative_to(AGENT_HOST / "contracts")
                    violations.append(f"{rel} imports {mod}")
        assert violations == [], f"Framework import violations:\n" + "\n".join(violations)


# =========================================================================
# Ring 2: Core — imports only from contracts/
# =========================================================================


class TestCoreImportRules:
    """Core layer may import from contracts/, but NOT from adapters/ or main.py.

    All core→adapter imports have been eliminated via dependency injection:
    - orchestrator.py was fixed by F2 (mode_handler_factory + plan_mode_ops DI).
    - handlers/infrastructure.py was fixed by FIX-A (normalize_path_fn DI).
    """

    # Files with known adapter imports (documented trade-offs).
    # All resolved — core/ has ZERO adapter imports.
    _KNOWN_EXCEPTIONS: set[str] = set()

    def test_no_unexpected_imports_from_adapters(self):
        violations = []
        for filepath in _get_python_files(AGENT_HOST / "core"):
            rel = str(filepath.relative_to(AGENT_HOST / "core"))
            if any(rel.endswith(exc) or rel == exc for exc in self._KNOWN_EXCEPTIONS):
                continue
            for mod in _extract_imports(filepath):
                if mod.startswith("agent_host.adapters"):
                    violations.append(f"{rel} imports {mod}")
        assert violations == [], f"Core→Adapters violations:\n" + "\n".join(violations)

    def test_known_exceptions_are_documented(self):
        """Verify that ONLY the known files import from adapters (no silent growth)."""
        adapter_importers = set()
        for filepath in _get_python_files(AGENT_HOST / "core"):
            rel = str(filepath.relative_to(AGENT_HOST / "core"))
            for mod in _extract_imports(filepath):
                if mod.startswith("agent_host.adapters"):
                    adapter_importers.add(rel)
                    break
        unexpected = adapter_importers - self._KNOWN_EXCEPTIONS
        assert unexpected == set(), (
            f"New core/ files import from adapters/ without documentation: {unexpected}. "
            f"Add to _KNOWN_EXCEPTIONS with justification or fix the import."
        )

    def test_no_imports_from_main(self):
        violations = []
        for filepath in _get_python_files(AGENT_HOST / "core"):
            for mod in _extract_imports(filepath):
                if mod == "agent_host.main":
                    rel = filepath.relative_to(AGENT_HOST / "core")
                    violations.append(f"{rel} imports {mod}")
        assert violations == [], f"Core→main violations:\n" + "\n".join(violations)

    def test_core_no_infrastructure_imports(self):
        """Core must not import from infrastructure modules (ipc, memory, tools).

        Exceptions are documented in _INFRA_ALLOWED_EXCEPTIONS as
        ``(relative_filename, module_prefix)`` tuples.  Each exception
        represents a deliberate utility import that is not worth abstracting
        behind a port.
        """
        FORBIDDEN_PREFIXES = (
            "agent_host.ipc",
            "agent_host.memory",
            "agent_host.tools",
        )
        # Documented utility exceptions -- lazy runtime imports that
        # do NOT create hard module-level coupling.
        ALLOWED = {
            # DeviceToolRouter is lazy-imported inside a runtime branch
            ("orchestrator.py", "agent_host.ipc.device_tool_router"),
        }
        violations = []
        for filepath in _get_python_files(AGENT_HOST / "core"):
            rel = filepath.name
            for mod in _extract_imports(filepath):
                if any(mod.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
                    if (rel, mod) not in ALLOWED:
                        full_rel = str(filepath.relative_to(AGENT_HOST / "core"))
                        violations.append(f"{full_rel} imports {mod}")
        assert violations == [], (
            "Core has forbidden infrastructure imports:\n" + "\n".join(violations)
        )


# =========================================================================
# Ring 3: Adapters — no cross-adapter imports
# =========================================================================


class TestAdaptersImportRules:
    """No adapter package may import from a sibling adapter package."""

    def _adapter_packages(self) -> list[str]:
        """List top-level adapter package names (tools, modes, llm, etc.)."""
        adapters_dir = AGENT_HOST / "adapters"
        return [
            d.name for d in adapters_dir.iterdir()
            if d.is_dir() and not d.name.startswith("_") and d.name != "__pycache__"
        ]

    def test_no_cross_adapter_imports(self):
        """e.g., adapters/tools/ must NOT import from adapters/modes/."""
        adapters_dir = AGENT_HOST / "adapters"
        violations = []
        for pkg_name in self._adapter_packages():
            pkg_dir = adapters_dir / pkg_name
            for filepath in _get_python_files(pkg_dir):
                for mod in _extract_imports(filepath):
                    if not mod.startswith("agent_host.adapters"):
                        continue
                    # Extract the adapter sub-package name from the import
                    parts = mod.split(".")
                    # agent_host.adapters.<sub_package>...
                    if len(parts) >= 3:
                        imported_pkg = parts[2]
                        if imported_pkg != pkg_name and imported_pkg != "__init__":
                            rel = filepath.relative_to(pkg_dir)
                            violations.append(
                                f"adapters/{pkg_name}/{rel} imports from adapters/{imported_pkg} ({mod})"
                            )
        assert violations == [], f"Cross-adapter violations:\n" + "\n".join(violations)

    def test_no_imports_from_main(self):
        """Adapters must not import from main.py."""
        violations = []
        for filepath in _get_python_files(AGENT_HOST / "adapters"):
            for mod in _extract_imports(filepath):
                if mod == "agent_host.main":
                    rel = filepath.relative_to(AGENT_HOST / "adapters")
                    violations.append(f"{rel} imports {mod}")
        assert violations == [], f"Adapters→main violations:\n" + "\n".join(violations)


# =========================================================================
# Plugin protocol conformance
# =========================================================================


class TestPluginProtocolConformance:
    """All tool plugins registered in ToolExecutor must satisfy ToolPlugin."""

    def test_all_sync_plugins_satisfy_protocol(self, tmp_path):
        from agent_host.contracts.ports.tool import ToolPlugin
        from tests.conftest import build_tool_executor

        executor = build_tool_executor(tmp_path, search_scan_limit=200)

        plugin_names = executor.list_plugins()
        assert len(plugin_names) >= 8, (
            f"Expected at least 8 plugins, got {len(plugin_names)}"
        )
        for name in plugin_names:
            plugin = executor.get(name)
            assert isinstance(plugin, ToolPlugin), (
                f"Plugin '{name}' ({type(plugin).__name__}) does not satisfy ToolPlugin protocol"
            )
            assert plugin.name == name, (
                f"Plugin registered as '{name}' but reports name '{plugin.name}'"
            )

    def test_all_plugins_have_health_check(self, tmp_path):
        from tests.conftest import build_tool_executor

        executor = build_tool_executor(tmp_path, search_scan_limit=200)

        for name in executor.list_plugins():
            plugin = executor.get(name)
            result = plugin.health_check()
            assert result.is_ok, (
                f"Plugin '{name}' health_check failed: {result}"
            )


# =========================================================================
# Adapter protocol conformance
# =========================================================================


class TestAdapterProtocolConformance:
    """All adapters must satisfy their port protocols."""

    def test_gemini_adapter_satisfies_llm_provider(self):
        from agent_host.contracts.ports import LLMProvider
        from agent_host.adapters.llm import GeminiAdapter
        from unittest.mock import MagicMock

        mock = MagicMock()
        mock.model_name = "test"
        assert isinstance(GeminiAdapter(mock), LLMProvider)

    def test_memory_adapter_satisfies_memory_port(self):
        from agent_host.contracts.ports import MemoryPort
        from agent_host.adapters.storage.memory_adapter import MemoryAdapter
        from unittest.mock import MagicMock

        assert isinstance(MemoryAdapter(MagicMock()), MemoryPort)

    def test_audit_adapter_satisfies_audit_port(self):
        from agent_host.contracts.ports import AuditPort
        from agent_host.adapters.audit import AuditAdapter
        from unittest.mock import MagicMock

        assert isinstance(AuditAdapter(MagicMock()), AuditPort)

    def test_spacy_adapter_satisfies_nlp_port(self):
        from agent_host.contracts.ports import NLPClassifierPort
        from agent_host.adapters.nlp import SpacyNLPAdapter
        from unittest.mock import MagicMock

        assert isinstance(SpacyNLPAdapter(MagicMock()), NLPClassifierPort)

    def test_websocket_adapter_satisfies_ipc_port(self):
        from agent_host.contracts.ports import IPCPort
        from agent_host.adapters.ipc import WebSocketAdapter
        from unittest.mock import MagicMock

        mock = MagicMock()
        assert isinstance(WebSocketAdapter(mock), IPCPort)

    def test_event_bus_satisfies_protocol(self):
        from agent_host.contracts.ports import EventBus
        from agent_host.adapters.event_bus import InMemoryEventBus

        assert isinstance(InMemoryEventBus(), EventBus)

    def test_plan_store_satisfies_protocol(self):
        from agent_host.contracts.ports import PlanStore
        from agent_host.adapters.storage.in_memory_plan_store import InMemoryPlanStore

        assert isinstance(InMemoryPlanStore(), PlanStore)


# =========================================================================
# Structural invariants
# =========================================================================


class TestStructuralInvariants:
    """Verify structural properties that prevent scaling errors."""

    def test_every_adapter_tool_has_init_and_plugin(self):
        """Every adapter tool folder must have __init__.py and plugin.py."""
        tools_dir = AGENT_HOST / "adapters" / "tools"
        tool_dirs = [
            d for d in tools_dir.iterdir()
            if d.is_dir()
            and not d.name.startswith("_")
            and d.name != "__pycache__"
        ]
        assert len(tool_dirs) >= 8, f"Expected at least 8 tool dirs, got {len(tool_dirs)}"
        for tool_dir in tool_dirs:
            assert (tool_dir / "__init__.py").exists(), (
                f"Missing __init__.py in {tool_dir.name}/"
            )
            assert (tool_dir / "plugin.py").exists() or (tool_dir / "handler.py").exists(), (
                f"Missing plugin.py or handler.py in {tool_dir.name}/"
            )

    def test_every_adapter_mode_has_init_and_handler(self):
        """Every adapter mode folder must have __init__.py and handler.py."""
        modes_dir = AGENT_HOST / "adapters" / "modes"
        mode_dirs = [
            d for d in modes_dir.iterdir()
            if d.is_dir()
            and not d.name.startswith("_")
            and d.name != "__pycache__"
        ]
        assert len(mode_dirs) == 3, f"Expected 3 mode dirs, got {len(mode_dirs)}"
        for mode_dir in mode_dirs:
            assert (mode_dir / "__init__.py").exists(), (
                f"Missing __init__.py in {mode_dir.name}/"
            )
            assert (mode_dir / "handler.py").exists(), (
                f"Missing handler.py in {mode_dir.name}/"
            )

    def test_no_module_level_mutable_state_in_registry(self):
        """registry.py must not have module-level mutable dicts."""
        registry_path = AGENT_HOST / "tools" / "registry.py"
        source = registry_path.read_text()
        # Check for the old patterns
        assert "_NOTE_HANDLERS:" not in source, (
            "registry.py still has _NOTE_HANDLERS mutable state"
        )
        assert "_SCREEN_HANDLER:" not in source, (
            "registry.py still has _SCREEN_HANDLER mutable state"
        )
        # dispatch functions should be gone
        assert "async def dispatch_note_tool" not in source
        assert "async def dispatch_screen_tool" not in source

    def test_main_py_line_count_under_threshold(self):
        """main.py should stay compact — alert if it grows beyond 1500 lines."""
        main_path = AGENT_HOST / "main.py"
        line_count = len(main_path.read_text().splitlines())
        assert line_count < 1500, (
            f"main.py has grown to {line_count} lines — "
            f"consider extracting more code to core/ or adapters/"
        )
