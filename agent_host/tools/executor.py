"""Tool execution runtime for validated tool calls."""

from __future__ import annotations

import collections
import json
import logging
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from agent_host.config import Config
from agent_host.planning import (
    UnifiedPlanningEngine,
    UnifiedPlanningSecurityError,
    UnifiedPlanningUnavailableError,
)


logger = logging.getLogger(__name__)


class ToolExecutionError(RuntimeError):
    """Raised when a tool call cannot be executed safely.

    Attributes:
        error_type: Categorised error kind for structured reporting.
            Common values: ``"validation"``, ``"not_found"``, ``"permission"``,
            ``"timeout"``, ``"dependency"``, ``"internal"``.
        retryable: Hint for the caller — ``True`` when the error may be
            transient (e.g. a timeout or temporary lock).
    """

    def __init__(
        self,
        message: str,
        *,
        error_type: str = "internal",
        retryable: bool = False,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.retryable = retryable


class ToolExecutor:
    """Executes validated tool calls against local resources."""

    _EXCLUDED_TOP_LEVEL_DIRS = {
        # macOS system directories — never search or operate on these.
        "System",
        "Library",
        "bin",
        "sbin",
        "usr",
        "var",
        "etc",
        "tmp",
        "opt",
        "private",
        "cores",
        "dev",
        "Volumes",
        "home",       # macOS NFS automount dir, not the user home
        ".Trash",
        ".fseventsd",
        ".vol",
    }
    # Reduced to ~50 essential stopwords.  The model now provides structured
    # search parameters (extensions, folder_hint) so heavy NLP pre-processing
    # is no longer needed.  _SEARCH_TOKEN_ALIASES has been removed entirely —
    # the model handles synonyms via structured params.
    _SEARCH_STOPWORDS = {
        "a",
        "am",
        "an",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "can",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "he",
        "her",
        "him",
        "his",
        "i",
        "if",
        "in",
        "is",
        "it",
        "its",
        "me",
        "my",
        "no",
        "not",
        "of",
        "on",
        "or",
        "our",
        "she",
        "so",
        "the",
        "to",
        "up",
        "us",
        "was",
        "we",
        "who",
        "will",
        "with",
        "you",
        "your",
    }
    _SEMANTIC_EXTENSION_HINTS = {
        "document": {"pdf", "doc", "docx", "txt", "md", "rtf", "odt", "pages"},
        "documents": {"pdf", "doc", "docx", "txt", "md", "rtf", "odt", "pages"},
        "doc": {"doc", "docx"},
        "manual": {"pdf", "md", "txt", "rtf"},
        "notes": {"txt", "md", "rtf", "docx", "pages"},
        "report": {"pdf", "docx", "xlsx", "csv", "md"},
        "spreadsheet": {"csv", "xls", "xlsx", "numbers"},
        "sheet": {"csv", "xls", "xlsx", "numbers"},
        "presentation": {"ppt", "pptx", "key"},
        "slides": {"ppt", "pptx", "key"},
        "image": {"png", "jpg", "jpeg", "heic", "gif", "webp"},
        "images": {"png", "jpg", "jpeg", "heic", "gif", "webp"},
        "photo": {"jpg", "jpeg", "heic", "png"},
        "photos": {"jpg", "jpeg", "heic", "png"},
        "video": {"mp4", "mov", "mkv", "avi"},
        "videos": {"mp4", "mov", "mkv", "avi"},
        "audio": {"mp3", "wav", "m4a", "flac"},
        "music": {"mp3", "wav", "m4a", "flac"},
        "code": {"py", "js", "ts", "tsx", "swift", "go", "java", "rs", "cpp", "c"},
        "python": {"py"},
        "swift": {"swift"},
        "javascript": {"js", "jsx", "ts", "tsx"},
        "typescript": {"ts", "tsx"},
    }
    _DIRECT_EXTENSION_TOKENS = {
        "c",
        "cc",
        "cpp",
        "csv",
        "doc",
        "docx",
        "go",
        "heic",
        "java",
        "jpeg",
        "jpg",
        "js",
        "json",
        "key",
        "md",
        "mkv",
        "mov",
        "mp3",
        "mp4",
        "numbers",
        "odt",
        "pages",
        "pdf",
        "png",
        "ppt",
        "pptx",
        "py",
        "rs",
        "rtf",
        "sh",
        "swift",
        "ts",
        "tsx",
        "txt",
        "wav",
        "xlsx",
        "xml",
        "yaml",
        "yml",
    }
    _FOLDER_HINTS = {
        "desktop": "desktop",
        "document": "documents",
        "documents": "documents",
        "download": "downloads",
        "downloads": "downloads",
        "movie": "movies",
        "movies": "movies",
        "music": "music",
        "picture": "pictures",
        "pictures": "pictures",
        "photo": "pictures",
        "photos": "pictures",
        "project": "projects",
        "projects": "projects",
    }
    _HOME_PRIORITY_DIRS = (
        "Downloads",
        "Desktop",
        "Documents",
        "Pictures",
        "Movies",
        "Music",
    )
    _HOME_PRIORITY_DIRS_LOWER = {name.lower() for name in _HOME_PRIORITY_DIRS}
    _NOISY_COMPONENTS = {
        ".ds_store",
        ".fseventsd",
        ".git",
        ".hg",
        ".mypy_cache",
        ".pytest_cache",
        ".spotlight-v100",
        ".svn",
        ".trash",
        "__pycache__",
        "cache",
        "caches",
        "index.spotlightv3",
        "library",       # /Library and ~/Library — system/app data, not user files
        "node_modules",
        "spotlight",
    }
    _NOISY_SUFFIXES = {
        ".photoslibrary",
        ".photolibrary",
    }
    _NOISY_PATH_FRAGMENTS = (
        "/database/search/spotlight/",
        "/index.spotlightv3/",
        "/spotlight/",
    )
    _NOISY_FILENAME_PATTERNS = (
        re.compile(r"live\.\d+\.directorystorefile$", re.IGNORECASE),
        re.compile(r"clientstatesmetafile$", re.IGNORECASE),
    )
    _HARD_DELETE_ENV_VAR = "AI_AGENT_ENABLE_HARD_DELETE"
    _TRASH_COLLISION_ATTEMPTS = 100
    _SEARCH_RANKING_VERSION = "v2"
    _SPOTLIGHT_CONTENT_FLOOR = 18       # min score for Spotlight content-only matches
    _MAX_CONTENT_FLOOR_RESULTS = 15     # cap on content-floor results per search
    _SEARCH_CACHE_MAX_ENTRIES = 8
    _SEARCH_CACHE_TTL_SECONDS = 300.0   # 5 minutes
    _SEARCH_CACHE_OVERLAP_BOOST = 14
    _SEARCH_MODE_VALUES = {"auto", "fast", "deep"}
    _OVERWRITE_POLICIES = {"fail", "rename", "overwrite"}
    _PLANNER_PRIVACY_POLICY_VERSION = "v2-strict-no-text"
    _PLANNER_OP_CODES = {
        "move": 1,
        "rename": 2,
        "delete": 3,
        "copy": 4,
    }
    _APPLY_IDEMPOTENCY_CACHE_MAX = 200
    # Safety limits
    _MAX_READ_BYTES = 10 * 1024 * 1024  # 10 MB per read_text call
    _PLAN_TTL_SECONDS = 600.0  # 10 minutes
    _MAX_PLANS = 50
    # Rate limiting: token-bucket style per tool
    # Limits set very high so the model can call tools as many times as needed.
    _RATE_LIMIT_WINDOW_SECONDS = 60.0
    _RATE_LIMIT_MAX_CALLS: dict[str, int] = {
        "search_files": 999999,
        "apply_ops": 999999,
        "planner": 999999,
        "plan_ops": 999999,
        "open_item": 999999,
        "create_directory": 999999,
        "read_document": 999999,
        "browse_web": 999999,
    }
    # Application whitelist for open_item
    _OPEN_ITEM_APP_WHITELIST: set[str] = {
        "finder",
        "preview",
        "textedit",
        "safari",
        "notes",
        "xcode",
        "visual studio code",
        "vlc",
        "quicktime player",
        "pages",
        "numbers",
        "keynote",
        "music",
        "photos",
        "calendar",
        "reminders",
        "mail",
    }

    def __init__(
        self,
        *,
        allowed_roots: Sequence[Path],
        automations_dir: Path,
        enable_open_item: bool,
        search_scan_limit: int,
        planner_engine: Any | None = None,
    ) -> None:
        resolved_roots = [root.expanduser().resolve(strict=False) for root in allowed_roots]
        self.allowed_roots = tuple(dict.fromkeys(resolved_roots))
        self.automations_dir = automations_dir.expanduser().resolve(strict=False)
        self.enable_open_item = enable_open_item
        self.search_scan_limit = max(200, int(search_scan_limit))
        self._plans: dict[str, dict[str, Any]] = {}
        self._search_index_path = self._default_search_index_path()
        self._search_index_enabled = self._initialize_search_index()
        self._search_index_cursor_root = 0
        self._search_index_cursor_path = ""
        # Rate limiting state: tool_name -> list of call timestamps
        self._rate_limit_calls: dict[str, list[float]] = {}
        self._apply_idempotency_cache: dict[str, dict[str, Any]] = {}
        self._recent_search_cache: collections.OrderedDict[str, dict[str, Any]] = collections.OrderedDict()
        self._planner_security_lock_reason = ""
        self._unified_planner = planner_engine or self._build_planner_engine()

        # Import per-tool modules here (not at module level) to avoid
        # circular imports — the tool files import ToolExecutionError from
        # this module.
        from agent_host.tools import (
            apply_ops,
            browse_web,
            create_directory,
            open_item,
            plan_ops,
            planner_tool,
            read_document,
            search_files,
        )

        self._browse_rate_limiter = browse_web.DomainRateLimiter()
        self._browse_robots_cache = browse_web.RobotsTxtCache()
        self._browse_circuit_breaker = browse_web.DomainCircuitBreaker()
        browse_policy = browse_web._load_browse_compliance_policy()
        retention = browse_policy.get("retention", {})
        cache_ttl = float(retention.get("response_cache_ttl_seconds", 120))
        cache_max_entries = int(retention.get("response_cache_max_entries", 64))
        self._browse_response_cache = browse_web.ResponseCache(
            max_entries=max(8, cache_max_entries),
            ttl_seconds=max(30.0, cache_ttl),
        )
        incident_cfg = browse_policy.get("incident_response", {})
        self._browse_incident_monitor = browse_web.BrowseIncidentMonitor(
            threshold=int(incident_cfg.get("challenge_spike_threshold", 6)),
            window_seconds=float(incident_cfg.get("window_seconds", 300)),
            cooldown_seconds=float(incident_cfg.get("cooldown_seconds", 600)),
            incident_log_path=str(
                incident_cfg.get(
                    "incident_log_path",
                    Path.home()
                    / "Library"
                    / "Application Support"
                    / "AIAgent"
                    / "security"
                    / "browse_incidents.jsonl",
                )
            ),
        )

        self._handlers: dict[str, Callable[[Mapping[str, Any]], dict[str, Any]]] = {
            "search_files": lambda args: search_files.handle(self, args),
            "read_document": lambda args: read_document.handle(self, args),
            "planner": lambda args: planner_tool.handle(self, args),
            "plan_ops": lambda args: plan_ops.handle(self, args),
            "apply_ops": lambda args: apply_ops.handle(self, args),
            "open_item": lambda args: open_item.handle(self, args),
            "create_directory": lambda args: create_directory.handle(self, args),
            "browse_web": lambda args: browse_web.handle(self, args),
        }

    @classmethod
    def from_config(cls, config: Config) -> "ToolExecutor":
        return cls(
            allowed_roots=config.allowed_roots,
            automations_dir=config.automations_dir,
            enable_open_item=config.enable_open_item,
            search_scan_limit=config.search_scan_limit,
        )

    def _check_rate_limit(self, tool_name: str) -> None:
        """Enforce per-tool rate limiting using a sliding window."""
        max_calls = self._RATE_LIMIT_MAX_CALLS.get(tool_name)
        if max_calls is None:
            return
        now = time.time()
        window_start = now - self._RATE_LIMIT_WINDOW_SECONDS
        calls = self._rate_limit_calls.setdefault(tool_name, [])
        # Prune old entries
        calls[:] = [ts for ts in calls if ts > window_start]
        if len(calls) >= max_calls:
            raise ToolExecutionError(
                f"Rate limit exceeded for '{tool_name}': max {max_calls} calls "
                f"per {int(self._RATE_LIMIT_WINDOW_SECONDS)}s window"
            )
        calls.append(now)

    def _prune_expired_plans(self) -> int:
        """Remove plans older than _PLAN_TTL_SECONDS. Returns count removed."""
        now = time.time()
        expired = [
            plan_id
            for plan_id, plan in self._plans.items()
            if (now - plan.get("created_at", 0)) > self._PLAN_TTL_SECONDS
        ]
        for plan_id in expired:
            del self._plans[plan_id]
        return len(expired)

    def _build_planner_engine(self) -> UnifiedPlanningEngine:
        try:
            return UnifiedPlanningEngine()
        except (UnifiedPlanningUnavailableError, UnifiedPlanningSecurityError) as exc:
            raise ToolExecutionError(
                "Secure unified-planning engine initialization failed. "
                "Install and configure 'unified-planning' (Apache-2.0) before running the agent. "
                f"Details: {exc}"
            ) from exc

    def _planner_privacy_payload(self) -> dict[str, Any]:
        policy_checksum = getattr(self._unified_planner, "policy_checksum", "")
        package_hash = getattr(self._unified_planner, "package_hash", "")
        return {
            "policy_version": self._PLANNER_PRIVACY_POLICY_VERSION,
            "boundary_payload_mode": "numeric_boolean_only",
            "string_payload_blocked": True,
            "binary_payload_blocked": True,
            "path_data_sent_to_unified_planning": False,
            "network_disabled_during_planning": True,
            "planner_security_locked": bool(self._planner_security_lock_reason),
            "policy_checksum": str(policy_checksum),
            "policy_attestation_verified": bool(
                getattr(self._unified_planner, "policy_attestation_verified", False)
            ),
            "package_hash": str(package_hash),
            "package_hash_verified": bool(
                getattr(self._unified_planner, "package_hash_verified", False)
            ),
            "package_hash_pinned": bool(
                getattr(self._unified_planner, "package_hash_pinned", False)
            ),
            "package_hash_auto_rotate_enabled": bool(
                getattr(self._unified_planner, "package_hash_auto_rotate_enabled", False)
            ),
        }

    def _raise_if_planner_locked(self) -> None:
        if self._planner_security_lock_reason:
            raise ToolExecutionError(
                "Planner is security-locked for this session due to a prior policy violation: "
                f"{self._planner_security_lock_reason}"
            )

    @classmethod
    def _assert_no_text_boundary_payload(cls, payload: Any, *, context: str) -> None:
        if isinstance(payload, str):
            raise ToolExecutionError(f"{context} must not contain string values")
        if isinstance(payload, (bytes, bytearray, memoryview)):
            raise ToolExecutionError(f"{context} must not contain binary values")
        if payload is None:
            return
        if isinstance(payload, bool):
            return
        if isinstance(payload, int):
            return
        if isinstance(payload, (list, tuple, set, frozenset)):
            for value in payload:
                cls._assert_no_text_boundary_payload(value, context=context)
            return
        raise ToolExecutionError(
            f"{context} contains unsupported type for planner boundary: {type(payload).__name__}"
        )

    def _planner_analyze_complexity(
        self,
        *,
        steps: list[tuple[int, int, bool]],
        dependency_count: int,
    ) -> dict[str, Any]:
        self._raise_if_planner_locked()
        self._assert_no_text_boundary_payload(steps, context="planner steps")
        self._assert_no_text_boundary_payload(dependency_count, context="planner dependency_count")
        try:
            return self._unified_planner.analyze_complexity(
                steps=steps,
                dependency_count=dependency_count,
            )
        except UnifiedPlanningSecurityError as exc:
            self._planner_security_lock_reason = str(exc).strip() or exc.__class__.__name__
            raise ToolExecutionError(
                "Planner security policy violation detected; planner has been locked for this session"
            ) from exc
        except UnifiedPlanningUnavailableError as exc:
            raise ToolExecutionError(f"Planner unavailable: {exc}") from exc

    def _planner_plan_order(
        self,
        *,
        step_count: int,
        dependencies: list[tuple[int, int]],
    ) -> dict[str, Any]:
        self._raise_if_planner_locked()
        self._assert_no_text_boundary_payload(step_count, context="planner step_count")
        self._assert_no_text_boundary_payload(dependencies, context="planner dependencies")
        try:
            return self._unified_planner.plan_order(
                step_count=step_count,
                dependencies=dependencies,
            )
        except UnifiedPlanningSecurityError as exc:
            self._planner_security_lock_reason = str(exc).strip() or exc.__class__.__name__
            raise ToolExecutionError(
                "Planner security policy violation detected; planner has been locked for this session"
            ) from exc
        except UnifiedPlanningUnavailableError as exc:
            raise ToolExecutionError(f"Planner unavailable: {exc}") from exc

    def execute(self, tool_name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        handler = self._handlers.get(tool_name)
        if handler is None:
            raise ToolExecutionError(f"Unsupported tool: {tool_name}", error_type="not_found")
        if not isinstance(arguments, Mapping):
            raise ToolExecutionError(f"Tool '{tool_name}' arguments must be an object", error_type="validation")

        # Rate limiting
        self._check_rate_limit(tool_name)

        started_at = time.time()
        started_perf = time.perf_counter()

        try:
            output = handler(arguments)
        except ToolExecutionError:
            raise
        except Exception as exc:  # pragma: no cover - defensive wrapper
            raise ToolExecutionError(self._format_unexpected_tool_error(tool_name, exc)) from exc

        if not isinstance(output, Mapping):
            raise ToolExecutionError(f"Tool '{tool_name}' returned invalid output payload")

        finished_at = time.time()
        latency_ms = max(0.0, (time.perf_counter() - started_perf) * 1000.0)
        output_payload = dict(output)

        return {
            "tool": tool_name,
            "ok": bool(output_payload.get("ok", True)),
            "timestamp": finished_at,
            "started_at": started_at,
            "finished_at": finished_at,
            "latency_ms": round(latency_ms, 3),
            "output": output_payload,
        }

    @staticmethod
    def _format_unexpected_tool_error(tool_name: str, exc: BaseException) -> str:
        detail = str(exc).strip()
        if detail:
            return f"Tool '{tool_name}' failed with {exc.__class__.__name__}: {detail}"
        return f"Tool '{tool_name}' failed with {exc.__class__.__name__}"

    @staticmethod
    def _coerce_int(
        value: Any,
        *,
        argument_name: str,
        min_value: int,
        max_value: int,
        default: int,
    ) -> int:
        if value is None:
            return default
        if isinstance(value, bool):
            raise ToolExecutionError(
                f"{argument_name} must be an integer between {min_value} and {max_value}"
            )
        try:
            coerced = int(value)
        except (TypeError, ValueError) as exc:
            raise ToolExecutionError(
                f"{argument_name} must be an integer between {min_value} and {max_value}"
            ) from exc
        return max(min_value, min(max_value, coerced))

    @staticmethod
    def _is_enabled_env_var(name: str) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return False
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    def _default_search_index_path(self) -> Path:
        """Resolve where persistent search index data should live."""
        home = Path.home().expanduser().resolve(strict=False)
        if any(root == home or root in home.parents for root in self.allowed_roots):
            return home / "Library" / "Application Support" / "AIAgent" / "search" / "index.db"
        base = self.allowed_roots[0] if self.allowed_roots else Path.cwd()
        return base / ".ai-agent-search" / "index.db"

    @contextmanager
    def _open_search_index(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._search_index_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")
        try:
            yield conn
        finally:
            conn.close()

    def _initialize_search_index(self) -> bool:
        """Initialize SQLite + FTS5 storage for semantic file retrieval."""
        candidates: list[Path] = [self._search_index_path]
        if self.allowed_roots:
            candidates.append(self.allowed_roots[0] / ".ai-agent-search" / "index.db")
        candidates.append(Path("/tmp") / "ai-agent-search" / "index.db")

        tried: set[Path] = set()
        for candidate in candidates:
            normalized = candidate.expanduser().resolve(strict=False)
            if normalized in tried:
                continue
            tried.add(normalized)
            if self._initialize_search_index_at(normalized):
                self._search_index_path = normalized
                return True
        return False

    def _initialize_search_index_at(self, path: Path) -> bool:
        previous_path = self._search_index_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._search_index_path = path
            with self._open_search_index() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS search_files (
                        path TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        parent TEXT NOT NULL,
                        ext TEXT NOT NULL,
                        size_bytes INTEGER NOT NULL,
                        created_at REAL NOT NULL,
                        modified_at REAL NOT NULL,
                        display_path TEXT NOT NULL,
                        relative_path TEXT NOT NULL,
                        uri TEXT NOT NULL,
                        source TEXT NOT NULL,
                        updated_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS search_files_fts
                    USING fts5(
                        path UNINDEXED,
                        name,
                        parent,
                        tokens,
                        tokenize='unicode61'
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_search_files_modified_at
                    ON search_files(modified_at DESC)
                    """
                )
                conn.commit()
            return True
        except (sqlite3.Error, OSError) as init_exc:
            logger.warning("Search index initialization failed at %s: %s", path, init_exc)
            self._search_index_path = previous_path
            return False

    def _build_fts_query(
        self,
        *,
        query_lower: str,
        query_tokens: list[str],
        query_phrases: list[str],
    ) -> str:
        terms: list[str] = []
        for phrase in query_phrases[:2]:
            cleaned = phrase.strip().replace('"', "")
            if cleaned:
                terms.append(f'"{cleaned}"')
        for token in query_tokens[:8]:
            # Strip all non-alphanumeric chars to prevent FTS5 operator injection
            normalized = re.sub(r"[^a-z0-9]", "", token.lower())
            if not normalized:
                continue
            terms.append(f'"{normalized}"*')
        if terms:
            return " AND ".join(dict.fromkeys(terms))
        fallback = re.sub(r"\s+", " ", query_lower.strip().replace('"', ""))
        if not fallback:
            return ""
        return " AND ".join(
            f'"{re.sub(r"[^a-z0-9]", "", part)}"*'
            for part in fallback.split(" ")
            if re.sub(r"[^a-z0-9]", "", part)
        )

    def _build_fts_query_or(
        self,
        *,
        query_lower: str,
        query_tokens: list[str],
        query_phrases: list[str],
    ) -> str:
        """Build an OR-joined FTS5 query for broader recall (deep mode fallback)."""
        terms: list[str] = []
        for phrase in query_phrases[:2]:
            cleaned = phrase.strip().replace('"', "")
            if cleaned:
                terms.append(f'"{cleaned}"')
        for token in query_tokens[:8]:
            normalized = re.sub(r"[^a-z0-9]", "", token.lower())
            if not normalized:
                continue
            terms.append(f'"{normalized}"*')
        if terms:
            return " OR ".join(dict.fromkeys(terms))
        fallback = re.sub(r"\s+", " ", query_lower.strip().replace('"', ""))
        if not fallback:
            return ""
        return " OR ".join(
            f'"{re.sub(r"[^a-z0-9]", "", part)}"*'
            for part in fallback.split(" ")
            if re.sub(r"[^a-z0-9]", "", part)
        )

    def _upsert_search_index_entries(self, rows: list[dict[str, Any]]) -> int:
        if not self._search_index_enabled or not rows:
            return 0
        upserted = 0
        now = time.time()
        try:
            with self._open_search_index() as conn:
                for row in rows:
                    path = str(row.get("path", "")).strip()
                    if not path:
                        continue
                    name = str(row.get("name", "")).strip() or Path(path).name
                    parent = str(Path(path).parent)
                    ext = str(Path(path).suffix.lower().lstrip("."))
                    try:
                        size_bytes = int(row.get("size_bytes", 0))
                    except (ValueError, TypeError):
                        size_bytes = 0
                    try:
                        created_at = float(row.get("created_at", now))
                    except (ValueError, TypeError):
                        created_at = now
                    try:
                        modified_at = float(row.get("modified_at", now))
                    except (ValueError, TypeError):
                        modified_at = now
                    display_path = str(row.get("display_path", "")).strip() or path
                    relative_path = str(row.get("relative_path", "")).strip() or path
                    uri = str(row.get("uri", "")).strip()
                    source = str(row.get("source", "index")).strip() or "index"
                    token_blob = " ".join(
                        self._tokenize_search_query(f"{name.lower()} {relative_path.lower()} {path.lower()}")
                    )
                    conn.execute(
                        """
                        INSERT INTO search_files (
                            path, name, parent, ext, size_bytes, created_at, modified_at,
                            display_path, relative_path, uri, source, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(path) DO UPDATE SET
                            name=excluded.name,
                            parent=excluded.parent,
                            ext=excluded.ext,
                            size_bytes=excluded.size_bytes,
                            created_at=excluded.created_at,
                            modified_at=excluded.modified_at,
                            display_path=excluded.display_path,
                            relative_path=excluded.relative_path,
                            uri=excluded.uri,
                            source=excluded.source,
                            updated_at=excluded.updated_at
                        """,
                        (
                            path,
                            name,
                            parent,
                            ext,
                            size_bytes,
                            created_at,
                            modified_at,
                            display_path,
                            relative_path,
                            uri,
                            source,
                            now,
                        ),
                    )
                    conn.execute("DELETE FROM search_files_fts WHERE path = ?", (path,))
                    conn.execute(
                        """
                        INSERT INTO search_files_fts(path, name, parent, tokens)
                        VALUES (?, ?, ?, ?)
                        """,
                        (path, name, parent, token_blob),
                    )
                    upserted += 1
                conn.commit()
        except sqlite3.Error as exc:
            logger.warning("Search index upsert failed: %s", exc)
            return 0
        return upserted

    def _prune_stale_index_entries(self, max_checks: int = 100) -> int:
        """Remove FTS index entries for files that no longer exist.

        Checks the oldest entries first (most likely to be stale).
        Called during incremental seeding with a small budget.
        """
        if not self._search_index_enabled:
            return 0
        removed = 0
        try:
            with self._open_search_index() as conn:
                rows = conn.execute(
                    "SELECT path FROM search_files ORDER BY updated_at ASC LIMIT ?",
                    (max_checks,),
                ).fetchall()
                for row in rows:
                    if not Path(row["path"]).exists():
                        conn.execute("DELETE FROM search_files WHERE path = ?", (row["path"],))
                        conn.execute("DELETE FROM search_files_fts WHERE path = ?", (row["path"],))
                        removed += 1
                if removed:
                    conn.commit()
        except sqlite3.Error as exc:
            logger.debug("Stale index pruning failed: %s", exc)
        return removed

    def _seed_search_index_incremental(
        self,
        *,
        query_tokens: list[str],
        folder_hints: set[str],
        include_hidden: bool,
        max_depth: int | None,
        max_entries: int,
        max_seconds: float,
    ) -> dict[str, object]:
        if not self._search_index_enabled or max_entries <= 0 or max_seconds <= 0:
            return {"indexed": 0, "scanned": 0, "completed_cycle": False}

        # Prune stale entries before seeding new ones (lightweight, ~100 checks).
        self._prune_stale_index_entries(max_checks=100)

        targets: list[tuple[Path, set[str]]] = []
        for root in self.allowed_roots:
            if not root.exists():
                continue
            targets.extend(self._ordered_walk_targets(root))
        if not targets:
            return {"indexed": 0, "scanned": 0, "completed_cycle": False}

        start = time.monotonic()
        scanned_entries = 0
        collected: list[dict[str, Any]] = []
        cursor_index = self._search_index_cursor_root % len(targets)
        resume_after = self._search_index_cursor_path
        cycle_completed = False

        def _time_exhausted() -> bool:
            return (time.monotonic() - start) >= max_seconds

        processed_targets = 0
        while processed_targets < len(targets):
            walk_root, top_level_skip_names = targets[cursor_index]
            if walk_root.exists():
                for current_root, dirnames, filenames in os.walk(walk_root):
                    current_root_path = Path(current_root)
                    try:
                        relative_root = current_root_path.relative_to(walk_root)
                    except ValueError:
                        relative_root = Path(".")

                    if self._is_excluded_relative_path(relative_root):
                        dirnames[:] = []
                        continue

                    depth = 0 if relative_root == Path(".") else len(relative_root.parts)
                    if max_depth is not None and depth >= max_depth:
                        dirnames[:] = []

                    filtered_dirs: list[str] = []
                    for name in dirnames:
                        if not include_hidden and name.startswith("."):
                            continue
                        if relative_root == Path(".") and name in top_level_skip_names:
                            continue
                        relative_child = (
                            relative_root / name if relative_root != Path(".") else Path(name)
                        )
                        if self._is_excluded_relative_path(relative_child):
                            continue
                        if self._path_has_noisy_components(current_root_path / name):
                            continue
                        filtered_dirs.append(name)
                    filtered_dirs.sort(
                        key=lambda item: self._directory_sort_key(
                            item,
                            query_tokens=query_tokens,
                            folder_hints=folder_hints,
                        )
                    )
                    dirnames[:] = filtered_dirs

                    for filename in sorted(filenames):
                        if not include_hidden and filename.startswith("."):
                            continue

                        path = current_root_path / filename
                        scanned_entries += 1

                        if resume_after:
                            if str(path) <= resume_after:
                                continue
                            resume_after = ""

                        if self._path_has_noisy_components(path):
                            continue
                        if not path.is_file():
                            continue
                        try:
                            collected.append(self._make_search_metadata(path, score=0, source="index"))
                        except OSError:
                            continue

                        if len(collected) >= max_entries or _time_exhausted():
                            self._search_index_cursor_root = cursor_index
                            self._search_index_cursor_path = str(path)
                            upserted = self._upsert_search_index_entries(collected)
                            return {
                                "indexed": upserted,
                                "scanned": scanned_entries,
                                "completed_cycle": False,
                            }

            cursor_index = (cursor_index + 1) % len(targets)
            self._search_index_cursor_path = ""
            processed_targets += 1

        self._search_index_cursor_root = cursor_index
        self._search_index_cursor_path = ""
        cycle_completed = True
        upserted = self._upsert_search_index_entries(collected)
        return {"indexed": upserted, "scanned": scanned_entries, "completed_cycle": cycle_completed}

    def _query_search_index(
        self,
        *,
        query_lower: str,
        query_tokens: list[str],
        query_phrases: list[str],
        extension_hints: set[str],
        folder_hints: set[str],
        path_filter: str,
        limit: int,
        fts_fallback: bool = False,
        fts_tokens: list[str] | None = None,
    ) -> tuple[list[dict[str, Any]], int, bool]:
        """Returns (results, scanned_count, fts_error_flag).

        ``fts_tokens`` are used for FTS MATCH query building (defaults to
        ``query_tokens``).  Expanded tokens (plural/singular forms) can break
        AND semantics so callers should pass the core (pre-expansion) tokens.
        ``query_tokens`` (expanded) are still used for path scoring.
        """
        if not self._search_index_enabled:
            return [], 0, False

        effective_fts_tokens = fts_tokens if fts_tokens is not None else query_tokens
        fts_query = self._build_fts_query(
            query_lower=query_lower,
            query_tokens=effective_fts_tokens,
            query_phrases=query_phrases,
        )
        if not fts_query:
            return [], 0, False

        rows: list[sqlite3.Row] = []
        try:
            with self._open_search_index() as conn:
                if path_filter:
                    escaped_filter = path_filter.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                    rows = list(
                        conn.execute(
                            """
                            SELECT sf.path, sf.name, sf.display_path, sf.relative_path, sf.uri,
                                   sf.created_at, sf.modified_at, sf.size_bytes, sf.source,
                                   bm25(search_files_fts) AS fts_rank
                            FROM search_files_fts
                            JOIN search_files sf ON sf.path = search_files_fts.path
                            WHERE search_files_fts MATCH ?
                              AND lower(sf.path) LIKE ? ESCAPE '\\'
                            ORDER BY fts_rank ASC, sf.modified_at DESC
                            LIMIT ?
                            """,
                            (fts_query, f"%{escaped_filter}%", max(limit * 6, limit)),
                        )
                    )
                else:
                    rows = list(
                        conn.execute(
                            """
                            SELECT sf.path, sf.name, sf.display_path, sf.relative_path, sf.uri,
                                   sf.created_at, sf.modified_at, sf.size_bytes, sf.source,
                                   bm25(search_files_fts) AS fts_rank
                            FROM search_files_fts
                            JOIN search_files sf ON sf.path = search_files_fts.path
                            WHERE search_files_fts MATCH ?
                            ORDER BY fts_rank ASC, sf.modified_at DESC
                            LIMIT ?
                            """,
                            (fts_query, max(limit * 6, limit)),
                        )
                    )
        except sqlite3.Error as fts_exc:
            logger.warning("FTS query failed: %s", fts_exc)
            return [], 0, True

        results: list[dict[str, Any]] = []
        scanned = len(rows)
        for row in rows:
            path = Path(str(row["path"])).expanduser().resolve(strict=False)
            if not self._path_within_allowed_roots(path):
                continue
            if self._path_is_excluded(path):
                continue
            if not path.exists() or not path.is_file():
                continue

            base_score, signals = self._score_path_with_signals(
                query_lower=query_lower,
                query_tokens=query_tokens,
                query_phrases=query_phrases,
                extension_hints=extension_hints,
                folder_hints=folder_hints,
                path=path,
            )
            if base_score <= 0:
                continue
            try:
                metadata = self._make_search_metadata(path, score=base_score, source="index")
            except OSError:
                continue
            fts_rank_raw = row["fts_rank"]
            fts_rank = float(fts_rank_raw) if isinstance(fts_rank_raw, (int, float)) else 0.0
            # FTS5 bm25() returns negative values; more negative = better match.
            # -fts_rank converts to positive so better matches get higher boosts.
            semantic_boost = min(60.0, max(0.0, -fts_rank * 8.0))
            metadata["score"] = int(base_score + semantic_boost)
            metadata["match_signals"] = {
                **signals,
                "semantic_boost": round(semantic_boost, 3),
                "fts_rank": round(fts_rank, 6),
            }
            results.append(metadata)

        # --- OR-based fallback for deep mode (F4) ---
        # When AND query returns fewer results than requested and fts_fallback is
        # enabled, re-query with OR to catch partial matches.
        if fts_fallback and len(results) < limit:
            or_query = self._build_fts_query_or(
                query_lower=query_lower,
                query_tokens=effective_fts_tokens,
                query_phrases=query_phrases,
            )
            if or_query and or_query != fts_query:
                seen_paths = {r["path"] for r in results}
                try:
                    with self._open_search_index() as conn:
                        or_sql = """
                            SELECT sf.path, sf.name, sf.display_path, sf.relative_path, sf.uri,
                                   sf.created_at, sf.modified_at, sf.size_bytes, sf.source,
                                   bm25(search_files_fts) AS fts_rank
                            FROM search_files_fts
                            JOIN search_files sf ON sf.path = search_files_fts.path
                            WHERE search_files_fts MATCH ?
                            ORDER BY fts_rank ASC, sf.modified_at DESC
                            LIMIT ?
                        """
                        or_rows = list(conn.execute(or_sql, (or_query, max(limit * 4, limit))))
                except sqlite3.Error:
                    or_rows = []
                for row in or_rows:
                    if len(results) >= limit * 6:
                        break
                    path = Path(str(row["path"])).expanduser().resolve(strict=False)
                    if str(path) in seen_paths:
                        continue
                    if not self._path_within_allowed_roots(path):
                        continue
                    if self._path_is_excluded(path):
                        continue
                    if not path.exists() or not path.is_file():
                        continue
                    base_score, or_signals = self._score_path_with_signals(
                        query_lower=query_lower,
                        query_tokens=query_tokens,
                        query_phrases=query_phrases,
                        extension_hints=extension_hints,
                        folder_hints=folder_hints,
                        path=path,
                    )
                    if base_score <= 0:
                        continue
                    try:
                        metadata = self._make_search_metadata(path, score=base_score, source="index")
                    except OSError:
                        continue
                    or_fts_rank = float(row["fts_rank"]) if isinstance(row["fts_rank"], (int, float)) else 0.0
                    or_boost = min(60.0, max(0.0, -or_fts_rank * 8.0))
                    metadata["score"] = int(base_score + or_boost)
                    metadata["match_signals"] = {
                        **or_signals,
                        "semantic_boost": round(or_boost, 3),
                        "fts_rank": round(or_fts_rank, 6),
                        "or_fallback": True,
                    }
                    results.append(metadata)
                    seen_paths.add(str(path))
                    scanned += len(or_rows)

        return results, scanned, False

    # ------------------------------------------------------------------
    # path + policy helpers
    # ------------------------------------------------------------------
    def _path_within_allowed_roots(self, path: Path) -> bool:
        for root in self.allowed_roots:
            if path == root or root in path.parents:
                return True
        return False

    def _is_excluded_relative_path(self, relative: Path) -> bool:
        if not relative.parts:
            return False
        if relative.parts[0] in self._EXCLUDED_TOP_LEVEL_DIRS:
            return True
        return self._path_has_noisy_components(relative)

    def _path_is_excluded(self, path: Path) -> bool:
        if self._path_has_noisy_components(path):
            return True
        for root in self.allowed_roots:
            if path == root or root in path.parents:
                rel = path.relative_to(root)
                return self._is_excluded_relative_path(rel)
        return False

    @classmethod
    def _path_has_noisy_components(cls, path: Path) -> bool:
        parts = [part.lower() for part in path.parts]
        if any(part in cls._NOISY_COMPONENTS for part in parts):
            return True
        if any(any(part.endswith(suffix) for suffix in cls._NOISY_SUFFIXES) for part in parts):
            return True

        path_lower = str(path).lower()
        if any(fragment in path_lower for fragment in cls._NOISY_PATH_FRAGMENTS):
            return True

        filename_lower = path.name.lower()
        return any(pattern.search(filename_lower) for pattern in cls._NOISY_FILENAME_PATTERNS)

    def _normalize_user_path(
        self,
        raw_path: str,
        *,
        must_exist: bool,
        operate_on_symlink_path: bool = False,
        check_target_root: bool = True,
    ) -> Path:
        if not raw_path.strip():
            raise ToolExecutionError("Path cannot be empty")
        if "\x00" in raw_path:
            raise ToolExecutionError("Path contains invalid null byte")
        try:
            candidate = Path(raw_path).expanduser()
            if not candidate.is_absolute():
                candidate = (Path.cwd() / candidate)
            
            # Resolve fully to ensure the target is safe (permissions check).
            # This follows symlinks, ensuring we don't operate on forbidden targets.
            resolved = candidate.resolve(strict=must_exist)
        except (OSError, RuntimeError, ValueError) as exc:
            raise ToolExecutionError(f"Invalid path '{raw_path}': {exc}") from exc

        # If check_target_root is True (default), ensure the *resolved target* is within roots.
        # If False (e.g. deleting a link), we might skip this check if the link itself is valid.
        if check_target_root:
            if not self._path_within_allowed_roots(resolved):
                raise ToolExecutionError(
                    f"Path '{resolved}' is outside allowed roots: "
                    + ", ".join(str(root) for root in self.allowed_roots)
                )

        # If we are NOT checking the target root (e.g. deleting a symlink),
        # we MUST ensure the *lexical* path (the link itself) is within allowed roots.
        # Otherwise, one could delete /etc/passwd via a carefully constructed path.
        lexical_path = Path(os.path.normpath(candidate))
        if not check_target_root:
            if not self._path_within_allowed_roots(lexical_path):
                raise ToolExecutionError(
                    f"Path '{lexical_path}' is outside allowed roots"
                )
            
            # CRITICAL SECURITY CHECK:
            # Even if we ignore the leaf target (to allow deleting broken symlinks),
            # we MUST ensure we haven't traversed a symlink *parent* to get here.
            # e.g. "valid_link/file" where "valid_link -> /etc" would pass lexical check
            # but resolve to /etc/file. We must verify the PARENT directory is safe.
            try:
                parent_resolved = lexical_path.parent.resolve(strict=must_exist)
                if not self._path_within_allowed_roots(parent_resolved):
                    raise ToolExecutionError(
                        f"Path parent '{parent_resolved}' resolves outside allowed roots"
                    )
            except (OSError, RuntimeError, ValueError) as exc:
                if must_exist:
                    raise ToolExecutionError(f"Could not resolve parent of '{raw_path}': {exc}") from exc

        # Symlink safety: for destructive operations, reject if the original
        # path is a symlink pointing outside allowed roots (TOCTOU mitigation).
        # Note: We already checked `resolved` (the target) above if check_target_root=True.
        # This check prevents "confused deputy" where the user might think they
        # are operating on a local file, but it's actually a link to something else.
        if operate_on_symlink_path and candidate.is_symlink():
            link_target = candidate.resolve(strict=False)
            # If we are strictly validating the target, we ensure it's safe.
            if check_target_root and not self._path_within_allowed_roots(link_target):
                raise ToolExecutionError(
                    f"Symlink '{candidate}' resolves to '{link_target}' which is outside allowed roots"
                )

        # Return the normalized (lexical) path so tools can operate on the
        # symlink itself (e.g. delete the link, not the target), while having
        # the confidence that the target was validated above.
        return lexical_path

    @staticmethod
    def _serialize_stat(path: Path) -> dict[str, Any]:
        data = path.stat()
        mode = stat.S_IMODE(data.st_mode)
        return {
            "path": str(path),
            "exists": True,
            "is_file": path.is_file(),
            "is_dir": path.is_dir(),
            "size_bytes": int(data.st_size),
            "permissions_octal": oct(mode),
            "created_at": float(data.st_ctime),
            "modified_at": float(data.st_mtime),
        }

    def _make_search_metadata(self, path: Path, *, score: int, source: str) -> dict[str, Any]:
        resolved = path.expanduser().resolve(strict=False)
        metadata = self._serialize_stat(resolved)
        metadata["score"] = int(score)
        metadata["source"] = source
        metadata["name"] = resolved.name
        metadata["display_path"] = self._display_path_for_user(resolved)
        metadata["relative_path"] = self._relative_path_for_allowed_root(resolved)
        try:
            metadata["uri"] = resolved.as_uri()
        except ValueError:
            metadata["uri"] = ""
        return metadata

    def _relative_path_for_allowed_root(self, path: Path) -> str:
        for root in self.allowed_roots:
            if path == root or root in path.parents:
                relative = path.relative_to(root)
                return "." if not relative.parts else str(relative)
        return str(path)

    def _display_path_for_user(self, path: Path) -> str:
        try:
            home = Path.home().resolve(strict=False)
        except Exception:  # pragma: no cover - defensive
            home = Path.home()

        if path == home or home in path.parents:
            relative = path.relative_to(home)
            return "~" if not relative.parts else f"~/{relative}"
        return str(path)

    def _ordered_walk_targets(self, root: Path) -> list[tuple[Path, set[str]]]:
        """Return prioritized walk targets for a root path.

        For the user's home directory (or the root filesystem), scan
        high-signal user folders first so matches are found before the
        global scan budget is exhausted.  When the root is ``/``, the
        walker focuses on user-facing directories instead of traversing
        the entire filesystem.
        """
        home = Path.home().expanduser().resolve(strict=False)
        root_resolved = root.resolve(strict=False)

        # Root filesystem: walk user home (prioritized) + /Applications.
        # Never os.walk("/") directly — too expensive.
        if root_resolved == Path("/"):
            targets = self._ordered_walk_targets(home)
            apps = Path("/Applications")
            if apps.exists() and apps.is_dir():
                targets.append((apps, set()))
            return targets

        if root_resolved != home:
            return [(root, set())]

        prioritized_targets: list[tuple[Path, set[str]]] = []
        skipped_names: set[str] = set()
        for name in self._HOME_PRIORITY_DIRS:
            candidate = (root / name).resolve(strict=False)
            if not candidate.exists() or not candidate.is_dir():
                continue
            if not self._path_within_allowed_roots(candidate):
                continue
            if self._path_is_excluded(candidate):
                continue
            prioritized_targets.append((candidate, set()))
            skipped_names.add(name)

        # Final pass over home for everything else, excluding already-walked
        # top-level folders to avoid duplicate traversal.
        prioritized_targets.append((root, skipped_names))
        return prioritized_targets

    @classmethod
    def _directory_sort_key(
        cls,
        name: str,
        *,
        query_tokens: list[str],
        folder_hints: set[str],
    ) -> tuple[int, str]:
        """Sort directories so likely-relevant locations are visited earlier."""
        lowered = name.lower()
        score = 0

        if lowered in cls._HOME_PRIORITY_DIRS_LOWER:
            score -= 30
        if any(folder in lowered for folder in folder_hints):
            score -= 40
        for token in query_tokens:
            if token in lowered:
                score -= 16 if len(token) >= 4 else 8
        return score, lowered

    @staticmethod
    def _truncate_text(value: str, *, limit: int) -> tuple[str, bool, int]:
        text = value or ""
        total_chars = len(text)
        if total_chars <= limit:
            return text, False, total_chars
        omitted = total_chars - limit
        suffix = f"\n...[truncated {omitted} chars]"
        head_len = max(0, limit - len(suffix))
        # Semantic truncation: find the nearest clean break point
        # (paragraph, line, or word boundary) near the cut position
        # to avoid cutting mid-word or mid-sentence.
        scan_start = max(0, head_len - 200)
        region = text[scan_start:head_len]
        # Prefer paragraph boundary → line boundary → word boundary.
        para_pos = region.rfind("\n\n")
        if para_pos != -1:
            head_len = scan_start + para_pos
        else:
            line_pos = region.rfind("\n")
            if line_pos != -1:
                head_len = scan_start + line_pos
            else:
                space_pos = region.rfind(" ")
                if space_pos != -1:
                    head_len = scan_start + space_pos
        # Re-compute omitted count after adjusting head_len.
        omitted = total_chars - head_len
        suffix = f"\n...[truncated {omitted} chars]"
        result = text[:head_len] + suffix
        if len(result) > limit:
            result = text[:limit]
        return result, True, total_chars


    @staticmethod
    def _tokenize_search_query(query_lower: str) -> list[str]:
        raw_tokens = re.findall(r"[a-z0-9._+-]+", query_lower)
        tokens: list[str] = []
        seen: set[str] = set()
        for token in raw_tokens:
            cleaned = token.strip("._-")
            if not cleaned:
                continue
            # _SEARCH_TOKEN_ALIASES removed — model handles synonyms
            # via structured extensions/folder_hint params.
            if cleaned in ToolExecutor._SEARCH_STOPWORDS:
                continue
            if len(cleaned) == 1 and cleaned not in ToolExecutor._DIRECT_EXTENSION_TOKENS:
                continue
            if cleaned in seen:
                continue
            seen.add(cleaned)
            tokens.append(cleaned)
        return tokens

    @staticmethod
    def _normalize_token_forms(token: str) -> list[str]:
        """Generate singular/plural forms via suffix rules (no hardcoded dict).

        Handles the most common English plural patterns algorithmically:
        -ies → -y, -es → strip, -s → strip, and singular → +s.
        """
        forms = [token]
        # Plural → singular
        if token.endswith("ies") and len(token) > 4:
            forms.append(token[:-3] + "y")   # "memories" → "memory"
        elif token.endswith("es") and len(token) > 3:
            forms.append(token[:-2])          # "watches" → "watch"
        elif token.endswith("s") and len(token) > 2 and not token.endswith("ss"):
            forms.append(token[:-1])          # "documents" → "document"
        # Singular → plural
        if not token.endswith("s"):
            forms.append(token + "s")         # "document" → "documents"
        return list(dict.fromkeys(forms))

    @classmethod
    def _expand_search_tokens(cls, query_tokens: list[str]) -> list[str]:
        expanded: list[str] = []
        seen: set[str] = set()

        def _add(token: str) -> None:
            normalized = token.strip().lower()
            if not normalized or normalized in seen:
                return
            seen.add(normalized)
            expanded.append(normalized)

        for token in query_tokens:
            _add(token)
            # Algorithmic plural/singular normalization (F6).
            for form in cls._normalize_token_forms(token):
                _add(form)

        token_set = set(expanded)
        if "images" in token_set or "image" in token_set:
            _add("image")
            _add("images")
        if "photos" in token_set or "photo" in token_set:
            _add("photo")
            _add("image")
        if "screenshots" in token_set or "screenshot" in token_set:
            _add("screenshot")
            _add("image")
        if "gemini" in token_set and ("image" in token_set or "images" in token_set):
            _add("generated")
        if "generated" in token_set and "gemini" in token_set:
            _add("image")
        if {"gemini", "generated", "image"}.issubset(set(expanded)):
            _add("gemini_generated_image")

        return expanded

    @classmethod
    def _derive_spotlight_query_variants(
        cls,
        *,
        original_query: str,
        query_tokens: list[str],
        query_phrases: list[str],
        extension_hints: set[str] | None = None,
    ) -> list[str]:
        variants: list[str] = []
        seen: set[str] = set()

        def _add(candidate: str) -> None:
            normalized = " ".join(candidate.split())
            if not normalized:
                return
            lowered = normalized.lower()
            if lowered in seen:
                return
            seen.add(lowered)
            variants.append(normalized)

        _add(original_query)

        for phrase in query_phrases[:2]:
            _add(phrase)

        if query_tokens:
            _add(" ".join(query_tokens[:8]))

        token_set = set(query_tokens)
        if {"gemini", "image"}.issubset(token_set):
            _add("gemini generated image")

        # Filename-targeted mdfind variants via -name: sentinel prefix.
        # mdfind -name is dramatically more precise than general content search.
        if query_tokens:
            _add(f"-name:{' '.join(query_tokens[:4])}")

        # Extension-filtered filename variants for the top 2 extension hints.
        if extension_hints:
            for ext in sorted(extension_hints)[:2]:
                _add(f"-name:.{ext}")

        return variants[:6]

    @classmethod
    def _derive_extension_hints(cls, query_tokens: list[str]) -> set[str]:
        hints: set[str] = set()
        for token in query_tokens:
            normalized = token.lower().lstrip(".")
            if normalized in cls._DIRECT_EXTENSION_TOKENS:
                hints.add(normalized)
            semantic_hints = cls._SEMANTIC_EXTENSION_HINTS.get(normalized)
            if semantic_hints:
                hints.update(semantic_hints)
        return hints

    @classmethod
    def _derive_folder_hints(cls, query_tokens: list[str]) -> set[str]:
        hints: set[str] = set()
        for token in query_tokens:
            mapped = cls._FOLDER_HINTS.get(token.lower())
            if mapped:
                hints.add(mapped)
        return hints

    @classmethod
    def _score_path_with_signals(
        cls,
        query_lower: str,
        query_tokens: list[str],
        query_phrases: list[str],
        extension_hints: set[str],
        folder_hints: set[str],
        path: Path,
    ) -> tuple[int, dict[str, float]]:
        if cls._path_has_noisy_components(path):
            return 0, {"excluded_noise": 1.0}

        filename_lower = path.name.lower()
        stem_lower = path.stem.lower()
        haystack = str(path).lower()
        parent_lower = str(path.parent).lower()
        score = 0
        matched_tokens = 0
        signals: dict[str, float] = {}

        if query_lower and query_lower in filename_lower:
            score += 180
            signals["exact_filename_match"] = 180.0
        elif query_lower and query_lower in haystack:
            score += 90
            signals["path_substring_match"] = 90.0

        normalized_query = re.sub(r"[^a-z0-9]+", "", query_lower)
        normalized_stem = re.sub(r"[^a-z0-9]+", "", stem_lower)
        if len(normalized_query) >= 4 and normalized_query in normalized_stem:
            score += 60
            signals["normalized_stem_match"] = 60.0

        # Exact stem match: the entire stem equals the query (e.g., "report"
        # matches "report.txt" but not "monthly_report_summary.txt").
        if query_lower and query_lower == stem_lower:
            score += 30
            signals["exact_stem_match"] = 30.0

        for phrase in query_phrases:
            if phrase in filename_lower:
                score += 70
                signals["phrase_filename_match"] = signals.get("phrase_filename_match", 0.0) + 70.0
            elif phrase in haystack:
                score += 40
                signals["phrase_path_match"] = signals.get("phrase_path_match", 0.0) + 40.0

        # Split filename stem into word-boundary segments for prefix matching.
        stem_words = re.split(r"[._\-\s]+", stem_lower)
        parent_words = re.split(r"[/_.\-\s]+", parent_lower)

        for token in query_tokens:
            token_score = 0
            if token in filename_lower:
                token_score = 40 if len(token) >= 4 else 28
            elif token in stem_lower:
                token_score = 32
            elif token in parent_lower:
                token_score = 16
            elif token in haystack:
                token_score = 8

            # Word-boundary prefix matching (F6): "doc" at a word boundary
            # in "budget_document" gets a bonus, but "doc" inside
            # "indoctrinate" does not.  Acts as primary score when no
            # substring match found, or supplemental bonus to distinguish
            # word-boundary hits from coincidental mid-word substrings.
            if len(token) >= 3:
                prefix_bonus = 0
                for word in stem_words:
                    if len(word) >= 3 and word.startswith(token) and word != token:
                        prefix_bonus = 14 if not token_score else 10
                        break
                if not prefix_bonus:
                    for word in parent_words:
                        if len(word) >= 3 and word.startswith(token) and word != token:
                            prefix_bonus = 8 if not token_score else 6
                            break
                token_score += prefix_bonus

            if token_score:
                score += token_score
                matched_tokens += 1
                signals["token_score"] = signals.get("token_score", 0.0) + float(token_score)

        ext = path.suffix.lower().lstrip(".")
        if extension_hints:
            if ext in extension_hints:
                score += 42
                signals["extension_hint_match"] = 42.0
            elif ext:
                score -= 8
                signals["extension_penalty"] = -8.0

        for folder in folder_hints:
            if f"/{folder}/" in haystack:
                score += 16
                signals["folder_hint_match"] = signals.get("folder_hint_match", 0.0) + 16.0

        for preferred_folder in ("/documents/", "/desktop/", "/downloads/", "/projects/"):
            if preferred_folder in haystack:
                score += 4
                signals["preferred_user_folder"] = 4.0
                break

        if query_tokens:
            coverage = matched_tokens / len(query_tokens)
            if coverage >= 0.75:
                score += 24
                signals["token_coverage_boost"] = 24.0
            elif coverage >= 0.5:
                score += 14
                signals["token_coverage_boost"] = 14.0

        min_score = 14 + min(24, len(query_tokens) * 3)
        if score < min_score:
            return 0, {"below_threshold": float(min_score - score)}
        return score, signals

    @classmethod
    def _score_path(
        cls,
        query_lower: str,
        query_tokens: list[str],
        query_phrases: list[str],
        extension_hints: set[str],
        folder_hints: set[str],
        path: Path,
    ) -> int:
        score, _ = cls._score_path_with_signals(
            query_lower=query_lower,
            query_tokens=query_tokens,
            query_phrases=query_phrases,
            extension_hints=extension_hints,
            folder_hints=folder_hints,
            path=path,
        )
        return score

    def _search_spotlight(
        self,
        *,
        queries: Sequence[str],
        query_lower: str,
        query_tokens: list[str],
        query_phrases: list[str],
        extension_hints: set[str],
        folder_hints: set[str],
        path_filter: str,
        limit: int,
        mdfind_timeout: int = 8,
        collect_cap_mult: int = 3,
    ) -> tuple[list[dict[str, Any]], int]:
        if shutil.which("mdfind") is None:
            return [], 0

        # Build all (root, query) work items for parallel execution.
        work_items = [
            (root, query)
            for root in self.allowed_roots if root.exists()
            for query in queries
        ]
        if not work_items:
            return [], 0

        collected: list[dict[str, Any]] = []
        seen: set[str] = set()
        scanned_candidates = 0
        collect_cap = max(limit * collect_cap_mult, limit)

        def _run_mdfind(
            root: Path, query: str,
        ) -> subprocess.CompletedProcess[str] | None:
            try:
                # Detect -name: sentinel prefix for filename-targeted queries (F3).
                if query.startswith("-name:"):
                    name_query = query[6:]
                    cmd = ["mdfind", "-onlyin", str(root), "-name", name_query]
                else:
                    cmd = ["mdfind", "-onlyin", str(root), query]
                return subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=mdfind_timeout,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as mdfind_exc:
                logger.debug("mdfind failed for root %s: %s", root, mdfind_exc)
                return None

        workers = min(8, len(work_items))
        content_floor_count = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_run_mdfind, root, query): (root, query)
                for root, query in work_items
            }
            for future in as_completed(futures):
                if len(collected) >= collect_cap:
                    break
                completed = future.result()
                if completed is None or completed.returncode not in {0, 1}:
                    continue

                _orig_root, orig_query = futures[future]
                is_content_query = not orig_query.startswith("-name:")

                for line in completed.stdout.splitlines():
                    candidate_raw = line.strip()
                    if not candidate_raw:
                        continue
                    scanned_candidates += 1
                    candidate = Path(candidate_raw).expanduser().resolve(strict=False)
                    path_key = str(candidate)
                    if path_key in seen:
                        continue
                    if not self._path_within_allowed_roots(candidate):
                        continue
                    if self._path_is_excluded(candidate):
                        continue
                    haystack = path_key.lower()
                    if path_filter and path_filter not in haystack:
                        continue
                    if not candidate.exists():
                        continue
                    if not candidate.is_file():
                        continue

                    score = self._score_path(
                        query_lower,
                        query_tokens,
                        query_phrases,
                        extension_hints,
                        folder_hints,
                        candidate,
                    )
                    is_content_floor = False
                    if score <= 0:
                        if is_content_query and content_floor_count < self._MAX_CONTENT_FLOOR_RESULTS:
                            score = self._SPOTLIGHT_CONTENT_FLOOR
                            content_floor_count += 1
                            is_content_floor = True
                        else:
                            continue
                    try:
                        metadata = self._make_search_metadata(
                            candidate, score=score, source="spotlight",
                        )
                    except OSError:
                        continue
                    if is_content_floor:
                        metadata["spotlight_content_match"] = True
                    collected.append(metadata)
                    seen.add(path_key)
                    if len(collected) >= collect_cap:
                        break

        return collected, scanned_candidates

    def _merge_ranked_search_candidates(
        self,
        *,
        candidates: list[dict[str, Any]],
        query_lower: str,
        query_tokens: list[str],
        query_phrases: list[str],
        extension_hints: set[str],
        folder_hints: set[str],
    ) -> list[dict[str, Any]]:
        # Group candidates by source to apply Reciprocal Rank Fusion (RRF)
        source_candidates: dict[str, list[dict[str, Any]]] = {
            "spotlight": [],
            "index": [],
            "walk": [],
        }
        
        now_ts = time.time()
        for row in candidates:
            path_raw = str(row.get("path", "")).strip()
            if not path_raw:
                continue
            path_obj = Path(path_raw).expanduser().resolve(strict=False)
            if not path_obj.exists() or not path_obj.is_file():
                continue
            if not self._path_within_allowed_roots(path_obj):
                continue
            if self._path_is_excluded(path_obj):
                continue

            score, default_signals = self._score_path_with_signals(
                query_lower=query_lower,
                query_tokens=query_tokens,
                query_phrases=query_phrases,
                extension_hints=extension_hints,
                folder_hints=folder_hints,
                path=path_obj,
            )
            source = str(row.get("source", "walk")).strip() or "walk"
            if score <= 0:
                if source == "spotlight" and not default_signals.get("excluded_noise"):
                    score = self._SPOTLIGHT_CONTENT_FLOOR
                    default_signals = {"spotlight_content_floor": float(self._SPOTLIGHT_CONTENT_FLOOR)}
                else:
                    continue

            modified_at_raw = row.get("modified_at")
            modified_at = float(modified_at_raw) if isinstance(modified_at_raw, (int, float)) else now_ts
            age_days = max(0.0, (now_ts - modified_at) / 86400.0)
            recency_boost = max(0.0, 24.0 - min(24.0, age_days))

            signal_payload = row.get("match_signals")
            signals = dict(signal_payload) if isinstance(signal_payload, dict) else {}
            if not signals:
                signals.update(default_signals)

            row["_intrinsic_score"] = float(score)
            row["recency_boost"] = recency_boost
            row["match_signals"] = signals
            row["path"] = str(path_obj)
            row["source"] = source
            row["modified_at"] = modified_at

            source_candidates.setdefault(source, []).append(row)

        # Sort each source list by intrinsic score to determine ordinal ranks
        for source_name, items in source_candidates.items():
            items.sort(key=lambda x: (x.get("_intrinsic_score", 0), x.get("recency_boost", 0)), reverse=True)

        # Apply Reciprocal Rank Fusion (RRF): score = sum(1 / (k + rank))
        k = 60.0
        merged: dict[str, dict[str, Any]] = {}
        
        for source_name, items in source_candidates.items():
            for rank_idx, item in enumerate(items):
                path_key = str(item["path"])
                rrf_term = 1.0 / (k + rank_idx + 1)
                
                if path_key not in merged:
                    item["_rrf_sum"] = rrf_term
                    item["match_signals"][f"{source_name}_rank"] = rank_idx + 1
                    merged[path_key] = item
                else:
                    existing = merged[path_key]
                    existing["_rrf_sum"] += rrf_term
                    existing["match_signals"][f"{source_name}_rank"] = rank_idx + 1
                    if item["_intrinsic_score"] > existing["_intrinsic_score"]:
                        existing["_intrinsic_score"] = item["_intrinsic_score"]
                        existing["match_signals"].update(item["match_signals"])

        # Finalize and scale scores
        ranked = list(merged.values())
        for row in ranked:
            base_rrf_score = row.pop("_rrf_sum") * 3000.0
            recency = row.pop("recency_boost", 0.0)
            
            source_boost = 0.0
            if "spotlight_rank" in row["match_signals"]:
                source_boost += 8.0
            if "index_rank" in row["match_signals"]:
                source_boost += 4.0
                
            final_score = base_rrf_score + recency + source_boost
            
            row["score"] = int(final_score)
            row["match_signals"]["rrf_score"] = round(base_rrf_score, 3)
            row["match_signals"]["recency_boost"] = round(recency, 3)
            row.pop("_intrinsic_score", None)

        ranked.sort(
            key=lambda item: (
                int(item.get("score", 0)),
                float(item.get("modified_at", 0.0)),
                str(item.get("path", "")),
            ),
            reverse=True,
        )
        return ranked

    # ------------------------------------------------------------------
    # directory co-location discovery (S2)
    # ------------------------------------------------------------------

    def _discover_colocated_files(
        self,
        ranked_results: list[dict[str, Any]],
        *,
        top_n: int = 5,
        min_shared: int = 2,
        max_siblings: int = 10,
        boost_score: int = 12,
    ) -> list[dict[str, Any]]:
        """Add sibling files from directories with multiple top results.

        When 2+ top results share a parent directory, other files in that
        directory are likely related.  Returns new candidates only (callers
        should extend the existing list).
        """
        if len(ranked_results) < min_shared:
            return []

        existing_paths = {r.get("path", "") for r in ranked_results}

        # Count how many top results share each parent directory.
        dir_counts: dict[str, int] = {}
        for result in ranked_results[:top_n]:
            path_raw = result.get("path", "")
            if not path_raw:
                continue
            parent = str(Path(path_raw).parent)
            dir_counts[parent] = dir_counts.get(parent, 0) + 1

        siblings: list[dict[str, Any]] = []
        for dir_path, count in dir_counts.items():
            if count < min_shared:
                continue
            parent = Path(dir_path)
            if not parent.is_dir():
                continue
            added = 0
            try:
                for child in parent.iterdir():
                    if added >= max_siblings:
                        break
                    if not child.is_file():
                        continue
                    child_str = str(child)
                    if child_str in existing_paths:
                        continue
                    if not self._path_within_allowed_roots(child):
                        continue
                    if self._path_is_excluded(child):
                        continue
                    if self._path_has_noisy_components(child):
                        continue
                    try:
                        metadata = self._make_search_metadata(
                            child, score=boost_score, source="colocation",
                        )
                    except OSError:
                        continue
                    metadata["colocation_source"] = True
                    siblings.append(metadata)
                    existing_paths.add(child_str)
                    added += 1
            except OSError:
                continue
        return siblings

    # ------------------------------------------------------------------
    # search result cache (S3)
    # ------------------------------------------------------------------

    def _cache_search_results(
        self,
        query_lower: str,
        query_tokens: list[str],
        result_paths: tuple[str, ...],
        result_scores: tuple[int, ...],
    ) -> None:
        """Store recent search results for cross-execution recall."""
        entry: dict[str, Any] = {
            "query_lower": query_lower,
            "query_tokens": frozenset(query_tokens),
            "timestamp": time.time(),
            "result_paths": result_paths,
            "result_scores": result_scores,
        }
        while len(self._recent_search_cache) >= self._SEARCH_CACHE_MAX_ENTRIES:
            self._recent_search_cache.popitem(last=False)
        self._recent_search_cache[query_lower] = entry
        self._recent_search_cache.move_to_end(query_lower)

    def _apply_cache_boost(
        self,
        *,
        current_query_tokens: list[str],
        candidates: list[dict[str, Any]],
    ) -> int:
        """Boost candidates that appeared in recent related searches.

        Returns the number of candidates that received a boost.
        """
        now = time.time()
        current_tokens = set(current_query_tokens)
        if not current_tokens:
            return 0

        boosted_paths: dict[str, float] = {}
        for _cache_key, entry in self._recent_search_cache.items():
            if now - entry["timestamp"] > self._SEARCH_CACHE_TTL_SECONDS:
                continue
            cached_tokens = entry["query_tokens"]
            overlap = current_tokens & cached_tokens
            if not overlap:
                continue
            overlap_ratio = len(overlap) / max(len(current_tokens), len(cached_tokens))
            if overlap_ratio < 0.3:
                continue
            boost = self._SEARCH_CACHE_OVERLAP_BOOST * overlap_ratio
            for path_str in entry["result_paths"]:
                existing_boost = boosted_paths.get(path_str, 0.0)
                boosted_paths[path_str] = max(existing_boost, boost)

        if not boosted_paths:
            return 0

        boosted_count = 0
        for candidate in candidates:
            path = candidate.get("path", "")
            boost = boosted_paths.get(path, 0.0)
            if boost > 0:
                candidate["score"] = int(candidate.get("score", 0)) + int(boost)
                signals = candidate.get("match_signals", {})
                signals["cache_overlap_boost"] = round(boost, 3)
                candidate["match_signals"] = signals
                boosted_count += 1
        return boosted_count

    # ------------------------------------------------------------------
    # tool handlers
    # ------------------------------------------------------------------


    def _read_text(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Delegate to per-tool module (kept for internal cross-calls)."""
        from agent_host.tools import read_text
        return read_text.handle(self, arguments)

    @staticmethod
    def _infer_plan_dependencies(ops: Sequence[dict[str, Any]]) -> list[tuple[int, int]]:
        """Build abstract dependency edges using local comparisons only.

        This function may inspect paths locally, but only returns integer edges.
        No path strings are passed to the external planner engine.
        """
        edges: set[tuple[int, int]] = set()
        for i, left in enumerate(ops):
            left_src = str(left.get("src", "")).strip()
            left_dest = str(left.get("dest") or "").strip()
            for j in range(i + 1, len(ops)):
                right = ops[j]
                right_src = str(right.get("src", "")).strip()
                right_dest = str(right.get("dest") or "").strip()
                if left_dest and right_src and left_dest == right_src:
                    edges.add((i, j))
                if left_src and right_src and left_src == right_src:
                    edges.add((i, j))
                if left_dest and right_dest and left_dest == right_dest:
                    edges.add((i, j))
        return sorted(edges)

    @classmethod
    def _planner_op_code(cls, op_kind: str) -> int:
        return int(cls._PLANNER_OP_CODES.get(str(op_kind).strip().lower(), 0))

    @classmethod
    def _planner_abstract_steps_from_normalized_ops(
        cls,
        ops: Sequence[Mapping[str, Any]],
    ) -> list[tuple[int, int, bool]]:
        steps: list[tuple[int, int, bool]] = []
        for index, op in enumerate(ops):
            op_kind = str(op.get("op", "")).strip().lower()
            op_code = cls._planner_op_code(op_kind)
            is_valid = bool(op.get("valid", False))
            steps.append((index, op_code, is_valid))
        return steps

    @classmethod
    def _planner_abstract_steps_from_raw_ops(
        cls,
        raw_ops: Sequence[Any],
    ) -> list[tuple[int, int, bool]]:
        steps: list[tuple[int, int, bool]] = []
        for index, raw in enumerate(raw_ops):
            if not isinstance(raw, Mapping):
                steps.append((index, 0, False))
                continue
            op_kind = str(raw.get("op", "")).strip().lower()
            op_code = cls._planner_op_code(op_kind)
            has_src = isinstance(raw.get("src"), str) and bool(str(raw.get("src")).strip())
            requires_dest = op_kind in {"move", "rename", "copy"}
            has_dest = isinstance(raw.get("dest"), str) and bool(str(raw.get("dest")).strip())
            is_valid = bool(op_code) and has_src and (not requires_dest or has_dest)
            steps.append((index, op_code, is_valid))
        return steps


    def _plan_ops(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Delegate to per-tool module (kept for internal cross-calls)."""
        from agent_host.tools import plan_ops
        return plan_ops.handle(self, arguments)

    @staticmethod
    def _trash_directory() -> Path:
        return Path.home().expanduser().resolve(strict=False) / ".Trash"

    def _trash_directory_candidates(self, *, src_path: Path) -> list[Path]:
        candidates: list[Path] = [self._trash_directory()]
        src_resolved = src_path.expanduser().resolve(strict=False)
        for root in self.allowed_roots:
            if src_resolved == root or root in src_resolved.parents:
                candidate = root / ".ai-agent-trash"
                if candidate not in candidates:
                    candidates.append(candidate)
                break
        return candidates

    def _next_available_trash_path(self, name: str, *, trash_dir: Path) -> Path:
        preferred = trash_dir / name
        if not preferred.exists():
            return preferred

        source = Path(name)
        suffix = "".join(source.suffixes)
        stem = source.name[: -len(suffix)] if suffix else source.name
        stem = stem.rstrip() or "item"

        for index in range(1, self._TRASH_COLLISION_ATTEMPTS + 1):
            candidate = trash_dir / f"{stem} {index}{suffix}"
            if not candidate.exists():
                return candidate

        return trash_dir / f"{stem}-{uuid.uuid4().hex}{suffix}"

    def _move_path_to_trash(self, src_path: Path) -> Path:
        src_resolved = src_path.resolve(strict=False)
        move_errors: list[OSError] = []

        for trash_dir in self._trash_directory_candidates(src_path=src_path):
            try:
                trash_dir.mkdir(parents=True, exist_ok=True)
                trash_resolved = trash_dir.resolve(strict=False)
            except OSError as exc:
                move_errors.append(exc)
                continue

            if src_resolved.parent == trash_resolved:
                return src_resolved

            destination = self._next_available_trash_path(src_path.name, trash_dir=trash_dir)
            try:
                shutil.move(str(src_path), str(destination))
                return destination
            except OSError as exc:
                move_errors.append(exc)
                continue

        if move_errors:
            raise move_errors[-1]
        raise OSError("No writable trash directory available")

    @staticmethod
    def _next_available_destination_path(destination: Path) -> Path:
        if not destination.exists():
            return destination

        suffix = "".join(destination.suffixes)
        stem = destination.name[: -len(suffix)] if suffix else destination.name
        stem = stem.rstrip() or "item"
        for index in range(1, 1001):
            candidate = destination.parent / f"{stem} {index}{suffix}"
            if not candidate.exists():
                return candidate
        return destination.parent / f"{stem}-{uuid.uuid4().hex}{suffix}"

    def _resolve_destination_with_policy(
        self,
        *,
        destination: Path,
        overwrite_policy: str,
    ) -> tuple[Path, bool]:
        """Resolve destination path according to conflict policy.

        Returns ``(resolved_destination, destination_already_exists)``.
        """
        destination_exists = destination.exists()
        if not destination_exists:
            return destination, False

        if overwrite_policy == "rename":
            return self._next_available_destination_path(destination), True
        if overwrite_policy == "overwrite":
            return destination, True
        raise ToolExecutionError(
            f"Destination already exists: {destination} (overwrite_policy=fail)"
        )

    def _verify_apply_result(
        self,
        *,
        op_kind: str,
        src_path: Path,
        dest_path: Path | None,
    ) -> str | None:
        if op_kind in {"move", "rename"}:
            if dest_path is None:
                return "Verification failed: destination path missing"
            if src_path.exists():
                return f"Verification failed: source still exists after {op_kind}: {src_path}"
            if not dest_path.exists():
                return f"Verification failed: destination missing after {op_kind}: {dest_path}"
            return None
        if op_kind == "copy":
            if dest_path is None:
                return "Verification failed: destination path missing"
            if not src_path.exists():
                return f"Verification failed: source missing after copy: {src_path}"
            if not dest_path.exists():
                return f"Verification failed: destination missing after copy: {dest_path}"
            return None
        if op_kind == "delete":
            if src_path.exists():
                return f"Verification failed: source still exists after delete: {src_path}"
            return None
        return None
