"""Tests for formatting executed tool output for user-visible responses."""

from __future__ import annotations

from agent_host.core.services.prompt_service import _format_tool_execution_output


def test_format_search_files_output_lists_paths() -> None:
    execution = {
        "tool": "search_files",
        "ok": True,
        "output": {
            "query": "python",
            "matches": [
                {"path": "/Users/test/Documents/a.py"},
                {"path": "/Users/test/Desktop/b.py"},
            ],
            "truncated": False,
        },
    }

    content, summary = _format_tool_execution_output("search_files", execution)

    assert "Found 2 matching file(s)." in content
    assert "[a.py](file:///Users/test/Documents/a.py)" in content
    assert "[b.py](file:///Users/test/Desktop/b.py)" in content
    assert "(`/Users/test/Documents/a.py`)" in content
    assert summary


def test_format_search_files_output_empty_result_guides_user() -> None:
    execution = {
        "tool": "search_files",
        "ok": True,
        "output": {
            "query": "nonexistent",
            "matches": [],
            "truncated": False,
        },
    }

    content, summary = _format_tool_execution_output("search_files", execution)

    assert "No files found." in content
    assert "Try a more specific" in content
    assert content == summary


def test_format_apply_ops_output_accepts_non_integer_indexes() -> None:
    execution = {
        "tool": "apply_ops",
        "ok": False,
        "output": {
            "plan_id": "plan-123",
            "applied": 0,
            "failed": 1,
            "skipped": 0,
            "results": [
                {
                    "index": "?",
                    "op": "move",
                    "ok": False,
                    "src": "/tmp/a.txt",
                    "error": "Invalid path",
                }
            ],
        },
    }

    content, summary = _format_tool_execution_output("apply_ops", execution)

    assert "**Operations Applied** — plan `plan-123`" in content
    assert "?. ❌ **move** `/tmp/a.txt` — Invalid path" in content
    assert summary
