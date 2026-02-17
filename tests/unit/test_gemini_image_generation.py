"""Unit tests for Gemini image generation helper APIs."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent_host.gemini_client import GeminiClient, GeminiClientError


def _make_client(*, models: list[SimpleNamespace], generate_impl):
    client = GeminiClient.__new__(GeminiClient)
    client.max_retries = 0
    client.retry_delay = 0.01
    client._cached_image_models = []
    client._cached_image_models_expires_at = 0.0
    client._client = SimpleNamespace(
        models=SimpleNamespace(
            list=lambda **_kwargs: models,
            generate_images=generate_impl,
        )
    )
    return client


def test_list_available_image_models_filters_non_image_models() -> None:
    models = [
        SimpleNamespace(
            name="models/imagen-4.0-generate-001",
            supported_actions=["generate_images"],
        ),
        SimpleNamespace(
            name="models/gemini-2.5-pro",
            supported_actions=["generate_content"],
        ),
        SimpleNamespace(
            name="models/imagen-4.0-fast-generate-001",
            supported_actions=[],
        ),
    ]
    client = _make_client(
        models=models,
        generate_impl=lambda **_kwargs: SimpleNamespace(generated_images=[]),
    )

    discovered = client._list_available_image_models(force_refresh=True)

    assert discovered == [
        "imagen-4.0-fast-generate-001",
        "imagen-4.0-generate-001",
    ]


def test_list_available_image_models_accepts_predict_supported_actions() -> None:
    models = [
        SimpleNamespace(
            name="models/imagen-3.0-generate-001",
            supported_actions=["predict"],
        )
    ]
    client = _make_client(
        models=models,
        generate_impl=lambda **_kwargs: SimpleNamespace(generated_images=[]),
    )

    discovered = client._list_available_image_models(force_refresh=True)

    assert discovered == ["imagen-3.0-generate-001"]


def test_resolve_image_model_uses_quality_preferences() -> None:
    models = [
        SimpleNamespace(
            name="models/imagen-4.0-fast-generate-001",
            supported_actions=["generate_images"],
        ),
        SimpleNamespace(
            name="models/imagen-4.0-generate-001",
            supported_actions=["generate_images"],
        ),
    ]
    client = _make_client(
        models=models,
        generate_impl=lambda **_kwargs: SimpleNamespace(generated_images=[]),
    )

    assert client.resolve_image_model(quality_tier="standard") == "imagen-4.0-generate-001"
    assert client.resolve_image_model(quality_tier="fast") == "imagen-4.0-fast-generate-001"
    with pytest.raises(GeminiClientError, match="quality_tier='ultra'"):
        client.resolve_image_model(quality_tier="ultra")


def test_generate_images_returns_parsed_bytes_and_metadata() -> None:
    calls: list[dict[str, object]] = []
    models = [
        SimpleNamespace(
            name="models/imagen-4.0-generate-001",
            supported_actions=["generate_images"],
        )
    ]

    def _generate_impl(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            generated_images=[
                SimpleNamespace(
                    image=SimpleNamespace(
                        image_bytes=b"\x89PNG\r\n\x1a\n",
                        width=256,
                        height=256,
                    ),
                    rai_filtered_reason="",
                    safety_attributes=None,
                )
            ]
        )

    client = _make_client(models=models, generate_impl=_generate_impl)

    result = client.generate_images(
        prompt="A simple sketch of a cat.",
        quality_tier="standard",
        number_of_images=1,
        aspect_ratio="1:1",
        image_size="1K",
        enhance_prompt=True,
        person_generation="allow_adult",
    )

    assert result["model"] == "imagen-4.0-generate-001"
    assert len(result["images"]) == 1
    first = result["images"][0]
    assert first["bytes"] == b"\x89PNG\r\n\x1a\n"
    assert first["width"] == 256
    assert first["height"] == 256
    assert calls


def test_resolve_image_model_rejects_unavailable_override() -> None:
    models = [
        SimpleNamespace(
            name="models/imagen-4.0-generate-001",
            supported_actions=["generate_images"],
        )
    ]
    client = _make_client(
        models=models,
        generate_impl=lambda **_kwargs: SimpleNamespace(generated_images=[]),
    )

    with pytest.raises(GeminiClientError, match="Configured image model"):
        client.resolve_image_model(model_override="imagen-4.0-ultra-generate-001")
