# File Doc: `tests/golden/fixtures/run_automation_001.json`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `tests/golden/fixtures/run_automation_001.json` |
| Doc Path | `projects/personal-macos-ai-agent/files/tests/golden/fixtures/run_automation_001.json.md` |
| Language | JSON |
| File Role | Golden Test Fixture |
| Ownership | QA / Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Align run_automation fixture fields with schema (name/inputs) |
| Lines of Code (LOC) | 30 |
| Cyclomatic Complexity | N/A |
| Test Coverage | N/A (fixture data) |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
Provides a canonical run_automation tool call fixture for golden parsing tests.

**Detailed responsibilities:**
- Defines a mock Gemini response with run_automation arguments
- Specifies expected tool call name and inputs payload

### What this file must NOT do (boundaries)
**Out of scope:**
- Validate allowlist rules or execute automations
- Include multiple automation scenarios

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| `tests/golden/test_golden_tool_calls.py` | Parse and validate tool call output | Per test run | pytest assertions |

---

## Fixture Schema
| Field | Type | Description |
|---|---|---|
| `test_id` | string | Fixture identifier |
| `description` | string | Scenario summary |
| `mock_gemini_response` | object | Simulated Gemini response payload |
| `expected_tool_call` | object | Expected name/arguments |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Agent (Codex) | Schema alignment | Updated fixture to use name/inputs fields | Medium |
