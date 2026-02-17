# File Doc: `agent_host/nlp/intent_classifier.py`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `agent_host/nlp/intent_classifier.py` |
| Doc Path | `projects/personal-macos-ai-agent/files/agent_host/nlp/intent_classifier.py.md` |
| Language | Python |
| File Role | Plan-mode NLP intent and confidence classifier |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-02-08 |
| Last Major Edit (YYYY-MM-DD) | 2026-02-08 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Added initial file documentation for required spaCy-backed plan-mode classification path |

## Responsibilities
- Loads spaCy model candidates for plan-mode intent scoring.
- Produces classification result with source metadata (spaCy vs fallback).
- Returns confidence/signal values used by plan clarification routing.
- Exposes load errors used by startup preload enforcement.

## Runtime Notes
- When no configured model is installed, classifier reports load error (`no configured spaCy model is installed`).
- Backend startup can enforce this as fatal depending on preload-required configuration.

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-02-08 | AI Agent (Codex) | New file documentation | Added current-state classifier responsibilities and preload behavior notes | Medium |
