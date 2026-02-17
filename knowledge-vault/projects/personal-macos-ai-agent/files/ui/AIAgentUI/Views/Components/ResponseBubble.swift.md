# File Doc: `ui/AIAgentUI/Views/Components/ResponseBubble.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `ui/AIAgentUI/Views/Components/ResponseBubble.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/Views/Components/ResponseBubble.swift.md` |
| Language | Swift |
| File Role | Assistant response renderer + plan-clarification interaction UI |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-02-08 |
| Last Major Edit (YYYY-MM-DD) | 2026-02-08 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Synced with current plan-clarification parsing, option ordering, and click-to-submit flow |

## What This File Does
- Renders response markdown blocks and streaming content.
- Parses plan clarification payloads from assistant text.
- Displays clickable A/B/C/D options for each clarification question.
- Supports both option-based answer submission and free-form custom submission.

## Plan Clarification Rendering Path
- Detects clarification payloads using `parsePlanClarificationPayload(_:)`.
- Parses `Qn.` lines and `A) ... D) ...` option lines.
- Sorts option keys to ensure stable display order.
- Tracks selections in local state and only enables "Send Answers" once all questions are selected.

## Interaction Behavior
- Option taps update per-question selection state.
- Submit action composes concise answer text (e.g., `Q1:A, Q2:D`) and forwards through app state prompt submission path.
- Free-form optional details can be sent separately.

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-02-08 | AI Agent (Codex) | Doc sync | Updated to describe plan clarification parser, ordered option rendering, and submission gating behavior | High |
| 2026-01-18 | AI Agent (Codex) | Streaming polish | Added shimmer/stream behavior and accessibility updates | Medium |
