"""Regression gate: prevent reintroduction of legacy runtime compatibility paths."""

from __future__ import annotations

from pathlib import Path

from scripts.check_strict_runtime_gate import format_violations, scan_for_banned_patterns


def test_strict_runtime_gate_has_no_legacy_markers() -> None:
    workspace_root = Path(__file__).resolve().parents[2]
    violations = scan_for_banned_patterns(workspace_root)
    assert not violations, format_violations(violations)
