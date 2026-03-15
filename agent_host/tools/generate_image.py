"""Handler for the ``generate_image`` tool."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Any

from agent_host.tools._helpers import (
    _build_default_image_output_path,
    _default_image_file_extension,
    _path_within_any_root,
)
from agent_host.tools.registry import ImageToolContext, register_note_handler

logger = logging.getLogger(__name__)


async def handle(
    ctx: ImageToolContext, arguments: dict[str, Any]
) -> dict[str, object]:
    """Execute the generate_image tool."""
    img_prompt = str(arguments.get("prompt", "") or "").strip()
    if not img_prompt:
        return {"ok": False, "output": "Image prompt cannot be empty."}

    image_failure: str | None = None

    def _set_image_failure(message: str) -> None:
        nonlocal image_failure
        if image_failure is None:
            image_failure = message

    # ── Parse and validate all arguments ──

    output_path_raw = arguments.get("output_path")
    output_path_str = ""
    if output_path_raw is None:
        output_path_str = ""
    elif isinstance(output_path_raw, str):
        output_path_str = output_path_raw.strip()
    else:
        _set_image_failure("output_path must be a string when provided.")

    raw_note_id_value = arguments.get("note_id")
    raw_note_id = ""
    if raw_note_id_value is None:
        raw_note_id = ""
    elif isinstance(raw_note_id_value, str):
        raw_note_id = raw_note_id_value.strip()
    else:
        _set_image_failure("note_id must be a string when provided.")

    requested_alt = arguments.get("alt_text")
    if requested_alt is None:
        img_alt = img_prompt[:120]
    elif isinstance(requested_alt, str):
        trimmed_alt = requested_alt.strip()
        img_alt = trimmed_alt if trimmed_alt else img_prompt[:120]
    else:
        img_alt = img_prompt[:120]
        _set_image_failure("alt_text must be a string when provided.")

    quality_raw = arguments.get("quality_tier") or "standard"
    quality_tier = "standard"
    if isinstance(quality_raw, str) and quality_raw.strip():
        quality_tier = quality_raw.strip().lower()
    else:
        _set_image_failure("quality_tier must be a non-empty string.")

    aspect_ratio_raw = arguments.get("aspect_ratio") or "1:1"
    aspect_ratio = "1:1"
    if isinstance(aspect_ratio_raw, str) and aspect_ratio_raw.strip():
        aspect_ratio = aspect_ratio_raw.strip()
    else:
        _set_image_failure("aspect_ratio must be a non-empty string.")

    image_size_raw = arguments.get("image_size") or "1K"
    image_size = "1K"
    if isinstance(image_size_raw, str) and image_size_raw.strip():
        image_size = image_size_raw.strip()
    else:
        _set_image_failure("image_size must be a non-empty string.")

    person_generation_raw = arguments.get("person_generation") or "ALLOW_ADULT"
    person_generation = "ALLOW_ADULT"
    if isinstance(person_generation_raw, str) and person_generation_raw.strip():
        person_generation = person_generation_raw.strip().upper()
    else:
        _set_image_failure("person_generation must be a non-empty string.")

    negative_prompt_raw = arguments.get("negative_prompt")
    negative_prompt: str | None = None
    if negative_prompt_raw is None:
        negative_prompt = None
    elif isinstance(negative_prompt_raw, str):
        trimmed_negative = negative_prompt_raw.strip()
        negative_prompt = trimmed_negative or None
    else:
        _set_image_failure("negative_prompt must be a string when provided.")

    number_raw = arguments.get("number_of_images", 1)
    number_of_images = 1
    if isinstance(number_raw, bool) or not isinstance(number_raw, int):
        _set_image_failure(
            "number_of_images must be an integer between 1 and 4."
        )
    else:
        number_of_images = number_raw
        if number_of_images < 1 or number_of_images > 4:
            _set_image_failure("number_of_images must be between 1 and 4.")

    # Nano Banana returns image/png by default; used for file extension logic
    output_mime_type = "image/png"

    # ── Resolve optional note_id ──

    embedded_note_id: str | None = None
    if image_failure is None and raw_note_id:
        embedded_note_id = await ctx.resolve_note_id(
            ctx.session_id,
            raw_note_id,
            ctx.memory_manager,
            ctx.db_timeout_seconds,
            ctx.request_id,
            ctx.method,
        )
        if embedded_note_id is None:
            _set_image_failure(
                f"No note found matching id prefix '{raw_note_id}'."
            )

    # ── Compute output paths ──

    output_paths: list[Path] = []
    if image_failure is None:
        if output_path_str:
            requested_output = Path(output_path_str).expanduser()
            if not requested_output.is_absolute():
                _set_image_failure(
                    "output_path must be absolute or ~-relative."
                )
            else:
                requested_output = requested_output.resolve(strict=False)
                allowed_output_roots = [
                    root.expanduser().resolve(strict=False)
                    for root in ctx.config_allowed_roots
                ]
                allowed_output_roots.append(ctx.image_output_root)
                if not _path_within_any_root(
                    requested_output, allowed_output_roots
                ):
                    _set_image_failure(
                        "output_path is outside allowed roots and image output root."
                    )
                else:
                    default_ext = _default_image_file_extension(output_mime_type)
                    if number_of_images == 1:
                        if not requested_output.suffix:
                            requested_output = requested_output.with_suffix(
                                default_ext
                            )
                        output_paths = [requested_output]
                    else:
                        stem = requested_output.stem
                        parent = requested_output.parent
                        ext = requested_output.suffix or default_ext
                        output_paths = [
                            parent / f"{stem}-{idx + 1:02d}{ext}"
                            for idx in range(number_of_images)
                        ]
        else:
            output_paths = [
                _build_default_image_output_path(
                    image_output_root=ctx.image_output_root,
                    session_id=ctx.session_id,
                    prompt=img_prompt,
                    image_index=idx,
                    output_mime_type=output_mime_type,
                )
                for idx in range(number_of_images)
            ]

    # ── Generate images via Gemini ──

    persisted_images: list[dict[str, object]] = []
    image_result: dict[str, Any] = {}
    generated_images: list[dict[str, Any]] = []
    if image_failure is None:
        try:
            image_result = await asyncio.wait_for(
                asyncio.to_thread(
                    ctx.gemini_client.generate_image,
                    prompt=img_prompt,
                    quality_tier=quality_tier,
                    number_of_images=number_of_images,
                    aspect_ratio=aspect_ratio,
                    image_size=image_size,
                    person_generation=person_generation,
                    negative_prompt=negative_prompt,
                    model_override=ctx.image_model_override,
                ),
                timeout=ctx.image_timeout_seconds,
            )
        except Exception as img_exc:
            logger.warning("Image generation failed: %s", img_exc)
            _set_image_failure(f"Image generation failed: {img_exc}")

    if image_failure is None:
        raw_generated_images = image_result.get("images", [])
        if not isinstance(raw_generated_images, list):
            _set_image_failure(
                "Image generation returned malformed images payload."
            )
        else:
            generated_images = [
                item
                for item in raw_generated_images
                if isinstance(item, dict)
            ]
            if len(generated_images) != len(raw_generated_images):
                _set_image_failure(
                    "Image generation returned malformed image entries."
                )
            elif len(generated_images) != number_of_images:
                _set_image_failure(
                    "Image generation did not return the requested number of images "
                    f"({len(generated_images)}/{number_of_images})."
                )

    # ── Validate image bytes ──

    prepared_images: list[tuple[bytes, str, int, int]] = []
    if image_failure is None:
        for generated in generated_images:
            image_bytes = generated.get("bytes", b"")
            if not isinstance(image_bytes, bytes) or not image_bytes:
                _set_image_failure("Image generation returned empty content")
                break
            img_mime = str(generated.get("mime_type", "image/png") or "image/png")
            width = int(generated.get("width", 0) or 0)
            height = int(generated.get("height", 0) or 0)
            prepared_images.append((image_bytes, img_mime, width, height))

    # ── Persist to disk + optionally embed in note ──

    markers_to_append: list[str] = []
    if image_failure is None:
        for idx, prepared_image in enumerate(prepared_images):
            image_bytes, img_mime, width, height = prepared_image
            target_path = output_paths[idx]
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(image_bytes)
            digest = hashlib.sha256(image_bytes).hexdigest()
            persisted_record: dict[str, object] = {
                "path": str(target_path),
                "mime_type": img_mime,
                "width": width,
                "height": height,
                "sha256": digest,
                "note_embedded": False,
            }

            if embedded_note_id:
                img_record = await ctx.run_blocking(
                    label="notes.create_image",
                    timeout_seconds=ctx.db_timeout_seconds,
                    func=ctx.memory_manager.create_note_image,
                    args=(ctx.session_id, embedded_note_id),
                    kwargs={
                        "image_bytes": image_bytes,
                        "mime_type": img_mime,
                        "width": width,
                        "height": height,
                        "alt_text": img_alt,
                    },
                    request_id=ctx.request_id,
                    method=ctx.method,
                )
                note_image_id = str(img_record["image_id"])
                markers_to_append.append(
                    f"![{img_alt}](note-image://{note_image_id})"
                )
                persisted_record["note_embedded"] = True
                persisted_record["note_id"] = embedded_note_id
                persisted_record["note_image_id"] = note_image_id

            persisted_images.append(persisted_record)

    if image_failure is None and embedded_note_id and markers_to_append:
        existing_note = await ctx.run_blocking(
            label="notes.get_for_image",
            timeout_seconds=ctx.db_timeout_seconds,
            func=ctx.memory_manager.get_note,
            args=(ctx.session_id, embedded_note_id),
            request_id=ctx.request_id,
            method=ctx.method,
        )
        current_content = (
            existing_note.get("content", "") if existing_note else ""
        )
        separator = "\n" if current_content else ""
        markers_block = "\n".join(markers_to_append)
        await ctx.run_blocking(
            label="notes.update_with_image",
            timeout_seconds=ctx.db_timeout_seconds,
            func=ctx.memory_manager.update_note,
            args=(ctx.session_id, embedded_note_id),
            kwargs={
                "content": f"{current_content}{separator}{markers_block}"
            },
            request_id=ctx.request_id,
            method=ctx.method,
        )

    # ── Return result ──

    if image_failure is not None:
        return {"ok": False, "output": image_failure}

    return {
        "ok": True,
        "output": {
            "summary": (
                f"Generated {len(persisted_images)} image(s) "
                f"with model '{image_result.get('model', '')}'."
            ),
            "model": image_result.get("model", ""),
            "images": persisted_images,
            "request": {
                "quality_tier": quality_tier,
                "aspect_ratio": aspect_ratio,
                "image_size": image_size,
                "number_of_images": number_of_images,
                "person_generation": person_generation,
            },
            "warnings": [],
            "prompt_metadata": {
                "prompt_length_chars": len(img_prompt),
            },
        },
    }


register_note_handler("generate_image", handle)
