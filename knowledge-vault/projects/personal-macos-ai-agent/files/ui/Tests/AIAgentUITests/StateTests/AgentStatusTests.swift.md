# File Doc: `ui/Tests/AIAgentUITests/StateTests/AgentStatusTests.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `ui/Tests/AIAgentUITests/StateTests/AgentStatusTests.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/Tests/AIAgentUITests/StateTests/AgentStatusTests.swift.md` |
| Language | Swift |
| File Role | State Model Tests |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-02-07 |
| Last Major Edit (YYYY-MM-DD) | 2026-02-07 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Added deterministic tests for status mapping and state semantics |

## Test Coverage
- Raw backend status mapping into `AgentStatus` enum (`calling_tool`, `error`).
- Busy/submission flags (`isBusy`, `canSubmit`) for representative statuses.
- Codable round-trip for structured status values.

## Dependencies
- `Testing` (Swift Testing framework)
- `@testable import AIAgentApp`
- Runtime type from `ui/AIAgentUI/State/AgentStatus.swift`

