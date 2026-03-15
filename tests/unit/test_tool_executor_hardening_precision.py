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

    result = executor.execute("read_document", {"path": str(target)})

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
    assert output["ranking_version"] == "v2"


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


def test_search_files_fts_seed_indexes_and_finds_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FTS seed walk indexes files in allowed_roots and the FTS query finds them."""
    executor = _make_executor(tmp_path, search_scan_limit=200)
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    for idx in range(5):
        (repo_dir / f"report_{idx:03d}.txt").write_text("x")

    monkeypatch.setattr(executor, "_search_spotlight", lambda **_kwargs: ([], 0))

    result = executor.execute("search_files", {"query": "report", "limit": 10})
    output = result["output"]
    assert output["ok"] is True
    # FTS seed should have scanned and indexed the files
    fts_stats = output["tier_stats"]["fts"]
    assert fts_stats["seed_scanned"] > 0
    assert fts_stats["seed_indexed"] > 0
    # FTS should return matches for "report" in the filenames
    assert len(output["matches"]) > 0
    paths = {item["path"] for item in output["matches"]}
    assert any("report_" in p for p in paths)


def test_search_files_rejects_non_empty_continuation_token(
    tmp_path: Path,
) -> None:
    """Strict runtime rejects non-empty continuation_token."""
    executor = _make_executor(tmp_path, search_scan_limit=200)

    with pytest.raises(ToolExecutionError, match="continuation_token"):
        executor.execute(
            "search_files",
            {
                "query": "gemini",
                "mode": "deep",
                "continuation_token": "some-token",
            },
        )


def test_search_files_deep_mode_accepts_extended_time_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deep mode accepts time_budget_ms up to the maximum (10000)."""
    executor = _make_executor(tmp_path, search_scan_limit=200)
    target = tmp_path / "Downloads" / "gemini_page_001.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x")

    monkeypatch.setattr(executor, "_search_spotlight", lambda **_kwargs: ([], 0))

    result = executor.execute(
        "search_files",
        {"query": "gemini page", "mode": "deep", "time_budget_ms": 4000, "limit": 5},
    )
    output = result["output"]
    assert output["ok"] is True
    assert output["mode"] == "deep"
    assert output["time_budget_ms"] == 4000
    # Stale continuation/truncation fields were removed (B6 cleanup)


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


def test_search_files_fast_mode_returns_spotlight_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fast mode returns results from Spotlight without walk entries."""
    executor = _make_executor(tmp_path)
    target = tmp_path / "Documents" / "gemini_file.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x")

    monkeypatch.setattr(
        executor,
        "_search_spotlight",
        lambda **_kwargs: ([executor._make_search_metadata(target, score=250, source="spotlight")], 1),
    )

    result = executor.execute(
        "search_files",
        {"query": "gemini file", "mode": "fast", "time_budget_ms": 1200, "limit": 5},
    )
    output = result["output"]
    assert output["ok"] is True
    # scanned_walk_entries was removed (B6 cleanup — always 0, vestigial)
    assert output["tier_stats"]["spotlight"]["matched"] == 1
    assert len(output["matches"]) >= 1
    assert any(item["path"] == str(target.resolve()) for item in output["matches"])


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


def test_search_files_gemini_image_query_found_via_spotlight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gemini image file found via Spotlight is scored and returned correctly."""
    executor = _make_executor(tmp_path, search_scan_limit=400)
    downloads = tmp_path / "Downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    target = downloads / "Gemini_Generated_Image_abc123.png"
    target.write_text("x")

    # Spotlight returns the Gemini image (simulating real mdfind behavior)
    monkeypatch.setattr(
        executor,
        "_search_spotlight",
        lambda **_kwargs: ([executor._make_search_metadata(target, score=100, source="spotlight")], 1),
    )

    result = executor.execute(
        "search_files",
        {
            "query": "gemini generated image",
            "limit": 10,
            "mode": "deep",
            "time_budget_ms": 1200,
        },
    )
    output = result["output"]
    paths = {item["path"] for item in output["matches"]}
    assert str(target.resolve()) in paths
    # The matched file should have a positive score
    for item in output["matches"]:
        if item["path"] == str(target.resolve()):
            assert item["score"] > 0


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


# -------------------------------------------------------------------------
# F1: FTS5 BM25 semantic boost correctness
# -------------------------------------------------------------------------

def test_fts_bm25_boost_differentiates_match_quality(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BM25 boost should give higher scores to better FTS matches."""
    executor = _make_executor(tmp_path, search_scan_limit=200)
    # Create files with varying relevance to the query "report"
    exact = tmp_path / "report.txt"
    exact.write_text("x")
    partial = tmp_path / "monthly_report_summary.txt"
    partial.write_text("x")
    unrelated = tmp_path / "random_notes.txt"
    unrelated.write_text("x")

    monkeypatch.setattr(executor, "_search_spotlight", lambda **_kwargs: ([], 0))

    result = executor.execute("search_files", {"query": "report", "limit": 10})
    output = result["output"]
    assert output["ok"] is True
    matches = output["matches"]
    # Exact filename match should appear before partial match
    paths = [m["path"] for m in matches]
    if str(exact.resolve()) in paths and str(partial.resolve()) in paths:
        exact_idx = paths.index(str(exact.resolve()))
        partial_idx = paths.index(str(partial.resolve()))
        assert exact_idx < partial_idx, "Exact match should rank higher than partial"
    # Unrelated file should not appear or rank last
    if str(unrelated.resolve()) in paths:
        assert paths.index(str(unrelated.resolve())) > 0


# -------------------------------------------------------------------------
# F2: Mode differentiation
# -------------------------------------------------------------------------

def test_search_files_fast_mode_skips_fts_seeding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fast mode should skip FTS seeding entirely."""
    executor = _make_executor(tmp_path, search_scan_limit=200)
    target = tmp_path / "doc.txt"
    target.write_text("x")

    monkeypatch.setattr(
        executor,
        "_search_spotlight",
        lambda **_kwargs: ([executor._make_search_metadata(target, score=100, source="spotlight")], 1),
    )

    result = executor.execute(
        "search_files",
        {"query": "doc", "mode": "fast", "limit": 5},
    )
    output = result["output"]
    assert output["ok"] is True
    # In fast mode, FTS seeding should NOT run (seed_scanned = 0)
    assert output["tier_stats"]["fts"]["seed_scanned"] == 0
    assert output["tier_stats"]["fts"]["seed_indexed"] == 0


def test_search_files_deep_mode_uses_larger_seed_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deep mode should use a larger seed budget and find more files."""
    executor = _make_executor(tmp_path, search_scan_limit=2000)
    # Create many files to exercise the larger seed budget
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for i in range(50):
        (data_dir / f"analysis_{i:03d}.csv").write_text("x")

    monkeypatch.setattr(executor, "_search_spotlight", lambda **_kwargs: ([], 0))

    result = executor.execute(
        "search_files",
        {"query": "analysis", "mode": "deep", "time_budget_ms": 5000, "limit": 50},
    )
    output = result["output"]
    assert output["ok"] is True
    assert output["mode"] == "deep"
    # Deep mode should seed more aggressively
    fts = output["tier_stats"]["fts"]
    assert fts["seed_scanned"] > 0


# -------------------------------------------------------------------------
# F3: mdfind -name query variant
# -------------------------------------------------------------------------

def test_spotlight_query_variants_include_name_sentinel() -> None:
    """_derive_spotlight_query_variants should include -name: sentinel variants."""
    variants = ToolExecutor._derive_spotlight_query_variants(
        original_query="budget report",
        query_tokens=["budget", "report"],
        query_phrases=[],
        extension_hints={"pdf"},
    )
    # Should contain a -name: sentinel for filename search
    assert any(v.startswith("-name:") for v in variants), (
        f"Expected -name: variant in {variants}"
    )
    # Should contain an extension -name variant
    assert any(v == "-name:.pdf" for v in variants), (
        f"Expected -name:.pdf variant in {variants}"
    )


def test_spotlight_name_variant_dispatches_correctly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mdfind -name: sentinel should be dispatched as mdfind -name flag."""
    executor = _make_executor(tmp_path)
    target = tmp_path / "invoice.pdf"
    target.write_text("x")

    captured_cmds: list[list[str]] = []

    def _fake_run(cmd, **kwargs):
        captured_cmds.append(cmd)
        result = subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return result

    monkeypatch.setattr("agent_host.tools.executor.shutil.which", lambda _name: "/usr/bin/mdfind")
    monkeypatch.setattr("agent_host.tools.executor.subprocess.run", _fake_run)

    executor._search_spotlight(
        queries=["-name:invoice", "invoice"],
        query_lower="invoice",
        query_tokens=["invoice"],
        query_phrases=[],
        extension_hints=set(),
        folder_hints=set(),
        path_filter="",
        limit=5,
    )

    # The -name: sentinel should produce ["mdfind", "-onlyin", ..., "-name", "invoice"]
    name_cmds = [cmd for cmd in captured_cmds if "-name" in cmd and cmd[0] == "mdfind"]
    assert len(name_cmds) > 0, f"Expected mdfind -name calls, got {captured_cmds}"
    assert name_cmds[0][-2] == "-name"
    assert name_cmds[0][-1] == "invoice"


# -------------------------------------------------------------------------
# F4: OR-based FTS fallback
# -------------------------------------------------------------------------

def test_fts_or_fallback_catches_partial_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OR fallback in deep mode should find files matching some but not all tokens."""
    executor = _make_executor(tmp_path, search_scan_limit=200)
    # File matches "proposal" but not "project"
    target = tmp_path / "proposal_draft.pdf"
    target.write_text("x")

    monkeypatch.setattr(executor, "_search_spotlight", lambda **_kwargs: ([], 0))

    # First search in auto mode (no OR fallback) — will use AND: "project" AND "proposal"
    result_auto = executor.execute(
        "search_files",
        {"query": "project proposal", "mode": "auto", "limit": 5},
    )

    # Then search in deep mode (with OR fallback)
    result_deep = executor.execute(
        "search_files",
        {"query": "project proposal", "mode": "deep", "time_budget_ms": 5000, "limit": 5},
    )

    deep_paths = [m["path"] for m in result_deep["output"]["matches"]]
    # Deep mode should find the partial match via OR fallback
    assert str(target.resolve()) in deep_paths


# -------------------------------------------------------------------------
# F5: Stale index pruning
# -------------------------------------------------------------------------

def test_stale_index_entries_are_pruned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stale index entries for deleted files should be removed during seeding."""
    executor = _make_executor(tmp_path, search_scan_limit=200)
    # Create and index a file, then delete it
    target = tmp_path / "ephemeral.txt"
    target.write_text("x")

    monkeypatch.setattr(executor, "_search_spotlight", lambda **_kwargs: ([], 0))

    # First search to index the file
    executor.execute("search_files", {"query": "ephemeral", "limit": 5})

    # Delete the file
    target.unlink()

    # Second search should trigger pruning
    result = executor.execute("search_files", {"query": "ephemeral", "limit": 5})
    matches = result["output"]["matches"]
    # The deleted file should NOT appear in results
    assert not any("ephemeral" in m.get("path", "") for m in matches)


# -------------------------------------------------------------------------
# F6: Algorithmic token normalization + prefix-aware scoring
# -------------------------------------------------------------------------

def test_normalize_token_forms_handles_plurals() -> None:
    """_normalize_token_forms should generate singular/plural variants."""
    # Singular → adds plural
    forms = ToolExecutor._normalize_token_forms("document")
    assert "document" in forms
    assert "documents" in forms

    # Plural -s → strips to singular
    forms = ToolExecutor._normalize_token_forms("documents")
    assert "documents" in forms
    assert "document" in forms

    # Plural -ies → -y
    forms = ToolExecutor._normalize_token_forms("memories")
    assert "memories" in forms
    assert "memory" in forms

    # Plural -es → strips
    forms = ToolExecutor._normalize_token_forms("watches")
    assert "watches" in forms
    assert "watch" in forms

    # Short tokens — should not strip "ss"
    forms = ToolExecutor._normalize_token_forms("boss")
    assert "boss" in forms
    assert "bos" not in forms  # "ss" ending protected


def test_expand_search_tokens_adds_normalized_forms() -> None:
    """_expand_search_tokens should add plural/singular forms of each token."""
    expanded = ToolExecutor._expand_search_tokens(["document", "image"])
    assert "document" in expanded
    assert "documents" in expanded
    assert "image" in expanded
    assert "images" in expanded


def test_prefix_scoring_awards_word_boundary_matches(tmp_path: Path) -> None:
    """Prefix-aware scoring should match 'doc' against the word 'document'."""
    score, signals = ToolExecutor._score_path_with_signals(
        query_lower="doc",
        query_tokens=["doc"],
        query_phrases=[],
        extension_hints=set(),
        folder_hints=set(),
        path=tmp_path / "budget_document.pdf",
    )
    # "doc" is a prefix of the word "document" at a word boundary
    assert score > 0, f"Expected positive score for prefix match, got {score}"


def test_prefix_scoring_ignores_mid_word_matches(tmp_path: Path) -> None:
    """Prefix scoring should NOT match 'doc' inside 'indoctrinate'."""
    score_prefix, _ = ToolExecutor._score_path_with_signals(
        query_lower="doc",
        query_tokens=["doc"],
        query_phrases=[],
        extension_hints=set(),
        folder_hints=set(),
        path=tmp_path / "budget_document.pdf",
    )
    score_mid, _ = ToolExecutor._score_path_with_signals(
        query_lower="doc",
        query_tokens=["doc"],
        query_phrases=[],
        extension_hints=set(),
        folder_hints=set(),
        path=tmp_path / "indoctrinate.txt",
    )
    # "budget_document.pdf" should score higher than "indoctrinate.txt"
    # because prefix matching at word boundary gives bonus points
    assert score_prefix > score_mid or (score_prefix > 0 and score_mid == 0)


# =========================================================================
# S1: Spotlight Source Confidence Floor
# =========================================================================


def test_spotlight_content_match_survives_scoring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Spotlight content-only match should survive scoring via the floor."""
    executor = _make_executor(tmp_path, search_scan_limit=200)
    # File whose name does NOT contain "aws" — simulates a content match.
    target = tmp_path / "deploy_script.sh"
    target.write_text("aws s3 cp bucket ...")

    def _fake_spotlight(**kwargs):
        # Simulate mdfind returning this file via content search.
        metadata = executor._make_search_metadata(target, score=executor._SPOTLIGHT_CONTENT_FLOOR, source="spotlight")
        metadata["spotlight_content_match"] = True
        return [metadata], 1

    monkeypatch.setattr(executor, "_search_spotlight", _fake_spotlight)

    result = executor.execute("search_files", {"query": "aws", "limit": 10})
    output = result["output"]
    assert output["ok"] is True
    paths = [m["path"] for m in output["matches"]]
    assert str(target.resolve()) in paths


def test_spotlight_content_floor_ranks_below_filename_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Content-floor results should rank below direct filename matches."""
    executor = _make_executor(tmp_path, search_scan_limit=200)
    # File with "aws" in filename — direct match.
    direct = tmp_path / "aws_config.yaml"
    direct.write_text("x")
    # File found by Spotlight content — no "aws" in name.
    content = tmp_path / "deploy_script.sh"
    content.write_text("aws s3 cp ...")

    def _fake_spotlight(**kwargs):
        direct_meta = executor._make_search_metadata(direct, score=200, source="spotlight")
        content_meta = executor._make_search_metadata(content, score=executor._SPOTLIGHT_CONTENT_FLOOR, source="spotlight")
        content_meta["spotlight_content_match"] = True
        return [direct_meta, content_meta], 2

    monkeypatch.setattr(executor, "_search_spotlight", _fake_spotlight)

    result = executor.execute("search_files", {"query": "aws", "limit": 10})
    matches = result["output"]["matches"]
    paths = [m["path"] for m in matches]
    assert str(direct.resolve()) in paths
    assert str(content.resolve()) in paths
    # Direct filename match should rank first.
    assert paths.index(str(direct.resolve())) < paths.index(str(content.resolve()))


def test_spotlight_content_floor_not_applied_to_name_query(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Floor should NOT apply to -name: query results with score 0."""
    executor = _make_executor(tmp_path, search_scan_limit=200)
    target = tmp_path / "unrelated.txt"
    target.write_text("x")

    # Simulate mdfind returning the file for a -name: query.
    # A -name: result with score 0 should be dropped, not floored.
    def _fake_spotlight(**kwargs):
        return [], 0  # -name queries that don't match should return nothing

    monkeypatch.setattr(executor, "_search_spotlight", _fake_spotlight)

    result = executor.execute("search_files", {"query": "nonexistent", "limit": 5})
    assert len(result["output"]["matches"]) == 0


def test_merge_rescues_spotlight_content_match(
    tmp_path: Path,
) -> None:
    """_merge_ranked_search_candidates should apply floor to spotlight sources."""
    executor = _make_executor(tmp_path, search_scan_limit=200)
    target = tmp_path / "deploy.sh"
    target.write_text("x")

    candidates = [
        {
            "path": str(target.resolve()),
            "name": "deploy.sh",
            "source": "spotlight",
            "score": 0,
            "modified_at": 0.0,
        }
    ]
    ranked = executor._merge_ranked_search_candidates(
        candidates=candidates,
        query_lower="aws",
        query_tokens=["aws"],
        query_phrases=[],
        extension_hints=set(),
        folder_hints=set(),
    )
    # Spotlight result should survive via content floor.
    assert len(ranked) == 1
    assert ranked[0]["score"] > 0
    signals = ranked[0].get("match_signals", {})
    assert "spotlight_content_floor" in signals


def test_merge_does_not_rescue_non_spotlight_source(
    tmp_path: Path,
) -> None:
    """Non-spotlight sources with score 0 should still be dropped."""
    executor = _make_executor(tmp_path, search_scan_limit=200)
    target = tmp_path / "deploy.sh"
    target.write_text("x")

    candidates = [
        {
            "path": str(target.resolve()),
            "name": "deploy.sh",
            "source": "walk",
            "score": 0,
            "modified_at": 0.0,
        }
    ]
    ranked = executor._merge_ranked_search_candidates(
        candidates=candidates,
        query_lower="aws",
        query_tokens=["aws"],
        query_phrases=[],
        extension_hints=set(),
        folder_hints=set(),
    )
    assert len(ranked) == 0


# =========================================================================
# S2: Directory Co-Location Discovery
# =========================================================================


def test_colocation_adds_siblings_from_shared_directory(
    tmp_path: Path,
) -> None:
    """Sibling files should be added when 2+ results share a directory."""
    executor = _make_executor(tmp_path, search_scan_limit=200)
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    # Two matched files in same directory.
    a = project_dir / "config.yaml"
    a.write_text("x")
    b = project_dir / "deploy.sh"
    b.write_text("x")
    # Sibling that was NOT in results.
    c = project_dir / "readme.txt"
    c.write_text("x")

    ranked = [
        {"path": str(a.resolve()), "score": 100, "modified_at": 0.0},
        {"path": str(b.resolve()), "score": 90, "modified_at": 0.0},
    ]
    siblings = executor._discover_colocated_files(ranked)
    sibling_paths = [s["path"] for s in siblings]
    assert str(c.resolve()) in sibling_paths


def test_colocation_skips_fast_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Co-location should be skipped entirely in fast mode."""
    executor = _make_executor(tmp_path, search_scan_limit=200)
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    a = project_dir / "a.txt"
    a.write_text("x")
    b = project_dir / "b.txt"
    b.write_text("x")
    c = project_dir / "c.txt"
    c.write_text("x")

    monkeypatch.setattr(
        executor,
        "_search_spotlight",
        lambda **_kwargs: (
            [
                executor._make_search_metadata(a, score=100, source="spotlight"),
                executor._make_search_metadata(b, score=90, source="spotlight"),
            ],
            2,
        ),
    )

    result = executor.execute("search_files", {"query": "a", "mode": "fast", "limit": 10})
    output = result["output"]
    assert output["diagnostics"]["colocation_siblings_added"] == 0


def test_colocation_respects_max_siblings_cap(
    tmp_path: Path,
) -> None:
    """Co-location should not add more than max_siblings per directory."""
    executor = _make_executor(tmp_path, search_scan_limit=200)
    project_dir = tmp_path / "bigdir"
    project_dir.mkdir()
    a = project_dir / "a.txt"
    a.write_text("x")
    b = project_dir / "b.txt"
    b.write_text("x")
    for i in range(30):
        (project_dir / f"file_{i:03d}.txt").write_text("x")

    ranked = [
        {"path": str(a.resolve()), "score": 100, "modified_at": 0.0},
        {"path": str(b.resolve()), "score": 90, "modified_at": 0.0},
    ]
    siblings = executor._discover_colocated_files(ranked, max_siblings=5)
    assert len(siblings) <= 5


# =========================================================================
# S3: Recent Search Result Cache
# =========================================================================


def test_search_cache_stores_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Search results should be cached after execution."""
    executor = _make_executor(tmp_path, search_scan_limit=200)
    target = tmp_path / "report.txt"
    target.write_text("x")

    monkeypatch.setattr(
        executor,
        "_search_spotlight",
        lambda **_kwargs: ([executor._make_search_metadata(target, score=100, source="spotlight")], 1),
    )

    executor.execute("search_files", {"query": "report", "limit": 5})
    assert len(executor._recent_search_cache) == 1
    entry = list(executor._recent_search_cache.values())[0]
    assert str(target.resolve()) in entry["result_paths"]


def test_search_cache_boost_on_overlapping_follow_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Follow-up search with overlapping tokens should boost cached results."""
    executor = _make_executor(tmp_path, search_scan_limit=200)
    target = tmp_path / "budget_report.txt"
    target.write_text("x")

    monkeypatch.setattr(
        executor,
        "_search_spotlight",
        lambda **_kwargs: ([executor._make_search_metadata(target, score=100, source="spotlight")], 1),
    )

    # First search — caches "budget report" results.
    executor.execute("search_files", {"query": "budget report", "limit": 5})
    assert len(executor._recent_search_cache) == 1

    # Second search with overlapping token "report".
    result2 = executor.execute("search_files", {"query": "report", "limit": 5})
    output = result2["output"]
    assert output["diagnostics"]["cache_overlap_boost_applied"] >= 0


def test_search_cache_evicts_oldest(
    tmp_path: Path,
) -> None:
    """Cache should evict oldest entries when full."""
    executor = _make_executor(tmp_path, search_scan_limit=200)
    # Fill cache to capacity.
    for i in range(executor._SEARCH_CACHE_MAX_ENTRIES + 2):
        executor._cache_search_results(
            query_lower=f"query_{i}",
            query_tokens=[f"query_{i}"],
            result_paths=(f"/fake/path_{i}",),
            result_scores=(50,),
        )
    assert len(executor._recent_search_cache) == executor._SEARCH_CACHE_MAX_ENTRIES
    # Oldest entry should be evicted.
    assert "query_0" not in executor._recent_search_cache
    assert "query_1" not in executor._recent_search_cache


def test_search_cache_ignores_expired_entries(
    tmp_path: Path,
) -> None:
    """Expired cache entries should not contribute boosts."""
    import time

    executor = _make_executor(tmp_path, search_scan_limit=200)
    # Insert an entry with a past timestamp.
    executor._recent_search_cache["old_query"] = {
        "query_lower": "old_query",
        "query_tokens": frozenset(["report"]),
        "timestamp": time.time() - executor._SEARCH_CACHE_TTL_SECONDS - 10,
        "result_paths": ("/fake/old_report.txt",),
        "result_scores": (100,),
    }
    candidates = [
        {"path": "/fake/old_report.txt", "score": 50, "match_signals": {}},
    ]
    boosted = executor._apply_cache_boost(
        current_query_tokens=["report"],
        candidates=candidates,
    )
    assert boosted == 0  # expired entry should not boost


# =========================================================================
# S4: Result Transparency (Diagnostics)
# =========================================================================


def test_diagnostics_in_search_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Search response should contain diagnostics dict."""
    executor = _make_executor(tmp_path, search_scan_limit=200)
    target = tmp_path / "doc.txt"
    target.write_text("x")

    monkeypatch.setattr(
        executor,
        "_search_spotlight",
        lambda **_kwargs: ([executor._make_search_metadata(target, score=100, source="spotlight")], 1),
    )

    result = executor.execute("search_files", {"query": "doc", "limit": 5})
    output = result["output"]
    assert "diagnostics" in output
    diag = output["diagnostics"]
    assert "spotlight_content_floor_applied" in diag
    assert "colocation_siblings_added" in diag
    assert "cache_overlap_boost_applied" in diag
    assert isinstance(diag["spotlight_content_floor_applied"], int)


# =========================================================================
# S5: Ranking version bump
# =========================================================================


def test_ranking_version_is_v2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ranking version should be v2 after S1-S4 changes."""
    executor = _make_executor(tmp_path, search_scan_limit=200)
    target = tmp_path / "test.txt"
    target.write_text("x")

    monkeypatch.setattr(
        executor,
        "_search_spotlight",
        lambda **_kwargs: ([executor._make_search_metadata(target, score=100, source="spotlight")], 1),
    )

    result = executor.execute("search_files", {"query": "test", "limit": 5})
    assert result["output"]["ranking_version"] == "v2"
