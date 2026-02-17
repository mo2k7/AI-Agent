"""Security-focused configuration default tests."""

from __future__ import annotations

from agent_host.config import Config, _get_project_root


def test_from_env_uses_secure_defaults(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.delenv("AI_AGENT_ALLOWED_ROOTS", raising=False)
    monkeypatch.delenv("AI_AGENT_ENABLE_OPEN_ITEM", raising=False)
    monkeypatch.delenv("AI_AGENT_AUDIT_INCLUDE_PROMPT", raising=False)

    config = Config.from_env()

    assert config.allowed_roots == [_get_project_root()]
    assert config.enable_open_item is False
    assert config.audit_include_prompt is False


def test_from_env_allows_audit_prompt_opt_in(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("AI_AGENT_AUDIT_INCLUDE_PROMPT", "true")

    config = Config.from_env()

    assert config.audit_include_prompt is True
