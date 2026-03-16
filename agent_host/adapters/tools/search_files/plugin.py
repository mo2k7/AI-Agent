"""Tool plugin: search_files.

Self-contained search engine combining macOS Spotlight (``mdfind``), an
incremental FTS5 full-text index, directory co-location discovery, and
an LRU cache of recent search results for cross-query recall.

This plugin owns ALL search state: the FTS index on disk, the in-memory
LRU cache, and the incremental-seeding cursor.  No search logic remains
in ``ToolExecutor``.
"""

from __future__ import annotations

import collections
import logging
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import time
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Mapping

from agent_host.adapters.tools._path_security import path_within_roots, serialize_stat
from agent_host.contracts.types.errors import AgentError, ErrorCode
from agent_host.contracts.types.result import Failure, Result, Success

logger = logging.getLogger(__name__)

# Mode-aware configuration — controls pipeline behaviour per search strategy.
_MODE_CONFIG: dict[str, dict[str, object]] = {
    "fast": {
        "seed": False,
        "mdfind_timeout": 4,
        "collect_cap_mult": 2,
        "fts_fallback": False,
        "seed_budget_cap_ms": 0,
        "seed_entries_cap": 0,
    },
    "auto": {
        "seed": True,
        "mdfind_timeout": 8,
        "collect_cap_mult": 3,
        "fts_fallback": False,
        "seed_budget_cap_ms": 220,
        "seed_entries_cap": 1200,
    },
    "deep": {
        "seed": True,
        "mdfind_timeout": 8,
        "collect_cap_mult": 5,
        "fts_fallback": True,
        "seed_budget_cap_ms": 600,
        "seed_entries_cap": 5000,
    },
}


class SearchFilesPlugin:
    """Self-contained plugin for the ``search_files`` tool.

    Implements the ``ToolPlugin`` protocol and encapsulates all search
    constants, FTS index management, Spotlight integration, path scoring,
    result caching, and directory co-location discovery.
    """

    # ------------------------------------------------------------------
    # Class constants
    # ------------------------------------------------------------------
    _EXCLUDED_TOP_LEVEL_DIRS: frozenset[str] = frozenset({
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
        "home",
        ".Trash",
        ".fseventsd",
        ".vol",
    })

    _SEARCH_STOPWORDS: frozenset[str] = frozenset({
        "a", "am", "an", "are", "as", "at", "be", "but", "by", "can",
        "do", "does", "for", "from", "had", "has", "have", "he", "her",
        "him", "his", "i", "if", "in", "is", "it", "its", "me", "my",
        "no", "not", "of", "on", "or", "our", "she", "so", "the", "to",
        "up", "us", "was", "we", "who", "will", "with", "you", "your",
    })

    _SEMANTIC_EXTENSION_HINTS: dict[str, set[str]] = {
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

    _DIRECT_EXTENSION_TOKENS: frozenset[str] = frozenset({
        "c", "cc", "cpp", "csv", "doc", "docx", "go", "heic", "java",
        "jpeg", "jpg", "js", "json", "key", "md", "mkv", "mov", "mp3",
        "mp4", "numbers", "odt", "pages", "pdf", "png", "ppt", "pptx",
        "py", "rs", "rtf", "sh", "swift", "ts", "tsx", "txt", "wav",
        "xlsx", "xml", "yaml", "yml",
    })

    _FOLDER_HINTS: dict[str, str] = {
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

    _HOME_PRIORITY_DIRS: tuple[str, ...] = (
        "Downloads",
        "Desktop",
        "Documents",
        "Pictures",
        "Movies",
        "Music",
    )
    _HOME_PRIORITY_DIRS_LOWER: frozenset[str] = frozenset(
        name.lower() for name in _HOME_PRIORITY_DIRS
    )

    _NOISY_COMPONENTS: frozenset[str] = frozenset({
        ".ds_store", ".fseventsd", ".git", ".hg", ".mypy_cache",
        ".pytest_cache", ".spotlight-v100", ".svn", ".trash",
        "__pycache__", "cache", "caches", "index.spotlightv3",
        "library", "node_modules", "spotlight",
    })
    _NOISY_SUFFIXES: frozenset[str] = frozenset({
        ".photoslibrary",
        ".photolibrary",
    })
    _NOISY_PATH_FRAGMENTS: tuple[str, ...] = (
        "/database/search/spotlight/",
        "/index.spotlightv3/",
        "/spotlight/",
    )
    _NOISY_FILENAME_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(r"live\.\d+\.directorystorefile$", re.IGNORECASE),
        re.compile(r"clientstatesmetafile$", re.IGNORECASE),
    )

    _SEARCH_RANKING_VERSION: str = "v2"
    _SPOTLIGHT_CONTENT_FLOOR: int = 18
    _MAX_CONTENT_FLOOR_RESULTS: int = 15
    _SEARCH_CACHE_MAX_ENTRIES: int = 8
    _SEARCH_CACHE_TTL_SECONDS: float = 300.0
    _SEARCH_CACHE_OVERLAP_BOOST: int = 14
    _SEARCH_MODE_VALUES: frozenset[str] = frozenset({"auto", "fast", "deep"})

    # ------------------------------------------------------------------
    # Constructor
    # ------------------------------------------------------------------

    def __init__(
        self,
        *,
        allowed_roots: Sequence[Path],
        search_scan_limit: int = 5000,
    ) -> None:
        self._allowed_roots: tuple[Path, ...] = tuple(
            dict.fromkeys(
                r.expanduser().resolve(strict=False) for r in allowed_roots
            )
        )
        self._search_scan_limit: int = max(200, int(search_scan_limit))

        self._search_index_path: Path = self._default_search_index_path()
        self._search_index_enabled: bool = self._initialize_search_index()
        self._search_index_cursor_root: int = 0
        self._search_index_cursor_path: str = ""
        self._recent_search_cache: collections.OrderedDict[str, dict[str, Any]] = (
            collections.OrderedDict()
        )

    # ------------------------------------------------------------------
    # ToolPlugin protocol
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "search_files"

    @property
    def description(self) -> str:
        return (
            "Search for files using Spotlight, FTS5, and path scoring. "
            "Supports fast, auto, and deep modes."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (file name, type, or content keywords)",
                },
                "mode": {
                    "type": "string",
                    "enum": ["auto", "fast", "deep"],
                    "description": "Search strategy (default: auto)",
                },
                "path_filter": {
                    "type": "string",
                    "description": "Substring filter applied to full file path",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (1-100, default: 10)",
                },
                "time_budget_ms": {
                    "type": "integer",
                    "description": "Maximum time budget in milliseconds (100-10000, default: 700)",
                },
                "include_hidden": {
                    "type": "boolean",
                    "description": "Include hidden files/dirs (default: false)",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum directory traversal depth (0-128)",
                },
                "extensions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Preferred file extensions to search for",
                },
                "folder_hint": {
                    "type": "string",
                    "description": "Hint about which folder category to prefer",
                },
            },
            "required": ["query"],
        }

    @property
    def search_scan_limit(self) -> int:
        return self._search_scan_limit

    @property
    def allowed_roots(self) -> tuple[Path, ...]:
        return self._allowed_roots

    def execute(self, arguments: Mapping[str, Any]) -> Result[dict[str, Any]]:
        """Execute the search_files tool, returning Success or Failure."""
        try:
            return Success(self._execute_inner(arguments))
        except _PluginValidationError as exc:
            return Failure(AgentError(
                code=ErrorCode.VALIDATION,
                message=str(exc),
                source="search_files",
            ))
        except Exception as exc:
            return Failure(AgentError(
                code=ErrorCode.INTERNAL,
                message=f"Unexpected error in search_files: {exc}",
                source="search_files",
            ))

    def health_check(self) -> Result[bool]:
        return Success(True)

    # ------------------------------------------------------------------
    # Core search pipeline
    # ------------------------------------------------------------------

    def _execute_inner(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Full search pipeline — mirrors the original ``handle()`` function."""

        # ---- validate inputs ----
        query = str(arguments.get("query", "")).strip()
        if not query:
            raise _PluginValidationError("search_files requires a non-empty 'query'")

        mode_raw = arguments.get("mode", "auto")
        if mode_raw is None:
            mode = "auto"
        elif isinstance(mode_raw, str):
            mode = mode_raw.strip().lower() or "auto"
        else:
            raise _PluginValidationError("search_files 'mode' must be one of: auto, fast, deep")
        if mode not in self._SEARCH_MODE_VALUES:
            raise _PluginValidationError("search_files 'mode' must be one of: auto, fast, deep")

        path_filter_raw = arguments.get("path_filter")
        if path_filter_raw is None:
            path_filter = ""
        elif isinstance(path_filter_raw, str):
            path_filter = path_filter_raw.strip().lower()
        else:
            raise _PluginValidationError("search_files 'path_filter' must be a string when provided")

        limit = self._coerce_int(
            arguments.get("limit", 10),
            argument_name="search_files 'limit'",
            min_value=1,
            max_value=100,
            default=10,
        )
        time_budget_ms = self._coerce_int(
            arguments.get("time_budget_ms", 700),
            argument_name="search_files 'time_budget_ms'",
            min_value=100,
            max_value=10_000,
            default=700,
        )

        include_hidden_raw = arguments.get("include_hidden", False)
        if isinstance(include_hidden_raw, bool):
            include_hidden = include_hidden_raw
        elif isinstance(include_hidden_raw, str):
            normalized_bool = include_hidden_raw.strip().lower()
            if normalized_bool in {"1", "true", "yes", "on"}:
                include_hidden = True
            elif normalized_bool in {"0", "false", "no", "off"}:
                include_hidden = False
            else:
                raise _PluginValidationError("search_files 'include_hidden' must be a boolean")
        else:
            raise _PluginValidationError("search_files 'include_hidden' must be a boolean")

        max_depth_raw = arguments.get("max_depth")
        max_depth: int | None
        if max_depth_raw is None:
            max_depth = None
        elif isinstance(max_depth_raw, bool):
            raise _PluginValidationError("search_files 'max_depth' must be an integer when provided")
        else:
            try:
                parsed_depth = int(max_depth_raw)
            except (TypeError, ValueError) as exc:
                raise _PluginValidationError(
                    "search_files 'max_depth' must be an integer when provided"
                ) from exc
            if parsed_depth < 0 or parsed_depth > 128:
                raise _PluginValidationError("search_files 'max_depth' must be between 0 and 128")
            max_depth = parsed_depth

        continuation_token_raw = arguments.get("continuation_token")
        if continuation_token_raw not in (None, ""):
            raise _PluginValidationError(
                "search_files 'continuation_token' is no longer supported in strict runtime."
            )

        # ---- model-provided structured search params ----
        extensions_raw = arguments.get("extensions")
        model_extensions: set[str] = set()
        if isinstance(extensions_raw, list):
            for ext_item in extensions_raw:
                if isinstance(ext_item, str):
                    cleaned_ext = ext_item.strip().lower().lstrip(".")
                    if cleaned_ext:
                        model_extensions.add(cleaned_ext)

        folder_hint_raw = arguments.get("folder_hint")
        model_folder_hint: str = ""
        if isinstance(folder_hint_raw, str):
            model_folder_hint = folder_hint_raw.strip().lower()

        # ---- tokenize and expand ----
        raw_query_lower = query.lower()
        core_tokens = self._tokenize_search_query(raw_query_lower)
        query_tokens = self._expand_search_tokens(core_tokens)
        query_lower = " ".join(core_tokens) if core_tokens else raw_query_lower
        query_phrases = [
            item.strip()
            for item in re.findall(r'"([^"]+)"', query_lower)
            if item.strip()
        ]
        if {"gemini", "generated", "image"}.issubset(set(query_tokens)):
            query_phrases = list(dict.fromkeys([*query_phrases, "gemini generated image"]))

        # Prefer model-provided extensions; fall back to heuristic derivation.
        if model_extensions:
            extension_hints = model_extensions
        else:
            extension_hints = self._derive_extension_hints(query_tokens)

        # Prefer model-provided folder_hint; fall back to heuristic derivation.
        if model_folder_hint:
            folder_hints = {model_folder_hint}
        else:
            folder_hints = self._derive_folder_hints(query_tokens)

        spotlight_queries = self._derive_spotlight_query_variants(
            original_query=query,
            query_tokens=query_tokens,
            query_phrases=query_phrases,
            extension_hints=extension_hints,
        )
        all_candidates: list[dict[str, Any]] = []
        scanned_index_candidates = 0
        scanned_index_seed_entries = 0
        search_started = time.perf_counter()

        # ---- mode-dependent pipeline configuration ----
        mcfg = _MODE_CONFIG.get(mode, _MODE_CONFIG["auto"])
        do_seed = bool(mcfg["seed"])
        mdfind_timeout = int(mcfg["mdfind_timeout"])  # type: ignore[arg-type]
        collect_cap_mult = int(mcfg["collect_cap_mult"])  # type: ignore[arg-type]
        fts_fallback = bool(mcfg["fts_fallback"])
        seed_budget_cap_ms = int(mcfg["seed_budget_cap_ms"])  # type: ignore[arg-type]
        seed_entries_cap = int(mcfg["seed_entries_cap"])  # type: ignore[arg-type]

        tier_stats: dict[str, dict[str, object]] = {
            "spotlight": {"elapsed_ms": 0.0, "scanned": 0, "matched": 0},
            "fts": {"elapsed_ms": 0.0, "seed_scanned": 0, "seed_indexed": 0, "matched": 0},
        }

        def _remaining_budget_ms() -> int:
            elapsed_ms = int((time.perf_counter() - search_started) * 1000.0)
            return max(0, time_budget_ms - elapsed_ms)

        # ---- run Spotlight and FTS seeding in parallel ----
        budget_fraction = 0.5 if mode == "deep" else 0.25
        seed_budget_ms = min(
            seed_budget_cap_ms,
            max(60, int(_remaining_budget_ms() * budget_fraction)),
        )

        parallel_started = time.perf_counter()
        seed_stats: dict[str, Any] = {}

        if self._search_index_enabled and do_seed:
            with ThreadPoolExecutor(max_workers=2) as pool:
                spotlight_future = pool.submit(
                    self._search_spotlight,
                    queries=spotlight_queries,
                    query_lower=query_lower,
                    query_tokens=query_tokens,
                    query_phrases=query_phrases,
                    extension_hints=extension_hints,
                    folder_hints=folder_hints,
                    path_filter=path_filter,
                    limit=limit,
                    mdfind_timeout=mdfind_timeout,
                    collect_cap_mult=collect_cap_mult,
                )
                seed_max_entries = max(
                    120,
                    min(seed_entries_cap, limit * (250 if mode == "deep" else 120)),
                )
                seed_future = pool.submit(
                    self._seed_search_index_incremental,
                    query_tokens=query_tokens,
                    folder_hints=folder_hints,
                    include_hidden=include_hidden,
                    max_depth=max_depth,
                    max_entries=seed_max_entries,
                    max_seconds=max(0.05, seed_budget_ms / 1000.0),
                )

                spotlight_results, scanned_spotlight_candidates = spotlight_future.result()
                seed_stats = seed_future.result()
        else:
            spotlight_results, scanned_spotlight_candidates = self._search_spotlight(
                queries=spotlight_queries,
                query_lower=query_lower,
                query_tokens=query_tokens,
                query_phrases=query_phrases,
                extension_hints=extension_hints,
                folder_hints=folder_hints,
                path_filter=path_filter,
                limit=limit,
                mdfind_timeout=mdfind_timeout,
                collect_cap_mult=collect_cap_mult,
            )

        spotlight_elapsed_ms = round(
            (time.perf_counter() - parallel_started) * 1000.0, 3,
        )
        tier_stats["spotlight"] = {
            "elapsed_ms": spotlight_elapsed_ms,
            "scanned": scanned_spotlight_candidates,
            "matched": len(spotlight_results),
        }
        all_candidates.extend(spotlight_results)

        # ---- sequential: cross-pollinate then query FTS ----
        fts_started = time.perf_counter()
        if self._search_index_enabled:
            scanned_index_seed_entries = int(seed_stats.get("scanned", 0))
            self._upsert_search_index_entries(spotlight_results)

            index_results, scanned_index_candidates, fts_error = self._query_search_index(
                query_lower=query_lower,
                query_tokens=query_tokens,
                query_phrases=query_phrases,
                extension_hints=extension_hints,
                folder_hints=folder_hints,
                path_filter=path_filter,
                limit=limit,
                fts_fallback=fts_fallback,
                fts_tokens=core_tokens,
            )
            all_candidates.extend(index_results)

            tier_stats["fts"] = {
                "elapsed_ms": round((time.perf_counter() - fts_started) * 1000.0, 3),
                "seed_scanned": scanned_index_seed_entries,
                "seed_indexed": int(seed_stats.get("indexed", 0)),
                "matched": len(index_results),
                "scanned": scanned_index_candidates,
                "error": fts_error,
            }
        else:
            fts_error = False
            tier_stats["fts"] = {
                "elapsed_ms": round((time.perf_counter() - fts_started) * 1000.0, 3),
                "seed_scanned": 0,
                "seed_indexed": 0,
                "matched": 0,
                "scanned": 0,
                "error": False,
            }

        ranked_results = self._merge_ranked_search_candidates(
            candidates=all_candidates,
            query_lower=query_lower,
            query_tokens=query_tokens,
            query_phrases=query_phrases,
            extension_hints=extension_hints,
            folder_hints=folder_hints,
        )

        # ---- S2: directory co-location discovery (skip in fast mode) ----
        colocation_added = 0
        if mode != "fast" and ranked_results:
            siblings = self._discover_colocated_files(ranked_results)
            if siblings:
                colocation_added = len(siblings)
                ranked_results.extend(siblings)
                ranked_results.sort(
                    key=lambda item: (
                        int(item.get("score", 0)),
                        float(item.get("modified_at", 0.0)),
                    ),
                    reverse=True,
                )

        # ---- S3: apply cache boost from recent related searches ----
        cache_boosted = self._apply_cache_boost(
            current_query_tokens=query_tokens,
            candidates=ranked_results,
        )
        if cache_boosted:
            ranked_results.sort(
                key=lambda item: (
                    int(item.get("score", 0)),
                    float(item.get("modified_at", 0.0)),
                ),
                reverse=True,
            )

        total_scanned_entries = (
            scanned_spotlight_candidates
            + scanned_index_candidates
            + scanned_index_seed_entries
        )
        warnings: list[str] = []
        if fts_error:
            warnings.append(
                "Search index query failed; results may be incomplete. Try a different query."
            )

        final_matches = ranked_results[:limit]

        # ---- S3: cache results for follow-up searches ----
        self._cache_search_results(
            query_lower=query_lower,
            query_tokens=query_tokens,
            result_paths=tuple(r["path"] for r in final_matches),
            result_scores=tuple(int(r.get("score", 0)) for r in final_matches),
        )

        # ---- S4: diagnostics ----
        spotlight_content_floor_count = sum(
            1 for r in final_matches if r.get("spotlight_content_match")
        )

        return {
            "ok": True,
            "query": query,
            "path_filter": path_filter,
            "limit": limit,
            "mode": mode,
            "time_budget_ms": time_budget_ms,
            "include_hidden": include_hidden,
            "max_depth": max_depth,
            "scanned_entries": total_scanned_entries,
            "scanned_spotlight_candidates": scanned_spotlight_candidates,
            "scanned_index_candidates": scanned_index_candidates,
            "scanned_index_seed_entries": scanned_index_seed_entries,
            "search_scan_limit": self._search_scan_limit,
            "tier_stats": tier_stats,
            "warnings": warnings,
            "ranking_version": self._SEARCH_RANKING_VERSION,
            "diagnostics": {
                "spotlight_content_floor_applied": spotlight_content_floor_count,
                "colocation_siblings_added": colocation_added,
                "cache_overlap_boost_applied": cache_boosted,
            },
            "matches": final_matches,
        }

    # ------------------------------------------------------------------
    # FTS index management
    # ------------------------------------------------------------------

    def _default_search_index_path(self) -> Path:
        """Resolve where persistent search index data should live."""
        home = Path.home().expanduser().resolve(strict=False)
        if any(root == home or root in home.parents for root in self._allowed_roots):
            return home / "Library" / "Application Support" / "AIAgent" / "search" / "index.db"
        base = self._allowed_roots[0] if self._allowed_roots else Path.cwd()
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
        if self._allowed_roots:
            candidates.append(self._allowed_roots[0] / ".ai-agent-search" / "index.db")
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

    # ------------------------------------------------------------------
    # FTS query building
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # FTS index mutations
    # ------------------------------------------------------------------

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
                        self._tokenize_search_query(
                            f"{name.lower()} {relative_path.lower()} {path.lower()}"
                        )
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
        """Remove FTS index entries for files that no longer exist."""
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

    # ------------------------------------------------------------------
    # Incremental seeding
    # ------------------------------------------------------------------

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

        self._prune_stale_index_entries(max_checks=100)

        targets: list[tuple[Path, set[str]]] = []
        for root in self._allowed_roots:
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
                    for dir_name in dirnames:
                        if not include_hidden and dir_name.startswith("."):
                            continue
                        if relative_root == Path(".") and dir_name in top_level_skip_names:
                            continue
                        relative_child = (
                            relative_root / dir_name
                            if relative_root != Path(".")
                            else Path(dir_name)
                        )
                        if self._is_excluded_relative_path(relative_child):
                            continue
                        if self._path_has_noisy_components(current_root_path / dir_name):
                            continue
                        filtered_dirs.append(dir_name)
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
                            collected.append(
                                self._make_search_metadata(path, score=0, source="index")
                            )
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

    # ------------------------------------------------------------------
    # FTS querying
    # ------------------------------------------------------------------

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
        """Returns (results, scanned_count, fts_error_flag)."""
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
                    escaped_filter = (
                        path_filter
                        .replace("\\", "\\\\")
                        .replace("%", "\\%")
                        .replace("_", "\\_")
                    )
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
            semantic_boost = min(60.0, max(0.0, -fts_rank * 8.0))
            metadata["score"] = int(base_score + semantic_boost)
            metadata["match_signals"] = {
                **signals,
                "semantic_boost": round(semantic_boost, 3),
                "fts_rank": round(fts_rank, 6),
            }
            results.append(metadata)

        # ---- OR-based fallback for deep mode (F4) ----
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
                        metadata = self._make_search_metadata(
                            path, score=base_score, source="index",
                        )
                    except OSError:
                        continue
                    or_fts_rank = (
                        float(row["fts_rank"])
                        if isinstance(row["fts_rank"], (int, float))
                        else 0.0
                    )
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
    # Path helpers
    # ------------------------------------------------------------------

    def _path_within_allowed_roots(self, path: Path) -> bool:
        for root in self._allowed_roots:
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
        for root in self._allowed_roots:
            if path == root or root in path.parents:
                rel = path.relative_to(root)
                return self._is_excluded_relative_path(rel)
        return False

    @classmethod
    def _path_has_noisy_components(cls, path: Path) -> bool:
        parts = [part.lower() for part in path.parts]
        if any(part in cls._NOISY_COMPONENTS for part in parts):
            return True
        if any(
            any(part.endswith(suffix) for suffix in cls._NOISY_SUFFIXES)
            for part in parts
        ):
            return True

        path_lower = str(path).lower()
        if any(fragment in path_lower for fragment in cls._NOISY_PATH_FRAGMENTS):
            return True

        filename_lower = path.name.lower()
        return any(pattern.search(filename_lower) for pattern in cls._NOISY_FILENAME_PATTERNS)

    def _make_search_metadata(
        self, path: Path, *, score: int, source: str,
    ) -> dict[str, Any]:
        resolved = path.expanduser().resolve(strict=False)
        metadata = serialize_stat(resolved)
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
        for root in self._allowed_roots:
            if path == root or root in path.parents:
                relative = path.relative_to(root)
                return "." if not relative.parts else str(relative)
        return str(path)

    @staticmethod
    def _display_path_for_user(path: Path) -> str:
        try:
            home = Path.home().resolve(strict=False)
        except Exception:
            home = Path.home()

        if path == home or home in path.parents:
            relative = path.relative_to(home)
            return "~" if not relative.parts else f"~/{relative}"
        return str(path)

    def _ordered_walk_targets(self, root: Path) -> list[tuple[Path, set[str]]]:
        """Return prioritised walk targets for a root path."""
        home = Path.home().expanduser().resolve(strict=False)
        root_resolved = root.resolve(strict=False)

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
        for dir_name in self._HOME_PRIORITY_DIRS:
            candidate = (root / dir_name).resolve(strict=False)
            if not candidate.exists() or not candidate.is_dir():
                continue
            if not self._path_within_allowed_roots(candidate):
                continue
            if self._path_is_excluded(candidate):
                continue
            prioritized_targets.append((candidate, set()))
            skipped_names.add(dir_name)

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

    # ------------------------------------------------------------------
    # Tokenization and expansion
    # ------------------------------------------------------------------

    @classmethod
    def _tokenize_search_query(cls, query_lower: str) -> list[str]:
        raw_tokens = re.findall(r"[a-z0-9._+-]+", query_lower)
        tokens: list[str] = []
        seen: set[str] = set()
        for token in raw_tokens:
            cleaned = token.strip("._-")
            if not cleaned:
                continue
            if cleaned in cls._SEARCH_STOPWORDS:
                continue
            if len(cleaned) == 1 and cleaned not in cls._DIRECT_EXTENSION_TOKENS:
                continue
            if cleaned in seen:
                continue
            seen.add(cleaned)
            tokens.append(cleaned)
        return tokens

    @staticmethod
    def _normalize_token_forms(token: str) -> list[str]:
        """Generate singular/plural forms via suffix rules."""
        forms = [token]
        if token.endswith("ies") and len(token) > 4:
            forms.append(token[:-3] + "y")
        elif token.endswith("es") and len(token) > 3:
            forms.append(token[:-2])
        elif token.endswith("s") and len(token) > 2 and not token.endswith("ss"):
            forms.append(token[:-1])
        if not token.endswith("s"):
            forms.append(token + "s")
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

        if query_tokens:
            _add(f"-name:{' '.join(query_tokens[:4])}")

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

    # ------------------------------------------------------------------
    # Path scoring
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Spotlight integration
    # ------------------------------------------------------------------

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

        work_items = [
            (root, query)
            for root in self._allowed_roots if root.exists()
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
                        if (
                            is_content_query
                            and content_floor_count < self._MAX_CONTENT_FLOOR_RESULTS
                        ):
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

    # ------------------------------------------------------------------
    # Merge and rank
    # ------------------------------------------------------------------

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
                    default_signals = {
                        "spotlight_content_floor": float(self._SPOTLIGHT_CONTENT_FLOOR),
                    }
                else:
                    continue

            modified_at_raw = row.get("modified_at")
            modified_at = (
                float(modified_at_raw)
                if isinstance(modified_at_raw, (int, float))
                else now_ts
            )
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

        for source_name, items in source_candidates.items():
            items.sort(
                key=lambda x: (
                    x.get("_intrinsic_score", 0),
                    x.get("recency_boost", 0),
                ),
                reverse=True,
            )

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
    # Directory co-location discovery (S2)
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
        """Add sibling files from directories with multiple top results."""
        if len(ranked_results) < min_shared:
            return []

        existing_paths = {r.get("path", "") for r in ranked_results}

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
    # Search result cache (S3)
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
    # Utility
    # ------------------------------------------------------------------

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
            raise _PluginValidationError(
                f"{argument_name} must be an integer between {min_value} and {max_value}"
            )
        try:
            coerced = int(value)
        except (TypeError, ValueError) as exc:
            raise _PluginValidationError(
                f"{argument_name} must be an integer between {min_value} and {max_value}"
            ) from exc
        return max(min_value, min(max_value, coerced))


class _PluginValidationError(Exception):
    """Internal validation error — converted to ``Failure`` at the boundary."""
