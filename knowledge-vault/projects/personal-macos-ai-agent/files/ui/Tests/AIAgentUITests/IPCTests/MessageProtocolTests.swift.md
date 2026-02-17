# File Doc: `ui/Tests/AIAgentUITests/IPCTests/MessageProtocolTests.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `ui/Tests/AIAgentUITests/IPCTests/MessageProtocolTests.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/Tests/AIAgentUITests/IPCTests/MessageProtocolTests.swift.md` |
| Language | Swift |
| File Role | IPC Contract Tests |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-02-07 |
| Last Major Edit (YYYY-MM-DD) | 2026-02-07 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Added Swift Testing coverage for request encoding and parser behavior |

## Test Coverage
- `PromptRequest` encoding uses `params.prompt` (not legacy `text`) and includes selected model.
- `CancelRequest` encodes `params.request_id` correctly and omits it when nil.
- `IPCMessageParser` correctly parses status and error envelopes.
- Invalid JSON parse path returns `nil`.

## Dependencies
- `Testing` (Swift Testing framework)
- `@testable import AIAgentApp`
- Runtime types from `ui/AIAgentUI/IPC/MessageProtocol.swift`

