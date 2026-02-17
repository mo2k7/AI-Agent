"""Tests for defensive environment variable parsing in store.py and server.py.

Validates that non-numeric env var values fall back to defaults rather than
crashing with ValueError (BUGs 42-44).
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# store.py helpers
# ---------------------------------------------------------------------------


class TestStoreSafeInt:
    """agent_host.memory.store._safe_int"""

    def test_valid_integer(self) -> None:
        from agent_host.memory.store import _safe_int

        assert _safe_int("42", 0) == 42

    def test_negative_integer(self) -> None:
        from agent_host.memory.store import _safe_int

        assert _safe_int("-3", 0) == -3

    def test_non_numeric_returns_default(self) -> None:
        from agent_host.memory.store import _safe_int

        assert _safe_int("notanumber", 5) == 5

    def test_empty_string_returns_default(self) -> None:
        from agent_host.memory.store import _safe_int

        assert _safe_int("", 10) == 10

    def test_float_string_returns_default(self) -> None:
        from agent_host.memory.store import _safe_int

        assert _safe_int("3.14", 7) == 7

    def test_none_returns_default(self) -> None:
        from agent_host.memory.store import _safe_int

        # os.environ.get() with missing key returns default str, but if
        # someone passes None explicitly it should still be safe.
        assert _safe_int(None, 99) == 99  # type: ignore[arg-type]


class TestStoreSafeFloat:
    """agent_host.memory.store._safe_float"""

    def test_valid_float(self) -> None:
        from agent_host.memory.store import _safe_float

        assert _safe_float("3.14", 0.0) == pytest.approx(3.14)

    def test_integer_string(self) -> None:
        from agent_host.memory.store import _safe_float

        assert _safe_float("20", 0.0) == pytest.approx(20.0)

    def test_non_numeric_returns_default(self) -> None:
        from agent_host.memory.store import _safe_float

        assert _safe_float("abc", 5.0) == pytest.approx(5.0)

    def test_empty_string_returns_default(self) -> None:
        from agent_host.memory.store import _safe_float

        assert _safe_float("", 1.5) == pytest.approx(1.5)

    def test_none_returns_default(self) -> None:
        from agent_host.memory.store import _safe_float

        assert _safe_float(None, 9.9) == pytest.approx(9.9)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# server.py helper
# ---------------------------------------------------------------------------


class TestServerSafeEnvInt:
    """agent_host.ipc.server._safe_env_int"""

    def test_valid_value(self) -> None:
        from agent_host.ipc.server import _safe_env_int

        with patch.dict(os.environ, {"_TEST_INT_VAR": "8192"}):
            assert _safe_env_int("_TEST_INT_VAR", 4096) == 8192

    def test_missing_key_returns_default(self) -> None:
        from agent_host.ipc.server import _safe_env_int

        env = os.environ.copy()
        env.pop("_TEST_INT_MISSING", None)
        with patch.dict(os.environ, env, clear=True):
            assert _safe_env_int("_TEST_INT_MISSING", 4096) == 4096

    def test_non_numeric_returns_default(self) -> None:
        from agent_host.ipc.server import _safe_env_int

        with patch.dict(os.environ, {"_TEST_INT_VAR": "garbage"}):
            assert _safe_env_int("_TEST_INT_VAR", 4096) == 4096

    def test_empty_value_returns_default(self) -> None:
        from agent_host.ipc.server import _safe_env_int

        with patch.dict(os.environ, {"_TEST_INT_VAR": "  "}):
            assert _safe_env_int("_TEST_INT_VAR", 4096) == 4096


# ---------------------------------------------------------------------------
# Integration: class-level attributes don't crash on bad env
# ---------------------------------------------------------------------------


class TestInstrumentedConnectionDefaults:
    """Verify _InstrumentedConnection class attributes are safe."""

    def test_default_retry_attempts(self) -> None:
        from agent_host.memory.store import _InstrumentedConnection

        assert isinstance(_InstrumentedConnection._retry_attempts, int)
        assert _InstrumentedConnection._retry_attempts >= 0

    def test_default_retry_delay(self) -> None:
        from agent_host.memory.store import _InstrumentedConnection

        assert isinstance(_InstrumentedConnection._retry_delay_seconds, float)
        assert _InstrumentedConnection._retry_delay_seconds >= 0.0
