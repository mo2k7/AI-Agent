"""Unit tests for IPC auth rotation token lifecycle (Upgrade A)."""

from __future__ import annotations

import time

import pytest

from agent_host.ipc.server import IPCServer


def _build_server(tmp_path) -> IPCServer:
    del tmp_path
    return IPCServer(
        require_auth=True,
        auth_token="test-token",
    )


# ---------------------------------------------------------------------------
# 1. Token generation returns a non-empty string
# ---------------------------------------------------------------------------


def test_generate_rotation_token_returns_string(tmp_path) -> None:
    server = _build_server(tmp_path)
    token = server._generate_rotation_token("c1")
    assert isinstance(token, str)
    assert len(token) > 0


# ---------------------------------------------------------------------------
# 2. Generated token can be consumed successfully
# ---------------------------------------------------------------------------


def test_consume_rotation_token_succeeds(tmp_path) -> None:
    server = _build_server(tmp_path)
    token = server._generate_rotation_token("c1")
    client_id = server._consume_rotation_token(token)
    assert client_id == "c1"


# ---------------------------------------------------------------------------
# 3. Rotation token is single-use (one-time)
# ---------------------------------------------------------------------------


def test_consume_rotation_token_one_time(tmp_path) -> None:
    server = _build_server(tmp_path)
    token = server._generate_rotation_token("c1")

    # First consumption succeeds.
    assert server._consume_rotation_token(token) == "c1"
    # Second consumption fails.
    assert server._consume_rotation_token(token) is None


# ---------------------------------------------------------------------------
# 4. Expired rotation token is rejected
# ---------------------------------------------------------------------------


def test_expired_rotation_token_rejected(tmp_path) -> None:
    server = _build_server(tmp_path)
    token = server._generate_rotation_token("c1")

    # Manually backdate the token beyond the TTL.
    server._active_rotation_tokens[token]["created_at"] = (
        time.monotonic() - server._rotation_token_ttl_seconds - 1
    )

    assert server._consume_rotation_token(token) is None


# ---------------------------------------------------------------------------
# 5. Purging tokens for one client leaves other clients intact
# ---------------------------------------------------------------------------


def test_purge_rotation_tokens_for_client(tmp_path) -> None:
    server = _build_server(tmp_path)
    tok_c1_a = server._generate_rotation_token("c1")
    tok_c1_b = server._generate_rotation_token("c1")
    tok_c2 = server._generate_rotation_token("c2")

    server._purge_rotation_tokens_for_client("c1")

    # c1 tokens are gone.
    assert server._consume_rotation_token(tok_c1_a) is None
    assert server._consume_rotation_token(tok_c1_b) is None
    # c2 token is still valid.
    assert server._consume_rotation_token(tok_c2) == "c2"


# ---------------------------------------------------------------------------
# 6. server.stop() clears all rotation tokens
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_stop_clears_rotation_tokens(tmp_path) -> None:
    server = _build_server(tmp_path)
    server._generate_rotation_token("c1")

    # stop() only runs cleanup when _running is True.
    server._running = True
    await server.stop()

    assert server._active_rotation_tokens == {}


# ---------------------------------------------------------------------------
# 7. Unknown token returns None
# ---------------------------------------------------------------------------


def test_unknown_token_returns_none(tmp_path) -> None:
    server = _build_server(tmp_path)
    assert server._consume_rotation_token("nonexistent") is None
