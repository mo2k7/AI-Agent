# File Doc: `scripts/run_backend.sh`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `scripts/run_backend.sh` |
| Doc Path | `projects/personal-macos-ai-agent/files/scripts/run_backend.sh.md` |
| Language | Bash |
| File Role | Backend launcher and NLP model readiness gate |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-02-08 |
| Last Major Edit (YYYY-MM-DD) | 2026-02-08 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Added initial documentation for required spaCy model verification/install/cache workflow |

## Responsibilities
- Validates Python/Poetry-backed backend launch path.
- Ensures required plan-mode spaCy model exists and is loadable.
- Installs missing spaCy model when required.
- Caches model fingerprint stamp to avoid unnecessary reinstalls.
- Starts backend server and waits for Unix socket readiness.

## Reliability Notes
- Fails fast with explicit diagnostics if socket is not created within timeout.
- Emits backend log tail on startup failures to reduce debugging latency.

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-02-08 | AI Agent (Codex) | New file documentation | Documented startup model gate and socket-readiness launch behavior | High |
