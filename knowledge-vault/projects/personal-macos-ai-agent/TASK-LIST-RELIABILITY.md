# Reliability and Stability Task List (Active)

**Project:** Personal macOS AI Agent  
**Last Updated:** 2026-02-08  
**Owner:** AI Agent (Codex)  
**Scope:** Plan Mode stability, unified-planning enforcement and privacy boundaries, startup pipeline reliability, IPC/runtime correctness, and documentation/graph sync.

## Completed Reliability Foundation
- [x] True prompt cancellation and in-flight task tracking in backend.
- [x] Blocking Gemini calls moved off event loop.
- [x] Parse/internal error request-id correlation hardened.
- [x] Swift cancel path uses targeted `request_id`.
- [x] Socket discovery and startup health checks hardened.
- [x] Session/memory mode synchronization reliability fixed.
- [x] SQLite sidecar cleanup on session deletion added.

## Completed Plan Mode Stabilization (2026-02-08)
- [x] Dynamic plan-clarification signal extraction added (`PlanPromptProfile` in `agent_host/main.py`).
- [x] Clarification output aligned to structured Q/A flow with A/B/C/D options and free-form support.
- [x] Plan Mode planner-card suppression added in backend and UI so planner tool cards do not pollute visible response bubbles.
- [x] Unified-planning bootstrap context integrated into planning pipeline with complexity/privacy metadata.
- [x] Plan-mode guardrails enforce planner-first behavior for actionable file-operation prompts with discovery budget checks.
- [x] Plan-mode NLP preload path made required by default with startup-time model checks.

## Completed Unified-Planning Security Controls
- [x] Apache-2.0-compatible license verification at runtime.
- [x] Boundary payload mode locked to numeric/boolean-only abstractions.
- [x] String/binary payload crossing planner boundary blocked.
- [x] Network primitives blocked during planner execution.
- [x] Policy checksum attestation verified.
- [x] Package hash attestation and pinning support enabled.
- [x] Optional signed hash-store auto-rotation path enabled for comma-separated digest histories.

## Completed Startup Pipeline Stabilization
- [x] App bootstrap re-exec through `scripts/start_latest_app.sh` wired and active.
- [x] Process-group cleanup hardened to avoid unbound-array failures in script shutdown path.
- [x] Backend runner made portable without brittle shell utilities (`setsid` fallback issues removed).
- [x] Required spaCy model verify/install/cache workflow enforced in `scripts/run_backend.sh`.

## Validation Snapshot (Current)
- Python full test suite: `375 passed` (`poetry run pytest -q`).
- Swift full test suite: `50 passed` (`cd ui && swift test`).
- Targeted regression fixed: missing async marker in `tests/unit/test_ipc_runtime.py` depth-limit test.

## Open Items
- [ ] Add explicit automated integration test for end-to-end Plan Mode UI clarification submission loop (UI + backend contract together).
- [ ] Add startup script smoke test in CI-like local command set (script invocation + socket readiness assertions).

## Notes
- Historical snapshots with lower pass counts were retained in older docs for chronology.
- This file reflects the latest reliable baseline for the current codebase state.

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-02-08 | AI Agent (Codex) | Full-state sync | Consolidated latest Plan Mode, planner security, startup, and full-test validation state into one active checklist | High |
| 2026-02-07 | AI Agent (Codex) | Reliability tracking | Added bug-sweep and memory/session stabilization checklist entries | High |
| 2026-02-06 | AI Agent (Codex) | Initial reliability sweep | Created reliability checklist and first validation snapshot | High |
