# File Doc: `ui/Tests/AIAgentUITests/IPCTests/StreamingParserTests.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `ui/Tests/AIAgentUITests/IPCTests/StreamingParserTests.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/Tests/AIAgentUITests/IPCTests/StreamingParserTests.swift.md` |
| Language | Swift |
| File Role | Streaming/Dispatch Tests |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-02-07 |
| Last Major Edit (YYYY-MM-DD) | 2026-02-07 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Added behavioral tests for socket stream parsing and message dispatcher flow |

## Test Coverage
- Fragmented stream chunks are buffered and emitted once a newline-delimited JSON line is complete.
- Invalid JSON emits parser error callback.
- `MessageDispatcher`:
  - accumulates stream text updates;
  - emits completion for result messages;
  - emits error callback for error envelopes.

## Dependencies
- `Testing` (Swift Testing framework)
- `@testable import AIAgentApp`
- Runtime types from `ui/AIAgentUI/IPC/StreamingParser.swift` and `ui/AIAgentUI/IPC/MessageProtocol.swift`

