# File Doc: `.env.example`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `.env.example` |
| Doc Path | `projects/personal-macos-ai-agent/files/env.example.md` |
| Language | Environment Config |
| File Role | Local setup template |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-02-06 |
| Last Major Edit (YYYY-MM-DD) | 2026-02-06 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Added missing setup template referenced by README |

## Purpose
- Provides starter environment variable template for local setup.
- Prevents onboarding failure due to missing referenced file.

## Current Variables
- `GOOGLE_API_KEY=your-api-key-here`

## Relations
- Referenced by `README.md` setup section.
- Read by `agent_host/main.py` via `load_dotenv()`.
