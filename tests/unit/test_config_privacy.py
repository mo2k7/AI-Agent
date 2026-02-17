"""Privacy-related configuration tests."""

from __future__ import annotations

from agent_host.config import Config


def test_from_env_loads_privacy_and_vertex_options(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("AI_AGENT_REQUIRE_NO_TRAINING", "true")
    monkeypatch.setenv("AI_AGENT_USE_VERTEXAI", "true")
    monkeypatch.setenv("AI_AGENT_VERTEX_PROJECT", "proj-123")
    monkeypatch.setenv("AI_AGENT_VERTEX_LOCATION", "us-east4")

    config = Config.from_env()

    assert config.require_no_training is True
    assert config.use_vertexai is True
    assert config.vertex_project == "proj-123"
    assert config.vertex_location == "us-east4"


def test_from_env_allows_vertex_mode_without_google_api_key(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("AI_AGENT_USE_VERTEXAI", "true")
    monkeypatch.setenv("AI_AGENT_VERTEX_PROJECT", "proj-vertex")

    config = Config.from_env()

    assert config.use_vertexai is True
    assert config.vertex_project == "proj-vertex"
