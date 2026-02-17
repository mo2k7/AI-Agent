"""Tests for user-visible response sanitization."""

from __future__ import annotations

from agent_host.response_sanitizer import sanitize_user_visible_response


def test_sanitize_response_passthrough_for_plain_text() -> None:
    text = "Here is a normal markdown answer.\n- point one\n- point two"
    assert sanitize_user_visible_response(text) == text


def test_sanitize_response_converts_structured_contract_json() -> None:
    raw = """
    {
      "verbosity": 1,
      "title": "Plan",
      "summary": "Quick summary.",
      "sections": [
        {
          "heading": "Steps",
          "content": "Do the following:",
          "bullets": ["First action", "Second action"]
        }
      ],
      "next_actions": ["Run tests"]
    }
    """
    rendered = sanitize_user_visible_response(raw)
    assert "Quick summary." in rendered
    assert "## Steps" in rendered
    assert "- First action" in rendered
    assert "## Next Actions" in rendered
    assert "\"verbosity\"" not in rendered


def test_sanitize_response_converts_generic_json_to_readable_bullets() -> None:
    raw = '{"status":"ok","details":{"count":3,"active":true},"items":["a","b"]}'
    rendered = sanitize_user_visible_response(raw)
    assert "I converted a structured payload into a readable summary:" in rendered
    assert "**status**: ok" in rendered
    assert "details" in rendered.lower()
    assert "\"status\"" not in rendered
