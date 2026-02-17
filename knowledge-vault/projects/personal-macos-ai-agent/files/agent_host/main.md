# File Doc: `agent_host/main.py`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `agent_host/main.py` |
| Doc Path | `projects/personal-macos-ai-agent/files/agent_host/main.md` |
| Language | Python 3.13+ |
| File Role | Backend runtime orchestrator + IPC prompt handler |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-02-08 |
| Last Major Edit (YYYY-MM-DD) | 2026-02-08 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Synced documentation with current Plan Mode behavior, unified-planning integration, and tool-card suppression flow |

## What This File Does
- Runs server mode (`run_server`) for Unix socket IPC.
- Handles prompt requests, cancellation, streaming responses, and tool lifecycle events.
- Coordinates execution modes: `direct` and `plan`.
- Performs plan-mode clarification generation and plan-mode guardrails.
- Integrates memory/session context and interaction persistence.

## Key Current Behaviors

### 1) Plan Mode Clarification
- Uses `PlanClarificationState` and `PlanPromptProfile` for dynamic follow-up questions.
- Extracts query signals (timeline/privacy/rollback/retention/etc.) to adapt question wording and options.
- Emits structured clarification text blocks (`Q1..Qn` and `A/B/C/D` options).

### 2) Plan Mode + Unified Planning
- For actionable file-operation prompts, unified planning is required before extended discovery behavior.
- Builds and injects `[UNIFIED_PLANNING_CONTEXT]` block from planner complexity/privacy metadata.
- Sends explicit rejection when discovery budget exceeds pre-planner allowance.

### 3) Tool-Card Visibility Control
- In Plan mode, planner tool calls are intentionally hidden from visible tool-card rendering.
- Backend gates planner tool notifications and omits planner tool payloads from result message tool-call lists when hidden.

### 4) NLP Preload Requirement
- Plan-mode NLP classifier preload runs at startup.
- If preload is configured required and model is unavailable, startup logs error and fails early.

## Critical Integrations
- `agent_host/tools/executor.py`: tool execution including planner/plan_ops/apply_ops.
- `agent_host/planning/unified_planner.py`: secure planner engine behavior and attestation outputs.
- `agent_host/nlp/intent_classifier.py`: clarification intent scoring.
- `agent_host/ipc/protocol.py`: status/error/result payload contracts.

## Risk and Reliability Notes
- This file is the highest orchestration-risk surface due to combined concerns: IPC, model I/O, memory, and tool control.
- Regression tests around plan mode, IPC runtime, and memory session flows should remain mandatory for each significant edit.

## Tests That Exercise This File
- `tests/unit/test_main_verbosity.py`
- `tests/unit/test_ipc_runtime.py`
- `tests/unit/test_memory_session_history_rpc_regression.py`
- `tests/unit/test_ipc_runtime.py::test_tool_chain_depth_limit_returns_last_non_terminal_result`

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-02-08 | AI Agent (Codex) | Doc sync | Updated for Plan Mode dynamic clarification, unified-planning bootstrap context, and planner-card suppression behavior | High |
| 2026-02-06 | AI Agent (Codex) | Reliability hardening | Added cancellation/in-flight lifecycle and error-correlation reliability work | High |
