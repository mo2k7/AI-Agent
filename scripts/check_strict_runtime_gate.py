#!/usr/bin/env python3
"""Strict no-legacy/no-fallback gate for first-party runtime code.

This gate scans backend + UI first-party source directories and fails when
known deprecated compatibility branches or legacy identifiers reappear.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sys


FIRST_PARTY_ROOTS = (
    Path("agent_host"),
    Path("ui") / "AIAgentUI",
)
SOURCE_EXTENSIONS = {".py", ".swift"}
EXCLUDED_PARTS = {"__pycache__", ".build", ".swiftpm", "DerivedData"}


@dataclass(frozen=True)
class GateRule:
    name: str
    pattern: re.Pattern[str]
    scoped_paths: tuple[str, ...] = ()

    def applies_to(self, relative_path: str) -> bool:
        if not self.scoped_paths:
            return True
        return any(relative_path.endswith(scope) for scope in self.scoped_paths)


@dataclass(frozen=True)
class Violation:
    rule_name: str
    path: str
    line: int
    snippet: str


GATE_RULES = (
    GateRule(
        name="Legacy symlink rejection param name",
        pattern=re.compile(r"\breject_symlinks\b"),
    ),
    GateRule(
        name="Legacy web extraction fallback mode",
        pattern=re.compile(r"\bfull_text_fallback\b"),
    ),
    GateRule(
        name="Legacy flashcard parser mode",
        pattern=re.compile(r"\bparseConsecutiveQA\b"),
    ),
    GateRule(
        name="Deprecated screen permission preflight/request APIs",
        pattern=re.compile(r"\bCGPreflightScreenCaptureAccess\b|\bCGRequestScreenCaptureAccess\b"),
    ),
    GateRule(
        name="Legacy executor search fallback tier helper",
        pattern=re.compile(r"\b_search_fallback_tier\b"),
    ),
    GateRule(
        name="Legacy executor search continuation token codec",
        pattern=re.compile(r"\b_(?:encode|decode)_search_continuation_token\b"),
    ),
    GateRule(
        name="Legacy AppState connect API",
        pattern=re.compile(r"\bfunc\s+connect\s*\("),
        scoped_paths=("ui/AIAgentUI/State/AppState.swift",),
    ),
    GateRule(
        name="Legacy backend-launcher development path fallback lookup",
        pattern=re.compile(r"\bcommonDevelopmentPaths\b|\bdevelopmentFallback\b"),
        scoped_paths=("ui/AIAgentUI/IPC/BackendLauncher.swift",),
    ),
    GateRule(
        name="Legacy runtime memory restore/ghost cleanup path",
        pattern=re.compile(
            r"\b_restore_sessions_from_session_db\b"
            r"|\b_cleanup_orphaned_session_files\b"
            r"|\bcleanup_ghost_sessions\b"
        ),
        scoped_paths=(
            "agent_host/memory/store.py",
            "agent_host/memory/manager.py",
            "agent_host/main.py",
        ),
    ),
    GateRule(
        name="Legacy OCR API in modern capture service",
        pattern=re.compile(r"\bVNRecognizeTextRequest\b"),
        scoped_paths=("ui/AIAgentUI/Services/ScreenCaptureService.swift",),
    ),
    GateRule(
        name="UI bulk-delete fallback phrase",
        pattern=re.compile(r"fall(?:ing)?\s+back\s+to\s+session\.delete", re.IGNORECASE),
        scoped_paths=(
            "ui/AIAgentUI/IPC/IPCClient.swift",
            "ui/AIAgentUI/State/AppState.swift",
        ),
    ),
)


def _iter_source_files(workspace_root: Path):
    for root in FIRST_PARTY_ROOTS:
        absolute_root = workspace_root / root
        if not absolute_root.exists():
            continue
        for file_path in absolute_root.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix not in SOURCE_EXTENSIONS:
                continue
            relative = file_path.relative_to(workspace_root)
            if any(part in EXCLUDED_PARTS for part in relative.parts):
                continue
            yield file_path, relative.as_posix()


def scan_for_banned_patterns(workspace_root: Path) -> list[Violation]:
    violations: list[Violation] = []
    for file_path, relative_path in _iter_source_files(workspace_root):
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for rule in GATE_RULES:
            if not rule.applies_to(relative_path):
                continue
            for match in rule.pattern.finditer(content):
                line = content.count("\n", 0, match.start()) + 1
                line_text = content.splitlines()[line - 1].strip()
                violations.append(
                    Violation(
                        rule_name=rule.name,
                        path=relative_path,
                        line=line,
                        snippet=line_text,
                    )
                )
    return violations


def format_violations(violations: list[Violation]) -> str:
    lines = ["Strict runtime gate failed. Remove legacy/fallback code paths:"]
    for item in violations:
        lines.append(f"- [{item.rule_name}] {item.path}:{item.line} -> {item.snippet}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    workspace_root = Path(argv[1]).resolve() if len(argv) > 1 else Path.cwd()
    violations = scan_for_banned_patterns(workspace_root)
    if violations:
        print(format_violations(violations))
        return 1
    print("Strict runtime gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
