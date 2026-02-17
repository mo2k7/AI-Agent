# File Doc: `scripts/start_latest_app.sh`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `scripts/start_latest_app.sh` |
| Doc Path | `projects/personal-macos-ai-agent/files/scripts/start_latest_app.sh.md` |
| Language | Bash |
| File Role | Clean startup/build orchestration script |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-02-08 |
| Last Major Edit (YYYY-MM-DD) | 2026-02-08 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Added initial documentation for startup rebuild/relaunch and process cleanup behavior |

## Responsibilities
- Ensures singleton startup lock behavior.
- Collects and terminates related AI-agent processes and process groups.
- Rebuilds latest app/backend state before launch.
- Coordinates backend and frontend launch scripts.
- Produces startup artifacts/log output for diagnostics.

## Reliability Notes
- Includes guarded handling for empty PID/PGID arrays to avoid unbound variable failures.
- Uses process-tree collection to reduce orphaned child process risk during clean restart.

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-02-08 | AI Agent (Codex) | New file documentation | Documented clean startup orchestration and process cleanup behavior | High |
