# File Doc: `ui/AIAgentUI/Security/PermissionsManager.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `ui/AIAgentUI/Security/PermissionsManager.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/Security/PermissionsManager.swift.md` |
| Language | Swift |
| File Role | Permission Orchestration |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-02-06 |
| Last Major Edit (YYYY-MM-DD) | 2026-02-06 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Reduce intrusive automation probing during permission polling and preserve reliable permission state updates |

## Responsibilities
- Tracks TCC permission statuses (accessibility, automation, full disk access).
- Triggers user-facing permission request flows.
- Opens System Settings for required permission panes.
- Provides polling loop for post-request status refresh.

## 2026-02-06 Reliability Changes
- Added `performAutomationProbe` control to `checkAllPermissions` and `checkPermission`.
- Polling now uses periodic automation probe instead of probing every cycle.
- Reduced repeated AppleScript side-effects during permission polling.

## Relations
- Consumed by `ui/AIAgentUI/Views/MainPanelView.swift`.
- Indirectly controls startup/user guidance behavior in `ui/AIAgentUI/App/AppDelegate.swift`.
- Contributes app state signals consumed by `ui/AIAgentUI/State/AppState.swift`.
