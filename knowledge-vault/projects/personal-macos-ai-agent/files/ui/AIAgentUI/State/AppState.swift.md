# File Doc: `ui/AIAgentUI/State/AppState.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `ui/AIAgentUI/State/AppState.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/State/AppState.swift.md` |
| Language | Swift |
| File Role | MainActor UI state coordinator |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-02-08 |
| Last Major Edit (YYYY-MM-DD) | 2026-02-08 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Synced with current Plan Mode state handling and tool-card suppression logic |

## What This File Does
- Owns message history, streaming state, connection state, and request lifecycle state.
- Coordinates IPC callbacks from backend to UI updates.
- Manages prompt submission/cancel lifecycle.
- Manages session/memory mode state and synchronization paths.

## Key Current Behaviors

### 1) Plan Mode Tool-Card Suppression
- Tracks `activePromptExecutionMode` for the active request.
- Uses `shouldSuppressToolCallCard(_:)` to hide planner tool cards while in plan mode.
- Suppression is applied in `handleToolCallUpdate(_:)` before tool-card attachment to messages.

### 2) Lifecycle Reset Correctness
- Clears active mode on completion, disconnect resets, and in-flight invalidation paths.
- Ensures stale request-mode state does not leak into later prompts.

### 3) Request and Streaming Coordination
- Sends prompt with current execution mode.
- Receives status/tool/result/error events and updates published state for UI components.

## Critical Dependencies
- `ui/AIAgentUI/IPC/IPCClient.swift`
- `ui/AIAgentUI/IPC/MessageProtocol.swift`
- `ui/AIAgentUI/Views/Components/ResponseBubble.swift`

## Tests That Exercise This File
- `ui/Tests/AIAgentUITests/RegressionFlowTests.swift`
- `ui/Tests/AIAgentUITests/ToolCallLifecycleStateTests.swift`
- `ui/Tests/AIAgentUITests/SessionMemoryModeSyncTests.swift`

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-02-08 | AI Agent (Codex) | Doc sync | Added current description of `activePromptExecutionMode` and planner-card suppression in plan mode | High |
| 2026-02-07 | AI Agent (Codex) | Runtime stability | Session/memory mode synchronization and lifecycle hardening updates | High |
