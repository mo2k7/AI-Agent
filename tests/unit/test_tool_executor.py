"""Unit tests for tool execution runtime."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from agent_host.tools.executor import ToolExecutionError, ToolExecutor


def _make_executor(tmp_path: Path, *, enable_open_item: bool = False) -> ToolExecutor:
    automations_dir = tmp_path / "automations"
    automations_dir.mkdir(parents=True, exist_ok=True)
    return ToolExecutor(
        allowed_roots=[tmp_path],
        automations_dir=automations_dir,
        enable_open_item=enable_open_item,
        search_scan_limit=5000,
    )


def test_search_files_finds_matches(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    target = tmp_path / "project" / "python_notes.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("hello")

    result = executor.execute("search_files", {"query": "python", "limit": 5})

    assert result["ok"] is True
    matches = result["output"]["matches"]
    assert any(item["path"] == str(target.resolve()) for item in matches)


def test_search_files_excludes_noisy_spotlight_paths(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    noisy_file = (
        tmp_path
        / "Pictures"
        / "Photos Library.photoslibrary"
        / "database"
        / "search"
        / "Spotlight"
        / "clientstatesmetafile"
    )
    noisy_file.parent.mkdir(parents=True, exist_ok=True)
    noisy_file.write_text("noise")

    good_file = tmp_path / "Documents" / "gemini_document_manual.md"
    good_file.parent.mkdir(parents=True, exist_ok=True)
    good_file.write_text("good")

    result = executor.execute(
        "search_files",
        {"query": "gemini file document man", "limit": 10},
    )

    matches = [item["path"] for item in result["output"]["matches"]]
    assert str(good_file.resolve()) in matches
    assert str(noisy_file.resolve()) not in matches


def test_search_files_semantic_extension_boosts_document_types(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    report_pdf = tmp_path / "Reports" / "project_overview.pdf"
    report_bin = tmp_path / "Reports" / "project_overview.bin"
    report_pdf.parent.mkdir(parents=True, exist_ok=True)
    report_pdf.write_text("pdf")
    report_bin.write_text("bin")

    result = executor.execute(
        "search_files",
        {"query": "project document", "limit": 10},
    )

    by_path = {item["path"]: int(item["score"]) for item in result["output"]["matches"]}
    assert str(report_pdf.resolve()) in by_path
    assert str(report_bin.resolve()) in by_path
    assert by_path[str(report_pdf.resolve())] > by_path[str(report_bin.resolve())]


def test_read_text_respects_byte_range(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    file_path = tmp_path / "story.txt"
    file_path.write_text("abcdefg")

    result = executor.execute(
        "read_text",
        {"path": str(file_path), "byte_range": [1, 4]},
    )

    assert result["ok"] is True
    output = result["output"]
    assert output["byte_range"] == [1, 4]
    assert output["content"] == "bcd"


def test_read_text_byte_range_avoids_full_file_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executor = _make_executor(tmp_path)
    file_path = tmp_path / "large_story.txt"
    file_path.write_text("0123456789" * 100)
    original_read_bytes = Path.read_bytes
    target = file_path.resolve()

    def _guarded_read_bytes(self: Path) -> bytes:
        if self.resolve() == target:
            raise AssertionError("read_bytes should not be called for ranged reads")
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", _guarded_read_bytes)

    result = executor.execute(
        "read_text",
        {"path": str(file_path), "byte_range": [10, 15]},
    )

    assert result["ok"] is True
    output = result["output"]
    assert output["byte_range"] == [10, 15]
    assert output["content"] == "01234"


def test_plan_and_apply_ops_move_file(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    src = tmp_path / "inbox" / "draft.txt"
    dest = tmp_path / "archive" / "draft.txt"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("data")

    plan = executor.execute(
        "plan_ops",
        {"ops": [{"op": "move", "src": str(src), "dest": str(dest)}]},
    )
    assert plan["ok"] is True
    plan_id = plan["output"]["plan_id"]

    applied = executor.execute("apply_ops", {"plan_id": plan_id})
    assert applied["ok"] is True
    assert applied["output"]["failed"] == 0
    assert not src.exists()
    assert dest.exists()


def test_planner_create_returns_structured_plan(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    src = tmp_path / "inbox" / "draft.txt"
    dest = tmp_path / "archive" / "draft.txt"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("data")

    planned = executor.execute(
        "planner",
        {
            "mode": "create",
            "goal": "Organize draft file",
            "ops": [{"op": "move", "src": str(src), "dest": str(dest)}],
        },
    )

    assert planned["ok"] is True
    output = planned["output"]
    assert isinstance(output.get("plan_id"), str)
    privacy = output.get("privacy", {})
    assert privacy.get("path_data_sent_to_unified_planning") is False
    assert privacy.get("network_disabled_during_planning") is True


def test_planner_analyze_reports_complexity(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    analyzed = executor.execute(
        "planner",
        {
            "mode": "analyze",
            "goal": "Assess complexity",
            "ops": [{"op": "copy", "src": "/redacted/source.txt", "dest": "/redacted/dest.txt"}],
        },
    )

    assert analyzed["ok"] is True
    complexity = analyzed["output"].get("complexity")
    assert isinstance(complexity, dict)
    assert "level" in complexity


@pytest.mark.parametrize("mode", ["create", "replan"])
def test_planner_create_or_replan_without_ops_returns_advisory_plan(
    tmp_path: Path,
    mode: str,
) -> None:
    executor = _make_executor(tmp_path)
    planned = executor.execute(
        "planner",
        {
            "mode": mode,
            "goal": "Create a study roadmap",
        },
    )

    assert planned["ok"] is True
    output = planned["output"]
    assert output.get("mode") == mode
    assert output.get("goal") == "Create a study roadmap"
    assert output.get("op_count") == 0
    assert output.get("advisory_only") is True
    assert output.get("requires_ops_for_execution") is True
    assert "plan_id" not in output
    assert isinstance(output.get("complexity"), dict)
    issues = output.get("issues")
    assert isinstance(issues, list) and issues


def test_apply_ops_delete_moves_to_trash_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executor = _make_executor(tmp_path)
    source = tmp_path / "inbox" / "delete_me.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("payload")
    trash_dir = tmp_path / ".test-trash"
    monkeypatch.setattr(ToolExecutor, "_trash_directory", staticmethod(lambda: trash_dir))

    plan = executor.execute(
        "plan_ops",
        {"ops": [{"op": "delete", "src": str(source)}]},
    )
    plan_id = plan["output"]["plan_id"]
    applied = executor.execute("apply_ops", {"plan_id": plan_id})

    assert applied["ok"] is True
    result_entry = applied["output"]["results"][0]
    assert result_entry["ok"] is True
    assert result_entry["delete_mode"] == "trash"
    trashed_path = Path(str(result_entry["trash_path"]))
    assert not source.exists()
    assert trashed_path.exists()
    assert trashed_path.read_text() == "payload"


def test_apply_ops_delete_trash_collision_gets_unique_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = _make_executor(tmp_path)
    source = tmp_path / "inbox" / "duplicate.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("new")
    trash_dir = tmp_path / ".test-trash"
    trash_dir.mkdir(parents=True, exist_ok=True)
    existing = trash_dir / "duplicate.txt"
    existing.write_text("old")
    monkeypatch.setattr(ToolExecutor, "_trash_directory", staticmethod(lambda: trash_dir))

    plan = executor.execute(
        "plan_ops",
        {"ops": [{"op": "delete", "src": str(source)}]},
    )
    applied = executor.execute("apply_ops", {"plan_id": plan["output"]["plan_id"]})

    result_entry = applied["output"]["results"][0]
    trashed_path = Path(str(result_entry["trash_path"]))
    assert result_entry["delete_mode"] == "trash"
    assert trashed_path.exists()
    assert trashed_path != existing
    assert trashed_path.read_text() == "new"
    assert existing.read_text() == "old"


def test_apply_ops_delete_hard_delete_opt_in_env_var(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = _make_executor(tmp_path)
    source = tmp_path / "inbox" / "remove_forever.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("x")
    trash_dir = tmp_path / ".test-trash"
    monkeypatch.setattr(ToolExecutor, "_trash_directory", staticmethod(lambda: trash_dir))
    monkeypatch.setenv(ToolExecutor._HARD_DELETE_ENV_VAR, "1")

    plan = executor.execute(
        "plan_ops",
        {"ops": [{"op": "delete", "src": str(source)}]},
    )
    applied = executor.execute("apply_ops", {"plan_id": plan["output"]["plan_id"]})

    result_entry = applied["output"]["results"][0]
    assert result_entry["delete_mode"] == "hard"
    assert not source.exists()
    assert not trash_dir.exists()


def test_apply_ops_unknown_plan_raises(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)

    with pytest.raises(ToolExecutionError, match="Unknown or expired plan_id"):
        executor.execute("apply_ops", {"plan_id": "plan-missing"})


def test_apply_ops_copy_with_rename_conflict_policy_preserves_existing(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    src = tmp_path / "inbox" / "report.txt"
    dest = tmp_path / "archive" / "report.txt"
    src.parent.mkdir(parents=True, exist_ok=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("new")
    dest.write_text("old")

    plan = executor.execute(
        "plan_ops",
        {
            "ops": [
                {
                    "op": "copy",
                    "src": str(src),
                    "dest": str(dest),
                    "overwrite_policy": "rename",
                }
            ]
        },
    )
    applied = executor.execute("apply_ops", {"plan_id": plan["output"]["plan_id"]})

    assert applied["ok"] is True
    assert dest.read_text() == "old"
    copy_target = Path(applied["output"]["results"][0]["dest"])
    assert copy_target.exists()
    assert copy_target.read_text() == "new"
    assert copy_target != dest


def test_apply_ops_stop_on_error_skips_remaining_operations(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    valid_src = tmp_path / "inbox" / "keep_me.txt"
    valid_dest = tmp_path / "archive" / "keep_me.txt"
    valid_src.parent.mkdir(parents=True, exist_ok=True)
    valid_src.write_text("payload")

    plan = executor.execute(
        "plan_ops",
        {
            "ops": [
                {"op": "move", "src": str(tmp_path / "missing.txt"), "dest": str(tmp_path / "x.txt")},
                {"op": "move", "src": str(valid_src), "dest": str(valid_dest)},
            ]
        },
    )
    applied = executor.execute(
        "apply_ops",
        {"plan_id": plan["output"]["plan_id"], "stop_on_error": True},
    )

    assert applied["ok"] is False
    assert applied["output"]["failed"] == 1
    assert applied["output"]["skipped"] == 1
    assert valid_src.exists()
    assert not valid_dest.exists()


def test_apply_ops_idempotency_key_replays_without_reexecution(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    src = tmp_path / "inbox" / "draft.txt"
    dest = tmp_path / "archive" / "draft.txt"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("data")

    plan = executor.execute(
        "plan_ops",
        {"ops": [{"op": "move", "src": str(src), "dest": str(dest)}]},
    )
    plan_id = plan["output"]["plan_id"]

    first = executor.execute(
        "apply_ops",
        {"plan_id": plan_id, "idempotency_key": "same-request-1"},
    )
    second = executor.execute(
        "apply_ops",
        {"plan_id": plan_id, "idempotency_key": "same-request-1"},
    )

    assert first["ok"] is True
    assert second["ok"] is True
    assert second["output"]["idempotent_replay"] is True
    assert dest.exists()
    assert not src.exists()


def test_run_automation_executes_allowlisted_shell_script(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    script = tmp_path / "automations" / "Echo_Inputs.sh"
    script.write_text("#!/bin/zsh\necho \"$AI_AGENT_AUTOMATION_INPUTS\"")
    os.chmod(script, 0o700)

    result = executor.execute(
        "run_automation",
        {"name": "Echo Inputs", "inputs": {"key": "value"}},
    )

    assert result["ok"] is True
    output = result["output"]
    assert output["ok"] is True
    payload = json.loads(output["stdout"])
    assert payload == {"key": "value"}


def test_open_item_rejected_when_disabled(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path, enable_open_item=False)
    item = tmp_path / "file.txt"
    item.write_text("x")

    with pytest.raises(ToolExecutionError, match="disabled"):
        executor.execute("open_item", {"path": str(item)})
