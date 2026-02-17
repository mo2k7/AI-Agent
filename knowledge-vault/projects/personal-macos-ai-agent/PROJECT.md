# Project: Personal macOS AI Agent

## Project Metadata
| Field | Value |
|---|---|
| Project Slug | `personal-macos-ai-agent` |
| Project Name | Personal macOS AI Agent |
| Doc Path | `projects/personal-macos-ai-agent/PROJECT.md` |
| Repository URL | Local (no remote) |
| Primary Language(s) | Python, Swift |
| Framework(s) | SwiftUI (UI), asyncio (backend IPC), unified-planning (planner engine) |
| Runtime/Platform | macOS |
| Version | `0.2.x` |
| Status | Active |
| Owner/Team | Individual Developer |
| Created Date (YYYY-MM-DD) | 2026-01-15 |
| Last Edited (YYYY-MM-DD) | 2026-02-08 |
| Last Major Edit (YYYY-MM-DD) | 2026-02-08 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Full codebase-state sync after Plan Mode stabilization, planner privacy hardening, startup rebuild pipeline fixes, and complete test verification |

---

## Executive Summary

### What This Project Does
Local-first macOS AI assistant with a SwiftUI desktop interface and a Python backend over Unix socket IPC.

### Current Product State
- Direct mode and Plan mode are both available.
- Plan mode now enforces structured clarification first, then planning output.
- Plan mode uses unified-planning as the mandatory planner backend for actionable file-operation planning paths.
- Planner privacy boundary is locked to numeric/boolean abstract payloads (no text/path payload transfer across the planning boundary).
- Startup path uses `scripts/start_latest_app.sh` bootstrap re-exec from the app to ensure clean rebuild/start from latest code.

### Current Health Snapshot (2026-02-08)
- Python full suite: `375 passed` (`poetry run pytest -q`)
- Swift full suite: `50 passed` (`cd ui && swift test`)
- Known warning: Torch JIT deprecation warning in one Python test path; non-blocking.

---

## System Architecture (Current)

### Components
1. Swift UI (`ui/`)
- Main state owner: `ui/AIAgentUI/State/AppState.swift`
- Clarification-option rendering and submission: `ui/AIAgentUI/Views/Components/ResponseBubble.swift`
- Bootstrap re-exec controller: `ui/AIAgentUI/App/AppDelegate.swift`

2. Python backend (`agent_host/`)
- Runtime orchestrator and IPC prompt handler: `agent_host/main.py`
- Tool execution and planner integration: `agent_host/tools/executor.py`
- Unified planning secure wrapper: `agent_host/planning/unified_planner.py`
- Plan-mode NLP intent classifier: `agent_host/nlp/intent_classifier.py`

3. Startup/runtime scripts (`scripts/`)
- Clean build orchestration: `scripts/start_latest_app.sh`
- Backend startup + required spaCy model verification/cache: `scripts/run_backend.sh`

### Plan Mode Behavior (Current)
- Clarification generation is dynamic and query-signal driven (`PlanPromptProfile` in `agent_host/main.py`).
- Clarification is emitted as a structured Q1..Qn payload with A/B/C/D options and optional free-form input.
- In Plan mode, planner tool cards are suppressed from user-facing message cards to keep output clean while preserving final answer output.
- Unified-planning context is injected into planning prompts when required, including complexity/privacy summary.

### Planner Security/Privacy Posture
- `unified-planning` license is validated as Apache-2.0 compatible at runtime.
- Planner boundary denies text and binary payloads.
- Network primitives are blocked while planning executes.
- Policy checksum attestation is enforced.
- Package hash attestation and optional pinned hash rotation are supported.
- Privacy metadata is surfaced via planner outputs (`path_data_sent_to_unified_planning=false`, `network_disabled_during_planning=true`).

---

## Repository Map (Focused)

| Path | Role | Status |
|---|---|---|
| `agent_host/main.py` | Request orchestration, Plan Mode routing, tool lifecycle, IPC emission | Active |
| `agent_host/tools/executor.py` | Tool dispatch (`planner`, `plan_ops`, `apply_ops`, file ops, etc.) | Active |
| `agent_host/planning/unified_planner.py` | Secure unified-planning abstraction | Active |
| `agent_host/nlp/intent_classifier.py` | Plan-mode NLP scoring/classification | Active |
| `ui/AIAgentUI/State/AppState.swift` | End-to-end UI state and IPC integration | Active |
| `ui/AIAgentUI/Views/Components/ResponseBubble.swift` | Clarification parser/rendering and message bubble behavior | Active |
| `ui/AIAgentUI/App/AppDelegate.swift` | Startup bootstrap re-exec flow | Active |
| `scripts/start_latest_app.sh` | Clean rebuild + process cleanup + launch pipeline | Active |
| `scripts/run_backend.sh` | Backend process launch and spaCy model enforcement/cache | Active |
| `tests/` | Python runtime/unit/golden coverage | Active |
| `ui/Tests/` | Swift IPC/state/presentation tests | Active |

---

## Operations Notes

### Startup Flow
1. `swift run AIAgentApp`
2. App checks bootstrap env and re-execs through `scripts/start_latest_app.sh` when needed.
3. Script performs process cleanup, clean build, dependency checks, backend startup, and frontend launch.
4. Backend startup validates required spaCy model and caches stamp to avoid unnecessary reinstalls.

### Plan Mode Runtime Constraints
- Plan mode rejects destructive execution behavior and requires planning-first sequencing.
- For actionable file-operation prompts, unified planning must be initialized before excessive discovery-tool drift.

---

## Current Risks / Watchlist

- Plan-mode quality remains sensitive to prompt ambiguity; clarification stage is critical and should remain mandatory for low-confidence prompts.
- spaCy model preload is required by default; missing model blocks backend startup until installed.
- Bootstrap scripts rely on shell tool availability (`bash`, `poetry`, process utilities), so environment parity matters.

---

## Major Edits Log (Append-Only)

| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-02-08 | AI Agent (Codex) | Codebase-state synchronization | Rewrote project doc to match current Plan Mode, unified-planning security posture, startup pipeline, and full test baselines (`375` Python + `50` Swift) | High |
| 2026-02-07 | AI Agent (Codex) | Reliability checklist sync | Documented reliability/stability workstreams and validation snapshots | High |
| 2026-01-18 | AI Agent (Codex) | Dependency refresh | Updated runtime and dependency documentation baselines | Medium |
| 2026-01-15 | Kilo Code | Initial project setup | Created initial project overview document | High |
