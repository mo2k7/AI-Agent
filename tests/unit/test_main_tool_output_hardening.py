"""Additional formatting tests for tool execution output rendering."""

from __future__ import annotations

from agent_host.main import _format_tool_execution_output


def test_format_search_files_prefers_link_ready_metadata() -> None:
    execution = {
        "tool": "search_files",
        "ok": True,
        "output": {
            "query": "python",
            "matches": [
                {
                    "path": "/tmp/project/src/app.py",
                    "name": "app.py",
                    "display_path": "~/project/src/app.py",
                    "uri": "file:///tmp/project/src/app.py",
                }
            ],
            "truncated": False,
        },
    }

    content, summary = _format_tool_execution_output("search_files", execution)

    assert "[app.py](file:///tmp/project/src/app.py)" in content
    assert "(`~/project/src/app.py`)" in content
    assert summary


def test_format_search_files_shows_truncation_reason_and_scan_count() -> None:
    execution = {
        "tool": "search_files",
        "ok": True,
        "output": {
            "query": "report",
            "matches": [{"path": "/tmp/report.pdf"}],
            "truncated": True,
            "truncated_reason": "Reached walk scan limit (200 entries)",
            "scanned_entries": 345,
        },
    }

    content, _ = _format_tool_execution_output("search_files", execution)

    assert "Search scan truncated: Reached walk scan limit (200 entries)." in content
    assert "Scanned entries: 345." in content


def test_format_search_files_falls_back_when_uri_missing() -> None:
    execution = {
        "tool": "search_files",
        "ok": True,
        "output": {
            "query": "notes",
            "matches": [{"path": "/tmp/notes.txt", "name": "notes.txt"}],
            "truncated": False,
        },
    }

    content, _ = _format_tool_execution_output("search_files", execution)

    assert "[notes.txt](file://" in content
    assert "notes.txt" in content


def test_format_search_files_uses_execution_tool_when_tool_name_mismatches() -> None:
    execution = {
        "tool": "search_files",
        "ok": True,
        "output": {
            "query": "gemini",
            "matches": [],
            "truncated": True,
            "truncated_reason": "Reached walk scan limit (20001 entries)",
        },
    }

    content, summary = _format_tool_execution_output("SEARCH_FILES", execution)

    assert "No files found." in content
    assert "Try a more specific" in content
    assert content == summary


def test_format_search_files_parses_stringified_output_payload() -> None:
    execution = {
        "tool": "search_files",
        "ok": True,
        "output": '{"query":"gemini","matches":[{"path":"/tmp/generated.png"}],"truncated":false}',
    }

    content, summary = _format_tool_execution_output("search_files", execution)

    assert "Found 1 matching file(s)." in content
    assert "[generated.png](file://" in content
    assert "generated.png" in content
    assert summary


def test_format_search_files_mentions_more_results_when_next_token_present() -> None:
    execution = {
        "tool": "search_files",
        "ok": True,
        "output": {
            "query": "gemini",
            "matches": [{"path": "/tmp/a.txt"}],
            "next_token": "opaque",
            "truncated": True,
        },
    }

    content, _ = _format_tool_execution_output("search_files", execution)

    assert "More results are available." in content


def test_format_unknown_tool_fallback_is_readable_not_raw_json() -> None:
    execution = {
        "tool": "unregistered_tool",
        "ok": False,
        "error": "simulated failure",
        "output": {"path": "/tmp/file.txt", "count": 2},
    }

    content, summary = _format_tool_execution_output("unregistered_tool", execution)

    assert "**Tool Execution Result**" in content
    assert "simulated failure" in content
    assert "\"tool\"" not in content
    assert summary


def test_format_generate_image_output_lists_saved_images() -> None:
    execution = {
        "tool": "generate_image",
        "ok": True,
        "output": {
            "summary": "Generated 1 image(s) with model 'imagen-4.0-fast-generate-001'.",
            "model": "imagen-4.0-fast-generate-001",
            "images": [
                {
                    "path": "/tmp/generated/cat.png",
                    "mime_type": "image/png",
                    "width": 1024,
                    "height": 1024,
                    "sha256": "abc",
                    "note_embedded": False,
                }
            ],
        },
    }

    content, summary = _format_tool_execution_output("generate_image", execution)

    assert "**Image Generation**" in content
    assert "Generated 1 image(s):" in content
    assert "[cat.png](file://" in content
    assert "generated/cat.png" in content
    assert "1024x1024" in content
    assert summary


def test_format_generate_image_output_handles_empty_payload() -> None:
    execution = {
        "tool": "generate_image",
        "ok": True,
        "output": {"model": "imagen-4.0-generate-001", "images": []},
    }

    content, summary = _format_tool_execution_output("generate_image", execution)

    assert "No saved images were returned." in content
    assert content == summary


def test_format_browse_web_output_compacts_policy_warnings() -> None:
    execution = {
        "tool": "browse_web",
        "ok": True,
        "output": {
            "final_url": "https://example.com/article",
            "title": "Example Article",
            "effective_browse_profile": "flexible",
            "policy_warnings": [
                "Access restriction warning: URL appears to require login.",
                "Security attestation warning: stale",
            ],
            "content": "Article body text.",
        },
    }

    content, summary = _format_tool_execution_output("browse_web", execution)

    assert "**Web Browse**" in content
    assert "Source: [Example Article](https://example.com/article)" in content
    assert "Browse profile: `flexible`" in content
    assert "Policy notice: `flexible` browsing allowed this result with policy warnings." in content
    assert "Policy notice: `flexible` browsing allowed this result with policy warnings.\n\nCaution:" in content
    assert "Caution: Access restriction warning: URL appears to require login. (+1 more)" in content
    assert "Article body text." in content
    assert "Caution:" in summary
