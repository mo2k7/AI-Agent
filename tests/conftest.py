"""Pytest configuration and shared fixtures."""
import os
import pytest
from pathlib import Path


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


@pytest.fixture(autouse=True)
def patch_secure_planner(monkeypatch):
    """Use a deterministic local planner stub in tests.

    Production still requires unified-planning; this patch is test-only to avoid
    external dependency installation in constrained CI/sandbox environments.
    """

    class _FakeUnifiedPlanner:
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

    monkeypatch.setattr(
        "agent_host.tools.executor.ToolExecutor._build_planner_engine",
        lambda self: _FakeUnifiedPlanner(),
    )
