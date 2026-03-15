"""Unit tests for IPC sliding-window rate limiter (Upgrade B)."""

from __future__ import annotations

from unittest.mock import patch

from agent_host.ipc.protocol import ErrorMessage
from agent_host.ipc.server import _SlidingWindowRateLimiter

import pytest


# ---------------------------------------------------------------------------
# 1. Requests under the limit are allowed
# ---------------------------------------------------------------------------


def test_allows_requests_under_limit() -> None:
    limiter = _SlidingWindowRateLimiter(max_requests=5, window_seconds=10)
    results = [limiter.check("c1", "prompt") for _ in range(5)]
    assert results == [True, True, True, True, True]


# ---------------------------------------------------------------------------
# 2. Requests over the limit are blocked
# ---------------------------------------------------------------------------


def test_blocks_request_over_limit() -> None:
    limiter = _SlidingWindowRateLimiter(max_requests=3, window_seconds=10)
    for _ in range(3):
        assert limiter.check("c1", "prompt") is True
    assert limiter.check("c1", "prompt") is False


# ---------------------------------------------------------------------------
# 3. Rate limiter recovers after the window elapses
# ---------------------------------------------------------------------------


def test_recovers_after_window_elapses() -> None:
    limiter = _SlidingWindowRateLimiter(max_requests=2, window_seconds=1)

    # Exhaust the limit at a known point in time.
    with patch("time.monotonic", return_value=100.0):
        assert limiter.check("c1", "prompt") is True
        assert limiter.check("c1", "prompt") is True
        assert limiter.check("c1", "prompt") is False

    # Advance time past the window — requests should be allowed again.
    with patch("time.monotonic", return_value=102.0):
        assert limiter.check("c1", "prompt") is True


# ---------------------------------------------------------------------------
# 4. Exempt methods bypass rate limiting
# ---------------------------------------------------------------------------


def test_exempt_methods_bypass() -> None:
    limiter = _SlidingWindowRateLimiter(max_requests=1, window_seconds=10)

    # Exhaust the single allowed request.
    assert limiter.check("c1", "prompt") is True
    assert limiter.check("c1", "prompt") is False

    # Exempt methods still pass.
    assert limiter.check("c1", "auth.hello") is True
    assert limiter.check("c1", "ping") is True


# ---------------------------------------------------------------------------
# 5. remove_client resets tracking state
# ---------------------------------------------------------------------------


def test_remove_client_cleans_state() -> None:
    limiter = _SlidingWindowRateLimiter(max_requests=2, window_seconds=10)

    assert limiter.check("c1", "prompt") is True
    assert limiter.check("c1", "prompt") is True
    assert limiter.check("c1", "prompt") is False

    limiter.remove_client("c1")

    # After removal the client starts with a fresh window.
    assert limiter.check("c1", "prompt") is True


# ---------------------------------------------------------------------------
# 6. ErrorMessage.RATE_LIMITED code value
# ---------------------------------------------------------------------------


def test_rate_limited_error_code() -> None:
    assert ErrorMessage.RATE_LIMITED == -32013


# ---------------------------------------------------------------------------
# 7. ErrorMessage.rate_limited() produces correct payload
# ---------------------------------------------------------------------------


def test_rate_limited_error_message() -> None:
    err = ErrorMessage.rate_limited("req-1", "too fast")
    assert err.error["code"] == -32013
    assert "Rate limited" in err.error["message"]
    assert "too fast" in err.error["message"]


# ---------------------------------------------------------------------------
# 8. Invalid constructor parameters raise ValueError
# ---------------------------------------------------------------------------


def test_invalid_params_raises_value_error() -> None:
    with pytest.raises(ValueError):
        _SlidingWindowRateLimiter(0, 10)
    with pytest.raises(ValueError):
        _SlidingWindowRateLimiter(5, 0)
