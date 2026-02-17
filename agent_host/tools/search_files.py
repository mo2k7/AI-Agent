"""Handler for the ``search_files`` tool."""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from agent_host.tools.executor import ToolExecutor

from agent_host.tools.executor import ToolExecutionError


def handle(executor: ToolExecutor, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Execute the search_files tool."""
    query = str(arguments.get("query", "")).strip()
    if not query:
        raise ToolExecutionError("search_files requires a non-empty 'query'")

    mode_raw = arguments.get("mode", "auto")
    if mode_raw is None:
        mode = "auto"
    elif isinstance(mode_raw, str):
        mode = mode_raw.strip().lower() or "auto"
    else:
        raise ToolExecutionError("search_files 'mode' must be one of: auto, fast, deep")
    if mode not in executor._SEARCH_MODE_VALUES:
        raise ToolExecutionError("search_files 'mode' must be one of: auto, fast, deep")

    path_filter_raw = arguments.get("path_filter")
    if path_filter_raw is None:
        path_filter = ""
    elif isinstance(path_filter_raw, str):
        path_filter = path_filter_raw.strip().lower()
    else:
        raise ToolExecutionError("search_files 'path_filter' must be a string when provided")

    limit = executor._coerce_int(
        arguments.get("limit", 10),
        argument_name="search_files 'limit'",
        min_value=1,
        max_value=100,
        default=10,
    )
    time_budget_ms = executor._coerce_int(
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
            raise ToolExecutionError("search_files 'include_hidden' must be a boolean")
    else:
        raise ToolExecutionError("search_files 'include_hidden' must be a boolean")

    max_depth_raw = arguments.get("max_depth")
    max_depth: int | None
    if max_depth_raw is None:
        max_depth = None
    elif isinstance(max_depth_raw, bool):
        raise ToolExecutionError("search_files 'max_depth' must be an integer when provided")
    else:
        try:
            parsed_depth = int(max_depth_raw)
        except (TypeError, ValueError) as exc:
            raise ToolExecutionError("search_files 'max_depth' must be an integer when provided") from exc
        if parsed_depth < 0 or parsed_depth > 128:
            raise ToolExecutionError("search_files 'max_depth' must be between 0 and 128")
        max_depth = parsed_depth

    continuation_token_raw = arguments.get("continuation_token")
    if continuation_token_raw not in (None, ""):
        raise ToolExecutionError(
            "search_files 'continuation_token' is no longer supported in strict runtime."
        )

    # --- Model-provided structured search params (Phase 3) ---
    # When the model provides explicit extensions/folder_hint, prefer
    # them over heuristic derivation from query tokens.
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

    raw_query_lower = query.lower()
    query_tokens = executor._tokenize_search_query(raw_query_lower)
    query_tokens = executor._expand_search_tokens(query_tokens)
    query_lower = " ".join(query_tokens) if query_tokens else raw_query_lower
    query_phrases = [item.strip() for item in re.findall(r'"([^"]+)"', query_lower) if item.strip()]
    if {"gemini", "generated", "image"}.issubset(set(query_tokens)):
        query_phrases = list(dict.fromkeys([*query_phrases, "gemini generated image"]))
    spotlight_queries = executor._derive_spotlight_query_variants(
        original_query=query,
        query_tokens=query_tokens,
        query_phrases=query_phrases,
    )

    # Prefer model-provided extensions; fall back to heuristic derivation.
    if model_extensions:
        extension_hints = model_extensions
    else:
        extension_hints = executor._derive_extension_hints(query_tokens)

    # Prefer model-provided folder_hint; fall back to heuristic derivation.
    if model_folder_hint:
        folder_hints = {model_folder_hint}
    else:
        folder_hints = executor._derive_folder_hints(query_tokens)
    all_candidates: list[dict[str, Any]] = []
    scanned_walk_entries = 0
    scanned_index_candidates = 0
    scanned_index_seed_entries = 0
    truncated = False
    truncated_reason = ""
    next_token = ""
    search_started = time.perf_counter()

    tier_stats: dict[str, dict[str, object]] = {
        "spotlight": {"elapsed_ms": 0.0, "scanned": 0, "matched": 0},
        "fts": {"elapsed_ms": 0.0, "seed_scanned": 0, "seed_indexed": 0, "matched": 0},
    }

    def _remaining_budget_ms() -> int:
        elapsed_ms = int((time.perf_counter() - search_started) * 1000.0)
        return max(0, time_budget_ms - elapsed_ms)

    # --- Run Spotlight and FTS seeding in parallel ---
    # Spotlight (mdfind subprocesses) and FTS seeding (filesystem walk + SQLite
    # inserts) are completely independent — no shared mutable state between them.
    # Running them concurrently cuts wall-clock time to max(spotlight, seed)
    # instead of spotlight + seed.
    #
    # The cross-pollination step (_upsert_search_index_entries) and FTS query
    # depend on BOTH completing, so they remain sequential afterward.

    # Pre-compute seed budget before launching parallel work (uses wall-clock).
    seed_budget_ms = min(220, max(60, int(_remaining_budget_ms() * 0.25)))

    parallel_started = time.perf_counter()
    seed_stats: dict[str, Any] = {}

    if executor._search_index_enabled:
        with ThreadPoolExecutor(max_workers=2) as pool:
            spotlight_future = pool.submit(
                executor._search_spotlight,
                queries=spotlight_queries,
                query_lower=query_lower,
                query_tokens=query_tokens,
                query_phrases=query_phrases,
                extension_hints=extension_hints,
                folder_hints=folder_hints,
                path_filter=path_filter,
                limit=limit,
            )
            seed_future = pool.submit(
                executor._seed_search_index_incremental,
                query_tokens=query_tokens,
                folder_hints=folder_hints,
                include_hidden=include_hidden,
                max_depth=max_depth,
                max_entries=max(120, min(1200, limit * 120)),
                max_seconds=max(0.05, seed_budget_ms / 1000.0),
            )

            spotlight_results, scanned_spotlight_candidates = spotlight_future.result()
            seed_stats = seed_future.result()
    else:
        # No FTS — run Spotlight alone (still benefits from internal mdfind parallelism).
        spotlight_results, scanned_spotlight_candidates = executor._search_spotlight(
            queries=spotlight_queries,
            query_lower=query_lower,
            query_tokens=query_tokens,
            query_phrases=query_phrases,
            extension_hints=extension_hints,
            folder_hints=folder_hints,
            path_filter=path_filter,
            limit=limit,
        )

    spotlight_elapsed_ms = round((time.perf_counter() - parallel_started) * 1000.0, 3)
    tier_stats["spotlight"] = {
        "elapsed_ms": spotlight_elapsed_ms,
        "scanned": scanned_spotlight_candidates,
        "matched": len(spotlight_results),
    }
    all_candidates.extend(spotlight_results)

    # --- Sequential: cross-pollinate then query FTS ---
    fts_started = time.perf_counter()
    if executor._search_index_enabled:
        scanned_index_seed_entries = int(seed_stats.get("scanned", 0))

        # Keep semantic index fresh with high-confidence spotlight candidates.
        executor._upsert_search_index_entries(spotlight_results)

        index_results, scanned_index_candidates, fts_error = executor._query_search_index(
            query_lower=query_lower,
            query_tokens=query_tokens,
            query_phrases=query_phrases,
            extension_hints=extension_hints,
            folder_hints=folder_hints,
            path_filter=path_filter,
            limit=limit,
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

    ranked_results = executor._merge_ranked_search_candidates(
        candidates=all_candidates,
        query_lower=query_lower,
        query_tokens=query_tokens,
        query_phrases=query_phrases,
        extension_hints=extension_hints,
        folder_hints=folder_hints,
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

    return {
        "ok": True,
        "query": query,
        "path_filter": path_filter,
        "limit": limit,
        "mode": mode,
        "time_budget_ms": time_budget_ms,
        "include_hidden": include_hidden,
        "max_depth": max_depth,
        "continuation_token": "",
        "next_token": next_token,
        "scanned_entries": total_scanned_entries,
        "scanned_spotlight_candidates": scanned_spotlight_candidates,
        "scanned_index_candidates": scanned_index_candidates,
        "scanned_index_seed_entries": scanned_index_seed_entries,
        "scanned_walk_entries": scanned_walk_entries,
        "search_scan_limit": executor.search_scan_limit,
        "truncated": truncated,
        "truncated_reason": truncated_reason,
        "tier_stats": tier_stats,
        "warnings": warnings,
        "ranking_version": executor._SEARCH_RANKING_VERSION,
        "matches": ranked_results[:limit],
    }
