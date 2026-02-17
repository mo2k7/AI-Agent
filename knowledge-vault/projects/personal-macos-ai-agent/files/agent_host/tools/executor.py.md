# File Doc: `agent_host/tools/executor.py`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `agent_host/tools/executor.py` |
| Doc Path | `projects/personal-macos-ai-agent/files/agent_host/tools/executor.py.md` |
| Language | Python |
| File Role | Central tool execution engine |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-02-08 |
| Last Major Edit (YYYY-MM-DD) | 2026-02-08 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Added initial documentation for unified-planning integration and planner privacy payloads |

## Responsibilities
- Dispatches tool invocations across supported tool handlers.
- Enforces tool rate limits and plan TTL behavior.
- Builds and validates unified planner engine on startup.
- Emits planner privacy payload metadata used by higher-level orchestration.
- Stores and resolves generated plans for `plan_ops`/`apply_ops` flow.

## Planner Integration Notes
- Hard-fails initialization when secure unified-planning requirements are not met.
- Exposes privacy/security metadata fields such as:
  - `boundary_payload_mode`
  - `path_data_sent_to_unified_planning`
  - `network_disabled_during_planning`
  - `policy_attestation_verified`
  - `package_hash_verified`

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-02-08 | AI Agent (Codex) | New file documentation | Added current-state summary for tool dispatch and secure planner integration | High |
