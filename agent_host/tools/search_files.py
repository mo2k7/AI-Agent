"""Handler for the ``search_files`` tool."""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from agent_host.tools.executor import ToolExecutor

from agent_host.tools.executor import ToolExecutionError

# Mode-aware configuration — controls pipeline behavior per search strategy.
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
    core_tokens = executor._tokenize_search_query(raw_query_lower)
    # Expanded tokens include plural/singular forms for broader path scoring.
    # FTS queries use core_tokens only (expanded forms can break AND semantics
    # when e.g. "pythons"* doesn't match the indexed token "python").
    query_tokens = executor._expand_search_tokens(core_tokens)
    query_lower = " ".join(core_tokens) if core_tokens else raw_query_lower
    query_phrases = [item.strip() for item in re.findall(r'"([^"]+)"', query_lower) if item.strip()]
    if {"gemini", "generated", "image"}.issubset(set(query_tokens)):
        query_phrases = list(dict.fromkeys([*query_phrases, "gemini generated image"]))

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

    spotlight_queries = executor._derive_spotlight_query_variants(
        original_query=query,
        query_tokens=query_tokens,
        query_phrases=query_phrases,
        extension_hints=extension_hints,
    )
    all_candidates: list[dict[str, Any]] = []
    scanned_index_candidates = 0
    scanned_index_seed_entries = 0
    search_started = time.perf_counter()

    # --- Mode-dependent pipeline configuration ---
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

    # --- Run Spotlight and FTS seeding in parallel ---
    # Spotlight (mdfind subprocesses) and FTS seeding (filesystem walk + SQLite
    # inserts) are completely independent — no shared mutable state between them.
    # Running them concurrently cuts wall-clock time to max(spotlight, seed)
    # instead of spotlight + seed.
    #
    # The cross-pollination step (_upsert_search_index_entries) and FTS query
    # depend on BOTH completing, so they remain sequential afterward.

    # Pre-compute seed budget before launching parallel work (uses wall-clock).
    budget_fraction = 0.5 if mode == "deep" else 0.25
    seed_budget_ms = min(seed_budget_cap_ms, max(60, int(_remaining_budget_ms() * budget_fraction)))

    parallel_started = time.perf_counter()
    seed_stats: dict[str, Any] = {}

    if executor._search_index_enabled and do_seed:
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
                mdfind_timeout=mdfind_timeout,
                collect_cap_mult=collect_cap_mult,
            )
            seed_max_entries = max(120, min(seed_entries_cap, limit * (250 if mode == "deep" else 120)))
            seed_future = pool.submit(
                executor._seed_search_index_incremental,
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
        # fast mode or no FTS — run Spotlight alone (still benefits from internal
        # mdfind parallelism).
        spotlight_results, scanned_spotlight_candidates = executor._search_spotlight(
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

    ranked_results = executor._merge_ranked_search_candidates(
        candidates=all_candidates,
        query_lower=query_lower,
        query_tokens=query_tokens,
        query_phrases=query_phrases,
        extension_hints=extension_hints,
        folder_hints=folder_hints,
    )

    # --- S2: Directory co-location discovery (skip in fast mode) ---
    colocation_added = 0
    if mode != "fast" and ranked_results:
        siblings = executor._discover_colocated_files(ranked_results)
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

    # --- S3: Apply cache boost from recent related searches ---
    cache_boosted = executor._apply_cache_boost(
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

    # --- S3: Cache results for follow-up searches ---
    executor._cache_search_results(
        query_lower=query_lower,
        query_tokens=query_tokens,
        result_paths=tuple(r["path"] for r in final_matches),
        result_scores=tuple(int(r.get("score", 0)) for r in final_matches),
    )

    # --- S4: Diagnostics ---
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
        "search_scan_limit": executor.search_scan_limit,
        "tier_stats": tier_stats,
        "warnings": warnings,
        "ranking_version": executor._SEARCH_RANKING_VERSION,
        "diagnostics": {
            "spotlight_content_floor_applied": spotlight_content_floor_count,
            "colocation_siblings_added": colocation_added,
            "cache_overlap_boost_applied": cache_boosted,
        },
        "matches": final_matches,
    }
