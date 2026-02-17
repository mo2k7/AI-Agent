# File Doc: `agent_host/planning/unified_planner.py`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `agent_host/planning/unified_planner.py` |
| Doc Path | `projects/personal-macos-ai-agent/files/agent_host/planning/unified_planner.py.md` |
| Language | Python |
| File Role | Secure wrapper for unified-planning |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-02-08 |
| Last Major Edit (YYYY-MM-DD) | 2026-02-08 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Added initial file-level documentation for planner security and privacy boundary behavior |

## Responsibilities
- Loads and validates `unified-planning` package availability and license compatibility.
- Enforces planner policy attestation checksum.
- Computes and validates package hash pinning.
- Supports optional signed hash-store auto-rotation.
- Blocks network primitives while planner operations execute.
- Enforces strict non-text/non-binary boundary payload policy.
- Provides `analyze_complexity(...)` and `plan_order(...)` APIs used by tool executor.

## Security Highlights
- Apache-2.0 token verification.
- SHA-256 policy checksum attestation.
- HMAC-signed hash store for rotation support.
- Numeric/boolean abstract payload-only boundary checks.
- Explicit blocking of socket/network APIs during planning execution.

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-02-08 | AI Agent (Codex) | New file documentation | Documented planner boundary, attestation, and ordering behavior | High |
