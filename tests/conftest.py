"""Pytest configuration and shared fixtures."""
from __future__ import annotations

from pathlib import Path
import pytest


@pytest.fixture
def schemas_dir() -> Path:
    """Return path to schemas directory."""
    return Path(__file__).parent.parent / "schemas"


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to golden test fixtures."""
    return Path(__file__).parent / "golden" / "fixtures"


@pytest.fixture
def mock_api_key() -> str:
    """Return a mock API key for testing."""
    return "test-api-key-12345"


@pytest.fixture(autouse=True)
def env_setup(monkeypatch, mock_api_key):
    """Set up environment variables for tests."""
    monkeypatch.setenv("GOOGLE_API_KEY", mock_api_key)
    monkeypatch.setenv("AI_AGENT_ENV", "test")
    monkeypatch.setenv("AI_AGENT_IPC_AUTH_TOKEN", "test-ipc-auth-token")


@pytest.fixture(autouse=True)
def patch_memory_keychain(monkeypatch):
    """Inject deterministic key material for tests without env fallback."""
    monkeypatch.setattr("agent_host.memory.keychain._load_from_keychain", lambda: b"k" * 32)


class FakeUnifiedPlanner:
    """Deterministic planner stub used in tests.

    Replaces the real UnifiedPlanningEngine so tests don't need the
    ``unified-planning`` package installed.
    """

    version = "test-stub"
    policy_checksum = "test-policy-checksum"
    policy_attestation_verified = True
    package_hash = "test-package-hash"
    package_hash_verified = True
    package_hash_pinned = False
    package_hash_auto_rotate_enabled = False

    def analyze_complexity(self, *, steps, dependency_count):
        op_count = len(steps) if isinstance(steps, list) else 0
        score = op_count + int(dependency_count)
        if score <= 3:
            level = "low"
            strategy = "linear"
        elif score <= 8:
            level = "medium"
            strategy = "dependency_ordered"
        else:
            level = "high"
            strategy = "risk_first_structured"
        return {
            "score": score,
            "level": level,
            "strategy": strategy,
            "factors": {
                "op_count": op_count,
                "destructive_op_count": 0,
                "invalid_op_count": 0,
                "dependency_count": int(dependency_count),
            },
        }

    def plan_order(self, *, step_count, dependencies):
        _ = dependencies
        return {
            "engine": "unified-planning",
            "engine_version": self.version,
            "engine_name": "test-stub",
            "status": "SOLVED_SATISFICING",
            "ordered_indices": list(range(int(step_count))),
        }


@pytest.fixture(autouse=True)
def patch_secure_planner(monkeypatch):
    """Use a deterministic local planner stub in tests.

    Production still requires unified-planning; this patch is test-only to avoid
    external dependency installation in constrained CI/sandbox environments.

    Since ToolExecutor now receives plugins via DI (no internal
    ``_build_planner_engine``), this fixture patches the
    ``UnifiedPlanningEngine`` class itself so any code that instantiates
    it (including test helpers that build plugins) gets the fake.
    """
    monkeypatch.setattr(
        "agent_host.planning.UnifiedPlanningEngine",
        FakeUnifiedPlanner,
    )


def build_tool_executor(
    tmp_path: Path,
    *,
    enable_open_item: bool = False,
    search_scan_limit: int = 5000,
    event_bus=None,
):
    """Create a ToolExecutor with proper DI plugin construction.

    Shared helper for all test files that need a working executor.
    """
    from agent_host.adapters.tools.create_directory import CreateDirectoryPlugin
    from agent_host.adapters.tools.open_item import OpenItemPlugin
    from agent_host.adapters.tools.read_document import ReadDocumentPlugin
    from agent_host.adapters.tools.planner import PlannerPlugin
    from agent_host.adapters.tools.plan_ops import PlanOpsPlugin
    from agent_host.adapters.tools.apply_ops import ApplyOpsPlugin
    from agent_host.adapters.tools.browse_web import BrowseWebPlugin
    from agent_host.adapters.tools.search_files import SearchFilesPlugin
    from agent_host.adapters.storage.in_memory_plan_store import InMemoryPlanStore
    from agent_host.tools.executor import ToolExecutor

    planner_engine = FakeUnifiedPlanner()
    plan_store = InMemoryPlanStore()
    roots_list = [tmp_path.resolve()]

    plugins = [
        CreateDirectoryPlugin(allowed_roots=roots_list),
        OpenItemPlugin(allowed_roots=roots_list, enable=enable_open_item),
        ReadDocumentPlugin(allowed_roots=roots_list),
        PlannerPlugin(planner_engine=planner_engine, plan_store=plan_store, allowed_roots=roots_list),
        PlanOpsPlugin(planner_engine=planner_engine, plan_store=plan_store, allowed_roots=roots_list),
        ApplyOpsPlugin(plan_store=plan_store, allowed_roots=roots_list, enable_open_item=enable_open_item),
        BrowseWebPlugin(),
        SearchFilesPlugin(allowed_roots=roots_list, search_scan_limit=max(200, search_scan_limit)),
    ]

    return ToolExecutor(plugins=plugins, event_bus=event_bus)
