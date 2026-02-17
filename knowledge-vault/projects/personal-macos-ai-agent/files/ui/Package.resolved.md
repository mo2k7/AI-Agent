# File Doc: `ui/Package.resolved`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `ui/Package.resolved` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/Package.resolved.md` |
| Language | JSON |
| File Role | Dependency Lockfile |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-02-07 |
| Last Major Edit (YYYY-MM-DD) | 2026-02-07 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Locks Swift package graph after adding `swift-testing` for test framework compatibility |

## Responsibilities
- Pins Swift package dependency revisions used by SPM.
- Ensures reproducible `swift build` and `swift test` behavior across environments.
- Tracks resolved revision for `swift-testing`.

## Notes
- Regenerate with `swift package resolve` when dependency versions in `ui/Package.swift` change.

