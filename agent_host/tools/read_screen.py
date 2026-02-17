"""Handler for the ``read_screen`` tool."""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

from agent_host.tools._helpers import _compact_ocr_text_for_model
from agent_host.tools.registry import ScreenToolContext, register_screen_handler

logger = logging.getLogger(__name__)


async def handle(
    ctx: ScreenToolContext, arguments: dict[str, Any]
) -> tuple[dict[str, object], bytes | None]:
    """Execute the read_screen tool.

    Returns ``(execution_dict, screen_image_bytes)`` where the image bytes
    may be ``None`` when the capture failed or did not include image data.
    """
    capture_future: asyncio.Future[dict | None] = (
        asyncio.get_running_loop().create_future()
    )
    ctx.pending_screen_captures[ctx.request_id] = (
        ctx.client_address,
        capture_future,
    )

    await ctx.send_status(ctx.request_id)

    _SCREEN_CAPTURE_TIMEOUT = object()
    try:
        capture_data = await asyncio.wait_for(capture_future, timeout=30.0)
    except asyncio.TimeoutError:
        capture_data = _SCREEN_CAPTURE_TIMEOUT
    finally:
        ctx.pending_screen_captures.pop(ctx.request_id, None)

    screen_image_bytes: bytes | None = None

    if capture_data is _SCREEN_CAPTURE_TIMEOUT:
        execution: dict[str, object] = {
            "ok": False,
            "output": (
                "Screen capture timed out after 30 seconds. "
                "The frontend may be unresponsive or disconnected."
            ),
        }
    elif capture_data is None:
        execution = {
            "ok": False,
            "output": (
                "Screen capture failed. "
                "Screen recording permission may not be granted, "
                "or the capture was cancelled."
            ),
        }
    else:
        capture_error = capture_data.get("error", "")
        if capture_error:
            execution = {
                "ok": False,
                "output": f"Screen capture failed: {capture_error}",
            }
        else:
            ocr_text = capture_data.get("ocr_text") or ""
            image_b64 = capture_data.get("image_data") or ""
            cap_width = capture_data.get("width") or 0
            cap_height = capture_data.get("height") or 0

            if image_b64:
                try:
                    screen_image_bytes = base64.b64decode(image_b64)
                except Exception:
                    screen_image_bytes = None

            purpose = arguments.get("purpose", "")
            compact_ocr, ocr_truncated, included_lines, total_lines = (
                _compact_ocr_text_for_model(
                    str(ocr_text),
                    purpose=str(purpose) if isinstance(purpose, str) else "",
                    prompt=ctx.resolved_user_prompt,
                    max_chars=ctx.read_screen_ocr_max_chars,
                    max_lines=ctx.read_screen_ocr_max_lines,
                )
            )
            if not compact_ocr.strip():
                compact_ocr = "(No OCR text detected.)"
            if ocr_truncated:
                logger.info(
                    "Compacted read_screen OCR payload for request %s: %s/%s lines",
                    ctx.request_id,
                    included_lines,
                    total_lines,
                )

            ocr_block_title = "--- OCR Text ---"
            truncation_note = ""
            if ocr_truncated:
                ocr_block_title = (
                    f"--- OCR Text (focused excerpt: "
                    f"{included_lines}/{total_lines} lines) ---"
                )
                truncation_note = (
                    "\nOCR text was compacted for latency and reliability. "
                    "Use the attached screenshot for full visual context.\n"
                )

            purpose_line = f"\nFocus: {purpose}" if purpose else ""
            execution = {
                "ok": True,
                "output": (
                    f"Screenshot captured ({cap_width}x{cap_height})."
                    f"{purpose_line}\n"
                    f"{ocr_block_title}\n{compact_ocr}\n--- End OCR ---\n"
                    f"{truncation_note}"
                    "The screenshot image is also attached for visual analysis.\n"
                    "This is the content currently visible on the user's screen. "
                    "Use this text to fulfill the user's request directly — "
                    "do not attempt to search for or browse to the source URL."
                ),
            }

    return execution, screen_image_bytes


register_screen_handler(handle)
