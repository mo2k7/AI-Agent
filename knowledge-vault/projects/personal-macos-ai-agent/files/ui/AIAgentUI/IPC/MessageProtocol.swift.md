# File Doc: `ui/AIAgentUI/IPC/MessageProtocol.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `ui/AIAgentUI/IPC/MessageProtocol.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/IPC/MessageProtocol.swift.md` |
| Language | Swift |
| File Role | IPC Message Contract |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-02-06 |
| Last Major Edit (YYYY-MM-DD) | 2026-02-06 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Add targeted cancel parameters to align frontend cancellation with backend request-task cancellation |

## Responsibilities
- Defines JSON-RPC request/response structures for Swift ↔ Python IPC.
- Encodes prompt/cancel/ping/reload/version requests.
- Decodes status/stream/tool/result/error/system responses.
- Provides typed parser from raw JSON to Swift enum message cases.

## 2026-02-06 Reliability Changes
- `CancelRequest` now includes optional `params.request_id` field (encoded as `request_id`).
- Enables frontend to cancel specific in-flight backend requests.

## Relations
- Used by `ui/AIAgentUI/IPC/SocketManager.swift` for transport serialization.
- Parsed payloads are dispatched by `ui/AIAgentUI/IPC/StreamingParser.swift`.
- Contract pair with backend definitions in `agent_host/ipc/protocol.py`.
