# File Doc: `agent_host/system_prompt.py`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `agent_host/system_prompt.py` |
| Doc Path | `projects/personal-macos-ai-agent/files/agent_host/system_prompt.md` |
| Language | Python |
| File Role | Prompt Configuration Loader |
| Ownership | Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-02-08 |
| Last Major Edit (YYYY-MM-DD) | 2026-02-08 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Restore missing file-level documentation entry referenced by the global registry |

---

## Purpose
Loads the backend system prompt from markdown/default sources and exposes stable prompt text for request orchestration.

## Key Responsibilities
- Load system prompt content from configured sources.
- Provide deterministic prompt text for runtime use.
- Keep prompt-loading behavior compatible with hot-reload workflows.

## Boundaries
- Does not execute model calls.
- Does not manage IPC or request lifecycles.
- Does not mutate memory/session storage.
