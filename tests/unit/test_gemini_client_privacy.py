"""Privacy hardening tests for Gemini client initialization."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import types

from agent_host.gemini_client import GeminiClient, GeminiClientError


def test_gemini_client_rejects_api_key_mode_when_no_training_required() -> None:
    with pytest.raises(GeminiClientError, match="No-training mode is enabled"):
        GeminiClient(
            api_key="test-key",
            model_name="gemini-2.0-flash-exp",
            require_no_training=True,
            use_vertexai=False,
        )


def test_gemini_client_uses_vertex_when_no_training_required(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    class _DummyClient:
        def __init__(self, **kwargs: Any) -> None:
            calls.append(kwargs)

    monkeypatch.setattr("agent_host.gemini_client.genai.Client", _DummyClient)

    GeminiClient(
        api_key="unused-in-vertex-mode",
        model_name="gemini-2.0-flash-exp",
        require_no_training=True,
        use_vertexai=True,
        vertex_project="my-project",
        vertex_location="us-central1",
    )

    assert calls
    call = calls[0]
    assert call.get("vertexai") is True
    assert call.get("project") == "my-project"
    assert call.get("location") == "us-central1"


def test_gemini_client_requires_vertex_project_when_vertex_enabled() -> None:
    with pytest.raises(GeminiClientError, match="vertex_project is required"):
        GeminiClient(
            api_key="unused-in-vertex-mode",
            model_name="gemini-2.0-flash-exp",
            require_no_training=True,
            use_vertexai=True,
            vertex_project=None,
        )


def test_parse_response_concatenates_multiple_candidate_text_parts() -> None:
    client = GeminiClient.__new__(GeminiClient)
    response = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(text="First segment "),
                        SimpleNamespace(text="second segment"),
                    ]
                )
            )
        ]
    )

    parsed = client._parse_response(response)
    assert parsed["text"] == "First segment second segment"
    assert parsed["function_call"] is None


def test_parse_response_keeps_candidate_text_when_function_call_exists() -> None:
    client = GeminiClient.__new__(GeminiClient)
    response = SimpleNamespace(
        text=None,
        function_calls=[SimpleNamespace(name="search_files", args={"query": "report"})],
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[SimpleNamespace(text="Working on it...")]
                )
            )
        ],
    )

    parsed = client._parse_response(response)
    assert parsed["function_call"] == {"name": "search_files", "args": {"query": "report"}}
    assert parsed["text"] == "Working on it..."


def test_build_thinking_config_uses_level_for_gemini3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_AGENT_DEEP_THINK_LEVEL_GEMINI3", "medium")
    client = GeminiClient.__new__(GeminiClient)

    config = client._build_thinking_config(
        model_name="gemini-3-flash-preview",
        deep_think=True,
    )

    assert config is not None
    assert config.thinking_level == types.ThinkingLevel.MEDIUM
    assert config.include_thoughts is False


def test_build_thinking_config_uses_budget_for_gemini25(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_AGENT_DEEP_THINK_BUDGET_GEMINI25", "2048")
    client = GeminiClient.__new__(GeminiClient)

    config = client._build_thinking_config(
        model_name="gemini-2.5-pro",
        deep_think=True,
    )

    assert config is not None
    assert config.thinking_budget == 2048
    assert config.include_thoughts is False


def test_build_thinking_config_rejects_unsupported_model_in_strict_mode() -> None:
    client = GeminiClient.__new__(GeminiClient)

    with pytest.raises(GeminiClientError, match="Deep-think mode requires"):
        client._build_thinking_config(
            model_name="gemini-2.0-flash-exp",
            deep_think=True,
        )
