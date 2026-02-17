"""Unit tests for hot reload file scanning behavior."""

from __future__ import annotations

from pathlib import Path

from agent_host.ipc.hot_reload import HotReloadManager


def test_scan_files_excludes_default_noisy_directories(tmp_path: Path) -> None:
    source_file = tmp_path / "agent_host" / "main.py"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text("print('ok')\n")

    ignored_paths = [
        tmp_path / ".venv" / "lib" / "python3.13" / "site.py",
        tmp_path / ".git" / "hooks" / "update.py",
        tmp_path / "build" / "generated.py",
        tmp_path / "__pycache__" / "cache.py",
    ]
    for path in ignored_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# ignored\n")

    manager = HotReloadManager(watch_dir=tmp_path, auto_watch=False)
    scanned = manager._scan_files()

    assert source_file in scanned
    for path in ignored_paths:
        assert path not in scanned

