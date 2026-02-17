# File Doc: `tests/unit/test_ipc_runtime.py`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `tests/unit/test_ipc_runtime.py` |
| Doc Path | `projects/personal-macos-ai-agent/files/tests/unit/test_ipc_runtime.py.md` |
| Language | Python |
| File Role | Async IPC runtime reliability/regression tests |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-02-08 |
| Last Major Edit (YYYY-MM-DD) | 2026-02-08 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Synced with current full-suite behavior and async marker fix for depth-limit regression test |

## What This File Validates
- Parse/internal IPC error correlation behavior.
- Prompt cancellation lifecycle and terminal status guarantees.
- Plan mode guardrails (including restricted tools and chain behavior).
- Tool-chain depth-limit fallback behavior.

## Current Reliability Notes
- Async tests are executed with `pytest-anyio` (`@pytest.mark.anyio`).
- Depth-limit test `test_tool_chain_depth_limit_returns_last_non_terminal_result` now includes async marker and passes in full suite runs.

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-02-08 | AI Agent (Codex) | Suite stabilization | Added missing async marker to depth-limit test and revalidated full suite | High |
| 2026-02-07 | AI Agent (Codex) | Coverage expansion | Added focused IPC cancellation/error runtime scenarios | High |
