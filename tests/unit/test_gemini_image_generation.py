"""Unit tests for Gemini image generation helper APIs (Nano Banana)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent_host.gemini_client import GeminiClient, GeminiClientError


def _make_client(*, models: list[SimpleNamespace], generate_content_impl=None):
    client = GeminiClient.__new__(GeminiClient)
    client.max_retries = 0
    client.retry_delay = 0.01
    client.BACKOFF_MULTIPLIER = 2.0
    client.MAX_BACKOFF_DELAY = 60.0
    client._cached_image_models = []
    client._cached_image_models_expires_at = 0.0
    client._cached_models = []
    client._cached_models_expires_at = 0.0
    mock_models = SimpleNamespace(
        list=lambda **_kwargs: models,
    )
    if generate_content_impl is not None:
        mock_models.generate_content = generate_content_impl
    client._client = SimpleNamespace(models=mock_models)
    return client


def test_list_available_image_models_discovers_nano_banana_models() -> None:
    models = [
        SimpleNamespace(
            name="models/gemini-2.5-flash-image",
            supported_actions=["generateContent"],
        ),
        SimpleNamespace(
            name="models/gemini-2.5-pro",
            supported_actions=["generateContent"],
        ),
        SimpleNamespace(
            name="models/imagen-4.0-generate-001",
            supported_actions=["generate_images"],
        ),
    ]
    client = _make_client(models=models)

    discovered = client._list_available_image_models(force_refresh=True)

    assert "gemini-2.5-flash-image" in discovered
    assert "imagen-4.0-generate-001" in discovered
    # gemini-2.5-pro does NOT have "image" in its name, so excluded
    assert "gemini-2.5-pro" not in discovered


def test_list_available_image_models_accepts_predict_supported_actions() -> None:
    models = [
        SimpleNamespace(
            name="models/imagen-3.0-generate-001",
            supported_actions=["predict"],
        )
    ]
    client = _make_client(models=models)

    discovered = client._list_available_image_models(force_refresh=True)

    assert discovered == ["imagen-3.0-generate-001"]


def test_resolve_image_model_prefers_nano_banana() -> None:
    models = [
        SimpleNamespace(
            name="models/gemini-2.5-flash-image",
            supported_actions=["generateContent"],
        ),
        SimpleNamespace(
            name="models/imagen-4.0-generate-001",
            supported_actions=["generate_images"],
        ),
    ]
    client = _make_client(models=models)

    resolved = client.resolve_image_model(quality_tier="standard")
    assert resolved == "gemini-2.5-flash-image"


def test_generate_image_returns_parsed_bytes() -> None:
    calls: list[dict[str, object]] = []
    models = [
        SimpleNamespace(
            name="models/gemini-2.5-flash-image",
            supported_actions=["generateContent"],
        )
    ]

    def _generate_content_impl(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            parts=[
                SimpleNamespace(
                    inline_data=SimpleNamespace(
                        data=b"\x89PNG\r\n\x1a\n",
                        mime_type="image/png",
                    ),
                    text=None,
                ),
                SimpleNamespace(
                    inline_data=None,
                    text="A sketch of a cat.",
                ),
            ]
        )

    client = _make_client(
        models=models,
        generate_content_impl=_generate_content_impl,
    )

    result = client.generate_image(
        prompt="A simple sketch of a cat.",
        quality_tier="standard",
        number_of_images=1,
        aspect_ratio="1:1",
        image_size="1K",
        person_generation="ALLOW_ADULT",
    )

    assert result["model"] == "gemini-2.5-flash-image"
    assert len(result["images"]) == 1
    first = result["images"][0]
    assert first["bytes"] == b"\x89PNG\r\n\x1a\n"
    assert first["mime_type"] == "image/png"
    assert "A sketch of a cat." in result["text_responses"]
    assert calls


def test_resolve_image_model_rejects_unavailable_override() -> None:
    models = [
        SimpleNamespace(
            name="models/gemini-2.5-flash-image",
            supported_actions=["generateContent"],
        )
    ]
    client = _make_client(models=models)

    with pytest.raises(GeminiClientError, match="Configured image model"):
        client.resolve_image_model(model_override="nonexistent-model")


def test_generate_image_multiple_calls_for_multiple_images() -> None:
    call_count = 0
    models = [
        SimpleNamespace(
            name="models/gemini-2.5-flash-image",
            supported_actions=["generateContent"],
        )
    ]

    def _generate_content_impl(**_kwargs):
        nonlocal call_count
        call_count += 1
        return SimpleNamespace(
            parts=[
                SimpleNamespace(
                    inline_data=SimpleNamespace(
                        data=b"\x89PNG" + bytes([call_count]),
                        mime_type="image/png",
                    ),
                    text=None,
                ),
            ]
        )

    client = _make_client(
        models=models,
        generate_content_impl=_generate_content_impl,
    )

    result = client.generate_image(
        prompt="Multiple cats",
        number_of_images=3,
    )

    assert call_count == 3
    assert len(result["images"]) == 3
    # Each image should have unique bytes
    all_bytes = [img["bytes"] for img in result["images"]]
    assert len(set(all_bytes)) == 3


def test_generate_image_appends_negative_prompt() -> None:
    captured_contents: list[list[str]] = []
    models = [
        SimpleNamespace(
            name="models/gemini-2.5-flash-image",
            supported_actions=["generateContent"],
        )
    ]

    def _generate_content_impl(**kwargs):
        captured_contents.append(kwargs.get("contents", []))
        return SimpleNamespace(
            parts=[
                SimpleNamespace(
                    inline_data=SimpleNamespace(data=b"img", mime_type="image/png"),
                    text=None,
                ),
            ]
        )

    client = _make_client(
        models=models,
        generate_content_impl=_generate_content_impl,
    )

    client.generate_image(
        prompt="A beautiful sunset",
        negative_prompt="blurry, low quality",
    )

    assert captured_contents
    prompt_text = captured_contents[0][0]
    assert "A beautiful sunset" in prompt_text
    assert "Avoid: blurry, low quality" in prompt_text


def test_resolve_text_model_uses_live_catalog_without_hardcoded_defaults() -> None:
    models = [
        SimpleNamespace(
            name="models/gemini-2.5-pro",
            display_name="Gemini 2.5 Pro",
            description="Stable reasoning model",
            supported_actions=["generateContent"],
            input_token_limit=1_048_576,
            output_token_limit=65_536,
        ),
        SimpleNamespace(
            name="models/gemini-2.5-flash",
            display_name="Gemini 2.5 Flash",
            description="Stable fast model",
            supported_actions=["generateContent"],
            input_token_limit=1_048_576,
            output_token_limit=65_536,
        ),
        SimpleNamespace(
            name="models/gemini-3-flash-preview",
            display_name="Gemini 3 Flash Preview",
            description="Preview model",
            supported_actions=["generateContent"],
            input_token_limit=1_048_576,
            output_token_limit=65_536,
        ),
    ]
    client = _make_client(models=models)
    client.model_name = ""

    resolved = client.resolve_text_model()

    assert resolved == "gemini-2.5-flash"
