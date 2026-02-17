"""
Hot Reload System for the AI Agent Backend.

This module provides automatic code reloading when Python files change,
allowing the backend to pick up code changes without a full restart.

Features:
- File system watcher for .py file changes
- Signal-based reload trigger (SIGHUP)
- IPC method for frontend-triggered reload
- Graceful reload that preserves connections
"""

import asyncio
import importlib
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Callable, Optional, Set, Dict, Any
from dataclasses import dataclass, field


logger = logging.getLogger(__name__)


@dataclass
class FileState:
    """Tracks the modification state of a file."""
    path: Path
    mtime: float
    
    @classmethod
    def from_path(cls, path: Path) -> "FileState":
        """Create FileState from a file path."""
        return cls(path=path, mtime=path.stat().st_mtime)
    
    def has_changed(self) -> bool:
        """Check if the file has been modified."""
        try:
            current_mtime = self.path.stat().st_mtime
            return current_mtime > self.mtime
        except FileNotFoundError:
            return True  # File was deleted


@dataclass
class ReloadEvent:
    """Event emitted when code reload is triggered."""
    timestamp: float
    trigger: str  # 'file_change', 'signal', 'ipc'
    changed_files: list[str] = field(default_factory=list)
    success: bool = True
    error: Optional[str] = None


class HotReloadManager:
    """
    Manages hot reloading of Python modules.
    
    This class watches for file changes and triggers module reloading
    when changes are detected. It supports multiple reload triggers:
    - File system changes (polling-based)
    - SIGHUP signal
    - IPC command from frontend
    """
    
    # Modules that should be reloaded (in order)
    RELOAD_MODULES = [
        "agent_host.config",
        "agent_host.system_prompt",  # System prompt (reload to pick up changes)
        "agent_host.gemini_client",
        "agent_host.tool_parser",
        "agent_host.schema_validator",
        "agent_host.ipc.protocol",
        "agent_host.ipc.server",
    ]
    DEFAULT_EXCLUDED_DIR_NAMES = {".git", ".venv", "build", "__pycache__"}
    
    def __init__(
        self,
        watch_dir: Optional[Path] = None,
        poll_interval: float = 2.0,
        auto_watch: bool = True,
    ):
        """
        Initialize the hot reload manager.
        
        Args:
            watch_dir: Directory to watch for changes (default: agent_host/)
            poll_interval: Seconds between file change checks
            auto_watch: Whether to start file watching automatically
        """
        self.watch_dir = watch_dir or Path(__file__).parent.parent
        self.poll_interval = poll_interval
        self.auto_watch = auto_watch
        self._excluded_dir_names = set(self.DEFAULT_EXCLUDED_DIR_NAMES)
        
        self._file_states: Dict[Path, FileState] = {}
        self._running = False
        self._watch_task: Optional[asyncio.Task] = None
        self._reload_callbacks: list[Callable[[ReloadEvent], Any]] = []
        self._last_reload: float = 0.0
        self._reload_cooldown: float = 1.0  # Prevent rapid reloads
        
        # Version tracking for clients
        self._version = int(time.time())
        
        logger.info(f"HotReloadManager initialized, watching: {self.watch_dir}")
    
    @property
    def version(self) -> int:
        """Current code version (timestamp of last reload)."""
        return self._version
    
    def on_reload(self, callback: Callable[[ReloadEvent], Any]) -> None:
        """Register a callback to be called when code is reloaded."""
        self._reload_callbacks.append(callback)
    
    def _scan_files(self) -> Set[Path]:
        """Scan for all Python files in the watch directory."""
        python_files = set()
        for root, dirs, files in os.walk(self.watch_dir):
            dirs[:] = [name for name in dirs if name not in self._excluded_dir_names]
            root_path = Path(root)
            for filename in files:
                if filename.endswith(".py"):
                    python_files.add(root_path / filename)
        return python_files
    
    def _update_file_states(self) -> list[Path]:
        """Update file states and return list of changed files."""
        changed = []
        current_files = self._scan_files()
        
        # Check for modified or new files
        for file_path in current_files:
            if file_path in self._file_states:
                if self._file_states[file_path].has_changed():
                    changed.append(file_path)
                    self._file_states[file_path] = FileState.from_path(file_path)
            else:
                # New file
                self._file_states[file_path] = FileState.from_path(file_path)
                changed.append(file_path)
        
        # Check for deleted files
        deleted = set(self._file_states.keys()) - current_files
        for file_path in deleted:
            del self._file_states[file_path]
            changed.append(file_path)
        
        return changed
    
    def reload_modules(self, trigger: str = "manual", changed_files: Optional[list[str]] = None) -> ReloadEvent:
        """
        Reload all registered modules.
        
        Args:
            trigger: What triggered the reload ('file_change', 'signal', 'ipc', 'manual')
            changed_files: List of files that changed (for logging)
        
        Returns:
            ReloadEvent with reload status
        """
        # Check cooldown
        now = time.time()
        if now - self._last_reload < self._reload_cooldown:
            return ReloadEvent(
                timestamp=now,
                trigger=trigger,
                changed_files=changed_files or [],
                success=False,
                error="Reload cooldown active",
            )
        
        self._last_reload = now
        event = ReloadEvent(
            timestamp=now,
            trigger=trigger,
            changed_files=changed_files or [],
        )
        
        logger.info(f"Starting hot reload (trigger: {trigger})")
        
        reloaded = []
        errors = []
        
        for module_name in self.RELOAD_MODULES:
            if module_name in sys.modules:
                try:
                    module = sys.modules[module_name]
                    importlib.reload(module)
                    reloaded.append(module_name)
                    logger.debug(f"Reloaded: {module_name}")
                except Exception as e:
                    error_msg = f"Failed to reload {module_name}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
        
        if errors:
            event.success = False
            event.error = "; ".join(errors)
        else:
            self._version = int(time.time())
            logger.info(f"Hot reload complete. Reloaded {len(reloaded)} modules. Version: {self._version}")
        
        # Notify callbacks
        for callback in self._reload_callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Reload callback error: {e}")
        
        return event
    
    async def _watch_loop(self) -> None:
        """Background task that watches for file changes."""
        logger.info("File watcher started")
        
        # Initial scan
        self._update_file_states()
        
        while self._running:
            await asyncio.sleep(self.poll_interval)
            
            if not self._running:
                break
            
            changed = self._update_file_states()
            if changed:
                changed_str = [str(p) for p in changed]
                logger.info(f"Detected {len(changed)} changed files")
                self.reload_modules(trigger="file_change", changed_files=changed_str)
    
    async def start(self) -> None:
        """Start the file watcher."""
        if self._running:
            return
        
        self._running = True
        
        if self.auto_watch:
            self._watch_task = asyncio.create_task(self._watch_loop())
        
        # Register signal handler for SIGHUP
        try:
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(
                signal.SIGHUP,
                lambda: self.reload_modules(trigger="signal"),
            )
            logger.info("SIGHUP handler registered")
        except (ValueError, OSError) as e:
            logger.warning(f"Could not register SIGHUP handler: {e}")
    
    async def stop(self) -> None:
        """Stop the file watcher."""
        self._running = False
        
        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass
            self._watch_task = None
        
        logger.info("File watcher stopped")


# Global instance for easy access
_reload_manager: Optional[HotReloadManager] = None


def get_reload_manager() -> HotReloadManager:
    """Get the global HotReloadManager instance."""
    global _reload_manager
    if _reload_manager is None:
        _reload_manager = HotReloadManager()
    return _reload_manager


def init_reload_manager(
    watch_dir: Optional[Path] = None,
    poll_interval: float = 2.0,
    auto_watch: bool = True,
) -> HotReloadManager:
    """Initialize the global HotReloadManager with custom settings."""
    global _reload_manager
    _reload_manager = HotReloadManager(
        watch_dir=watch_dir,
        poll_interval=poll_interval,
        auto_watch=auto_watch,
    )
    return _reload_manager
