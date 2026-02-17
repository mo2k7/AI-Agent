"""Hardening tests for tool executor reliability and precision paths."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_host.planning import UnifiedPlanningSecurityError
from agent_host.tools.executor import ToolExecutionError, ToolExecutor


def _make_executor(
    tmp_path: Path,
    *,
    enable_open_item: bool = False,
    search_scan_limit: int = 200,
) -> ToolExecutor:
    automations_dir = tmp_path / "automations"
    automations_dir.mkdir(parents=True, exist_ok=True)
    return ToolExecutor(
        allowed_roots=[tmp_path],
        automations_dir=automations_dir,
        enable_open_item=enable_open_item,
        search_scan_limit=search_scan_limit,
    )


def test_execute_returns_latency_envelope(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    target = tmp_path / "notes.txt"
    target.write_text("hello")

    result = executor.execute("read_text", {"path": str(target)})

    assert result["ok"] is True
    assert isinstance(result["started_at"], float)
    assert isinstance(result["finished_at"], float)
    assert isinstance(result["latency_ms"], float)
    assert result["finished_at"] >= result["started_at"]
    assert result["latency_ms"] >= 0.0


def test_execute_rejects_non_mapping_arguments(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)

    with pytest.raises(ToolExecutionError, match="arguments must be an object"):
        executor.execute("search_files", ["bad-args"])  # type: ignore[arg-type]


def test_search_files_rejects_non_string_path_filter(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)

    with pytest.raises(ToolExecutionError, match="path_filter"):
        executor.execute("search_files", {"query": "notes", "path_filter": 123})


def test_search_files_rejects_bool_limit(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)

    with pytest.raises(ToolExecutionError, match="limit"):
        executor.execute("search_files", {"query": "notes", "limit": True})


def test_search_files_accepts_tiered_search_arguments(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    target = tmp_path / "Downloads" / "Gemini_Generated_Image_test.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x")

    result = executor.execute(
        "search_files",
        {
            "query": "gemini generated image",
            "mode": "auto",
            "time_budget_ms": 1200,
            "include_hidden": False,
            "max_depth": 8,
            "limit": 5,
        },
    )

    output = result["output"]
    assert output["mode"] == "auto"
    assert output["time_budget_ms"] == 1200
    assert isinstance(output["tier_stats"], dict)
    assert "spotlight" in output["tier_stats"]
    assert "fts" in output["tier_stats"]
    assert "fallback" in output["tier_stats"]
    assert output["ranking_version"] == "v1"


def test_search_files_returns_link_ready_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executor = _make_executor(tmp_path)
    target = tmp_path / "Documents" / "python_notes.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("hello")

    monkeypatch.setattr(executor, "_search_spotlight", lambda **_kwargs: ([], 0))

    result = executor.execute("search_files", {"query": "python", "limit": 5})

    matches = result["output"]["matches"]
    assert matches
    entry = matches[0]
    assert entry["path"] == str(target.resolve())
    assert entry["name"] == "python_notes.txt"
    assert entry["uri"].startswith("file://")
    assert entry["relative_path"] == "Documents/python_notes.txt"
    assert "display_path" in entry and entry["display_path"]


def test_search_files_reports_truncation_reason(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executor = _make_executor(tmp_path, search_scan_limit=200)
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    for idx in range(220):
        (repo_dir / f"file_{idx:03d}.txt").write_text("x")

    monkeypatch.setattr(executor, "_search_spotlight", lambda **_kwargs: ([], 0))

    result = executor.execute("search_files", {"query": "file", "limit": 5})
    output = result["output"]
    assert output["truncated"] is True
    assert "Reached walk scan limit" in output["truncated_reason"]
    assert output["scanned_walk_entries"] == 200
    assert output["search_scan_limit"] == 200


def test_search_files_deep_mode_returns_continuation_token_on_truncation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = _make_executor(tmp_path, search_scan_limit=200)
    big = tmp_path / "Downloads"
    big.mkdir(parents=True, exist_ok=True)
    for idx in range(280):
        (big / f"gemini_{idx:03d}.txt").write_text("x")

    monkeypatch.setattr(executor, "_search_spotlight", lambda **_kwargs: ([], 0))
    executor._search_index_enabled = False

    result = executor.execute(
        "search_files",
        {"query": "gemini", "mode": "deep", "time_budget_ms": 4000, "limit": 10},
    )
    output = result["output"]
    assert output["truncated"] is True
    assert isinstance(output["next_token"], str)
    assert output["next_token"]


def test_search_files_continuation_advances_fallback_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = _make_executor(tmp_path, search_scan_limit=200)
    big = tmp_path / "Downloads"
    big.mkdir(parents=True, exist_ok=True)
    for idx in range(320):
        (big / f"gemini_page_{idx:03d}.txt").write_text("x")

    monkeypatch.setattr(executor, "_search_spotlight", lambda **_kwargs: ([], 0))
    executor._search_index_enabled = False

    first = executor.execute(
        "search_files",
        {"query": "gemini page", "mode": "deep", "time_budget_ms": 4000, "limit": 5},
    )["output"]
    assert first["next_token"]

    second = executor.execute(
        "search_files",
        {
            "query": "gemini page",
            "mode": "deep",
            "time_budget_ms": 4000,
            "limit": 5,
            "continuation_token": first["next_token"],
        },
    )["output"]

    first_paths = {item["path"] for item in first["matches"]}
    second_paths = {item["path"] for item in second["matches"]}
    assert second_paths
    assert first_paths != second_paths


def test_search_files_prioritizes_home_user_folders_before_budget_exhaustion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: ensure Downloads/Desktop are scanned before deep project trees."""
    executor = _make_executor(tmp_path, search_scan_limit=220)
    noisy = tmp_path / "AI Automation Agent macOS"
    noisy.mkdir(parents=True, exist_ok=True)
    for idx in range(260):
        (noisy / f"artifact_{idx:03d}.txt").write_text("noise")

    downloads = tmp_path / "Downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    target = downloads / "Gemini_Generated_Image_nio567nio567nio5.png"
    target.write_text("image")

    monkeypatch.setattr("agent_host.tools.executor.Path.home", lambda: tmp_path)
    monkeypatch.setattr(executor, "_search_spotlight", lambda **_kwargs: ([], 0))

    result = executor.execute("search_files", {"query": "gemini", "limit": 10})
    output = result["output"]
    paths = [item["path"] for item in output["matches"]]
    assert str(target.resolve()) in paths


def test_search_files_fast_mode_avoids_fallback_when_primary_tiers_suffice(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = _make_executor(tmp_path)
    target = tmp_path / "Documents" / "gemini_file.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x")

    monkeypatch.setattr(
        executor,
        "_search_spotlight",
        lambda **_kwargs: ([executor._make_search_metadata(target, score=250, source="spotlight")], 1),
    )

    def _unexpected_fallback(**_kwargs):
        raise AssertionError("fallback tier should not execute in fast mode with primary matches")

    monkeypatch.setattr(executor, "_search_fallback_tier", _unexpected_fallback)

    result = executor.execute(
        "search_files",
        {"query": "gemini file", "mode": "fast", "time_budget_ms": 1200, "limit": 5},
    )
    output = result["output"]
    assert output["scanned_walk_entries"] == 0
    assert output["tier_stats"]["fallback"]["matched"] == 0


def test_tokenize_search_query_removes_conversational_noise_and_maps_aliases() -> None:
    tokens = ToolExecutor._tokenize_search_query(
        "locate the gemini created image i dont know where it is"
    )

    assert "gemini" in tokens
    assert "created" in tokens
    assert "image" in tokens
    # Stopwords should be filtered out
    assert "the" not in tokens
    assert "is" not in tokens
    assert "it" not in tokens


def test_search_files_understands_natural_language_query_for_gemini_images(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = _make_executor(tmp_path, search_scan_limit=400)
    downloads = tmp_path / "Downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    target = downloads / "Gemini_Generated_Image_abc123.png"
    target.write_text("x")

    monkeypatch.setattr(executor, "_search_spotlight", lambda **_kwargs: ([], 0))
    executor._search_index_enabled = False

    result = executor.execute(
        "search_files",
        {
            "query": "locate the gemini created image i dont know where it is",
            "limit": 10,
            "mode": "deep",
            "time_budget_ms": 1200,
        },
    )
    output = result["output"]
    paths = {item["path"] for item in output["matches"]}
    assert str(target.resolve()) in paths


def test_search_spotlight_timeout_falls_back_to_walk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = _make_executor(tmp_path)
    target = tmp_path / "project" / "python.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x")

    monkeypatch.setattr("agent_host.tools.executor.shutil.which", lambda _name: "/usr/bin/mdfind")

    def _raise_timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["mdfind"], timeout=8)

    monkeypatch.setattr("agent_host.tools.executor.subprocess.run", _raise_timeout)

    result = executor.execute("search_files", {"query": "python", "limit": 5})
    paths = [item["path"] for item in result["output"]["matches"]]
    assert str(target.resolve()) in paths


def test_read_text_rejects_boolean_byte_range_values(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    target = tmp_path / "story.txt"
    target.write_text("abcdef")

    with pytest.raises(ToolExecutionError, match="byte_range"):
        executor.execute("read_text", {"path": str(target), "byte_range": [False, 3]})


def test_plan_ops_preserves_index_for_non_mapping_entries(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    src = tmp_path / "a.txt"
    src.write_text("x")

    plan = executor.execute(
        "plan_ops",
        {"ops": ["invalid", {"op": "delete", "src": str(src)}]},
    )
    plan_id = plan["output"]["plan_id"]
    applied = executor.execute("apply_ops", {"plan_id": plan_id})

    assert applied["output"]["failed"] == 1
    first = applied["output"]["results"][0]
    assert first["index"] == 0
    assert first["ok"] is False


def test_plan_ops_handles_null_byte_path_without_crashing(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)

    planned = executor.execute(
        "plan_ops",
        {"ops": [{"op": "delete", "src": "name\x00hidden.txt"}]},
    )

    output = planned["output"]
    assert output["ok"] is False
    issues = output.get("issues", [])
    assert isinstance(issues, list)
    assert any("null byte" in str(issue).lower() for issue in issues)


def test_plan_ops_does_not_send_paths_to_unified_planning(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    src = tmp_path / "inbox" / "a.txt"
    dest = tmp_path / "archive" / "a.txt"
    src.parent.mkdir(parents=True, exist_ok=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("x")

    captured: dict[str, object] = {}

    class _CapturePlanner:
        version = "capture"

        def analyze_complexity(self, *, steps, dependency_count):
            captured["steps"] = steps
            captured["dependency_count"] = dependency_count
            return {"score": 1, "level": "low", "strategy": "linear", "factors": {}}

        def plan_order(self, *, step_count, dependencies):
            captured["step_count"] = step_count
            captured["dependencies"] = dependencies
            return {
                "engine": "unified-planning",
                "engine_version": self.version,
                "engine_name": "capture",
                "status": "SOLVED_SATISFICING",
                "ordered_indices": list(range(step_count)),
            }

    executor._unified_planner = _CapturePlanner()
    planned = executor.execute(
        "plan_ops",
        {"ops": [{"op": "move", "src": str(src), "dest": str(dest)}]},
    )

    assert planned["ok"] is True
    serialized_steps = json.dumps(captured.get("steps", []))
    serialized_deps = json.dumps(captured.get("dependencies", []))
    assert str(src.resolve()) not in serialized_steps
    assert str(dest.resolve()) not in serialized_steps
    assert str(src.resolve()) not in serialized_deps
    assert str(dest.resolve()) not in serialized_deps
    steps = captured.get("steps", [])
    assert isinstance(steps, list)
    assert steps and all(isinstance(step, (list, tuple)) and len(step) == 3 for step in steps)
    for step in steps:
        step_id, op_code, is_valid = step
        assert isinstance(step_id, int) and not isinstance(step_id, bool)
        assert isinstance(op_code, int) and not isinstance(op_code, bool)
        assert isinstance(is_valid, bool)


def test_planner_analyze_sends_abstract_numeric_payload_only(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    src = tmp_path / "inbox" / "sensitive.txt"
    dest = tmp_path / "archive" / "sensitive.txt"
    src.parent.mkdir(parents=True, exist_ok=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("x")

    captured: dict[str, object] = {}

    class _CapturePlanner:
        version = "capture"

        def analyze_complexity(self, *, steps, dependency_count):
            captured["steps"] = steps
            captured["dependency_count"] = dependency_count
            return {"score": 2, "level": "low", "strategy": "linear", "factors": {}}

        def plan_order(self, *, step_count, dependencies):
            _ = (step_count, dependencies)
            return {
                "engine": "unified-planning",
                "engine_version": self.version,
                "engine_name": "capture",
                "status": "SOLVED_SATISFICING",
                "ordered_indices": [],
            }

    executor._unified_planner = _CapturePlanner()
    analyzed = executor.execute(
        "planner",
        {
            "mode": "analyze",
            "goal": f"Audit {src}",
            "ops": [
                {"op": "move", "src": str(src), "dest": str(dest)},
                {"op": "C:/users/private/path-like-op-name", "src": "token", "dest": "out"},
                "invalid-op-entry",
            ],
        },
    )

    assert analyzed["ok"] is True
    steps = captured.get("steps", [])
    assert isinstance(steps, list)
    assert len(steps) == 3
    for step in steps:
        assert isinstance(step, (list, tuple))
        assert len(step) == 3
        step_id, op_code, is_valid = step
        assert isinstance(step_id, int) and not isinstance(step_id, bool)
        assert isinstance(op_code, int) and not isinstance(op_code, bool)
        assert isinstance(is_valid, bool)

    serialized_steps = json.dumps(steps)
    assert str(src.resolve()) not in serialized_steps
    assert str(dest.resolve()) not in serialized_steps
    assert "private" not in serialized_steps.lower()


def test_plan_ops_never_sends_sensitive_path_variants_to_planner(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    captured: dict[str, object] = {}
    variants = [
        "/Users/name/Documents/secret.txt",
        "../secrets/.env",
        "./private/key.pem",
        "~/Library/Application Support/app/config.json",
        "C:\\Users\\name\\Desktop\\passwords.txt",
        "C:/Users/name/Desktop/passwords.txt",
        "\\\\server\\share\\finance.xlsx",
        "\\\\?\\C:\\Users\\name\\AppData\\Local\\token.db",
        "\\\\.\\pipe\\sensitive",
        "file:///Users/name/Downloads/file.txt",
        "smb://server/share/confidential.pdf",
        "afp://nas/share/archive.zip",
        "ftp://host/private.txt",
        "%2FUsers%2Fname%2FSecrets%2Fdb.sqlite",
        "%252FUsers%252Fname%252FSecrets%252Fdb.sqlite",
        "L1VzZXJzL25hbWUvc2VjcmV0LnR4dA==",
        "C:\\PROGRA~1\\Private\\a.txt",
        "file.txt:stream",
        "$HOME/.ssh/id_rsa",
        "%USERPROFILE%\\Desktop\\notes.txt",
        "．．/．．/private.txt",
        "／Users／name／secret.txt",
        "C：＼Users＼name＼secret.txt",
        "dir\u200b/hidden.txt",
        "dir\u2066/rtl.txt\u2069",
        "name\x00hidden.txt",
    ]

    class _CapturePlanner:
        version = "capture"

        def analyze_complexity(self, *, steps, dependency_count):
            captured["steps"] = steps
            captured["dependency_count"] = dependency_count
            return {"score": 1, "level": "low", "strategy": "linear", "factors": {}}

        def plan_order(self, *, step_count, dependencies):
            captured["dependencies"] = dependencies
            return {
                "engine": "unified-planning",
                "engine_version": self.version,
                "engine_name": "capture",
                "status": "SOLVED_SATISFICING",
                "ordered_indices": list(range(step_count)),
            }

    executor._unified_planner = _CapturePlanner()
    ops = [{"op": "delete", "src": variant} for variant in variants]
    planned = executor.execute("plan_ops", {"ops": ops})

    assert isinstance(planned["output"].get("plan_id"), str)
    serialized = json.dumps(
        {
            "steps": captured.get("steps", []),
            "dependencies": captured.get("dependencies", []),
        },
        ensure_ascii=False,
    )
    for variant in variants:
        assert variant not in serialized

    steps = captured.get("steps", [])
    assert isinstance(steps, list)
    assert len(steps) == len(variants)
    for step in steps:
        assert isinstance(step, (list, tuple))
        assert len(step) == 3
        assert isinstance(step[0], int) and not isinstance(step[0], bool)
        assert isinstance(step[1], int) and not isinstance(step[1], bool)
        assert isinstance(step[2], bool)


def test_planner_security_violation_locks_planner_session(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)

    class _FailingPlanner:
        version = "fail"

        def analyze_complexity(self, *, steps, dependency_count):
            _ = (steps, dependency_count)
            raise UnifiedPlanningSecurityError("intentional test security trip")

        def plan_order(self, *, step_count, dependencies):
            _ = (step_count, dependencies)
            raise AssertionError("plan_order should not be reached")

    executor._unified_planner = _FailingPlanner()
    with pytest.raises(ToolExecutionError, match="security policy violation"):
        executor.execute(
            "planner",
            {"mode": "analyze", "goal": "Lock planner", "ops": [{"op": "delete", "src": "x"}]},
        )

    with pytest.raises(ToolExecutionError, match="security-locked"):
        executor.execute(
            "planner",
            {"mode": "analyze", "goal": "Should remain locked", "ops": []},
        )


def test_plan_ops_privacy_payload_reports_strict_policy(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    src = tmp_path / "a.txt"
    src.write_text("x")

    planned = executor.execute("plan_ops", {"ops": [{"op": "delete", "src": str(src)}]})
    privacy = planned["output"].get("privacy", {})

    assert isinstance(privacy, dict)
    assert privacy.get("policy_version") == "v2-strict-no-text"
    assert privacy.get("boundary_payload_mode") == "numeric_boolean_only"
    assert privacy.get("string_payload_blocked") is True
    assert privacy.get("binary_payload_blocked") is True
    assert privacy.get("path_data_sent_to_unified_planning") is False
    assert privacy.get("policy_attestation_verified") is True
    assert privacy.get("package_hash_verified") is True
    assert privacy.get("package_hash_pinned") is False
    assert privacy.get("package_hash_auto_rotate_enabled") is False
    assert isinstance(privacy.get("policy_checksum"), str)
    assert isinstance(privacy.get("package_hash"), str)


def test_apply_ops_rejects_invalid_stop_on_error_type(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    src = tmp_path / "a.txt"
    dest = tmp_path / "b.txt"
    src.write_text("x")
    plan = executor.execute(
        "plan_ops",
        {"ops": [{"op": "move", "src": str(src), "dest": str(dest)}]},
    )

    with pytest.raises(ToolExecutionError, match="stop_on_error"):
        executor.execute(
            "apply_ops",
            {"plan_id": plan["output"]["plan_id"], "stop_on_error": "yes"},
        )


def test_apply_ops_overwrite_policy_overwrite_uses_trash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executor = _make_executor(tmp_path)
    src = tmp_path / "incoming.txt"
    dest = tmp_path / "archive" / "incoming.txt"
    trash = tmp_path / ".test-trash"
    dest.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("new")
    dest.write_text("old")
    monkeypatch.setattr(ToolExecutor, "_trash_directory", staticmethod(lambda: trash))

    plan = executor.execute(
        "plan_ops",
        {
            "ops": [
                {
                    "op": "move",
                    "src": str(src),
                    "dest": str(dest),
                    "overwrite_policy": "overwrite",
                }
            ]
        },
    )
    applied = executor.execute("apply_ops", {"plan_id": plan["output"]["plan_id"]})

    assert applied["ok"] is True
    entry = applied["output"]["results"][0]
    assert entry["ok"] is True
    assert entry["overwrite_policy"] == "overwrite"
    assert Path(entry["overwritten_destination_trashed_to"]).exists()
    assert dest.exists()
    assert dest.read_text() == "new"


def test_run_automation_rejects_invalid_name_characters(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)

    with pytest.raises(ToolExecutionError, match="may only contain"):
        executor.execute("run_automation", {"name": "../danger"})


def test_run_automation_rejects_ambiguous_stem_matches(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    (tmp_path / "automations" / "Backup.sh").write_text("#!/bin/zsh\necho ok")
    (tmp_path / "automations" / "Backup.scpt").write_text("display dialog \"ok\"")

    with pytest.raises(ToolExecutionError, match="ambiguous"):
        executor.execute("run_automation", {"name": "Backup"})


def test_run_automation_rejects_symlink_target_outside_automations(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    outside = tmp_path / "outside.sh"
    outside.write_text("#!/bin/zsh\necho outside")
    os.chmod(outside, 0o700)
    (tmp_path / "automations" / "Outside.sh").symlink_to(outside)

    with pytest.raises(ToolExecutionError, match="must be directly inside"):
        executor.execute("run_automation", {"name": "Outside.sh"})


def test_run_automation_rejects_non_mapping_inputs(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    script = tmp_path / "automations" / "Echo.sh"
    script.write_text("#!/bin/zsh\necho ok")
    os.chmod(script, 0o700)

    with pytest.raises(ToolExecutionError, match="inputs"):
        executor.execute("run_automation", {"name": "Echo.sh", "inputs": ["x"]})


def test_run_automation_timeout_returns_structured_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = _make_executor(tmp_path)
    script = tmp_path / "automations" / "Long.sh"
    script.write_text("#!/bin/zsh\nsleep 1")
    os.chmod(script, 0o700)

    class _FakePopen:
        def __init__(self, *args, **kwargs):
            self.pid = 99999
            self.returncode = -15
            self._call_count = 0

        def communicate(self, timeout=None):
            self._call_count += 1
            if self._call_count == 1:
                raise subprocess.TimeoutExpired(cmd=["test"], timeout=30)
            return ("o" * 40, "e" * 40)

        def terminate(self):
            pass

    monkeypatch.setattr("agent_host.tools.run_automation.subprocess.Popen", _FakePopen)
    monkeypatch.setattr(
        "agent_host.tools.run_automation.os.getpgid",
        lambda pid: (_ for _ in ()).throw(OSError("fake")),
    )

    result = executor.execute("run_automation", {"name": "Long.sh"})
    output = result["output"]
    assert output["ok"] is False
    assert output["timed_out"] is True
    assert output["exit_code"] == -15
    assert output["stdout_total_chars"] == 40
    assert output["stderr_total_chars"] == 40
    assert "timed out" in output["error"].lower()


def test_run_automation_truncates_stdout_and_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = _make_executor(tmp_path)
    script = tmp_path / "automations" / "Echo.sh"
    script.write_text("#!/bin/zsh\necho ok")
    os.chmod(script, 0o700)

    long_stdout = "a" * 17000
    long_stderr = "b" * 17000

    class _FakePopen:
        def __init__(self, *args, **kwargs):
            self.pid = 99999
            self.returncode = 0

        def communicate(self, timeout=None):
            return (long_stdout, long_stderr)

    monkeypatch.setattr("agent_host.tools.run_automation.subprocess.Popen", _FakePopen)

    result = executor.execute("run_automation", {"name": "Echo.sh", "inputs": {"k": "v"}})
    output = result["output"]
    assert output["ok"] is True
    assert output["stdout_truncated"] is True
    assert output["stderr_truncated"] is True
    assert output["stdout_total_chars"] == len(long_stdout)
    assert output["stderr_total_chars"] == len(long_stderr)
    assert len(output["stdout"]) <= 16000
    assert len(output["stderr"]) <= 16000


def test_run_automation_executes_and_sets_inputs(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    script = tmp_path / "automations" / "Echo_Inputs.sh"
    script.write_text("#!/bin/zsh\necho \"$AI_AGENT_AUTOMATION_INPUTS\"")
    os.chmod(script, 0o700)

    result = executor.execute(
        "run_automation",
        {"name": "Echo Inputs", "inputs": {"key": "value"}},
    )

    output = result["output"]
    assert output["ok"] is True
    assert output["matched_via"] == "slug_stem"
    assert json.loads(output["stdout"]) == {"key": "value"}


def test_run_automation_filters_process_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executor = _make_executor(tmp_path)
    script = tmp_path / "automations" / "Show_Secret.sh"
    script.write_text("#!/bin/zsh\necho \"${GOOGLE_API_KEY:-}\"")
    os.chmod(script, 0o700)

    monkeypatch.setenv("GOOGLE_API_KEY", "top-secret")
    monkeypatch.delenv("AI_AGENT_AUTOMATION_ENV_ALLOWLIST", raising=False)

    result = executor.execute("run_automation", {"name": "Show Secret"})

    output = result["output"]
    assert output["ok"] is True
    assert output["stdout"] == ""


def test_browse_web_rejects_insecure_tls_without_debug_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = _make_executor(tmp_path)
    monkeypatch.delenv("AI_AGENT_ALLOW_INSECURE_TLS", raising=False)

    with pytest.raises(ToolExecutionError, match="AI_AGENT_ALLOW_INSECURE_TLS"):
        executor.execute(
            "browse_web",
            {"url": "https://example.com", "verify_ssl": False},
        )


def test_open_item_rejects_terminal_even_when_enabled(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path, enable_open_item=True)
    item = tmp_path / "doc.txt"
    item.write_text("x")

    with pytest.raises(ToolExecutionError, match="not in the allowed list"):
        executor.execute(
            "open_item",
            {"path": str(item), "application": "Terminal"},
        )


def test_open_item_timeout_has_deterministic_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = _make_executor(tmp_path, enable_open_item=True)
    item = tmp_path / "doc.txt"
    item.write_text("x")

    def _raise_timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["open", str(item)], timeout=10)

    monkeypatch.setattr("agent_host.tools.executor.subprocess.run", _raise_timeout)

    with pytest.raises(ToolExecutionError, match="timed out"):
        executor.execute("open_item", {"path": str(item)})
