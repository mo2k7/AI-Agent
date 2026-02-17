# File Doc: `tests/golden/fixtures/get_metadata_001.json`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `tests/golden/fixtures/get_metadata_001.json` |
| Doc Path | `projects/personal-macos-ai-agent/files/tests/golden/fixtures/get_metadata_001.json.md` |
| Language | JSON |
| File Role | Golden Test Fixture |
| Ownership | QA / Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Document golden fixture coverage |
| Lines of Code (LOC) | 30 |
| Cyclomatic Complexity | N/A |
| Test Coverage | N/A (fixture data) |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
Provides a canonical get_metadata tool call fixture for golden parsing tests.

**Detailed responsibilities:**
- Defines a mock Gemini response with get_metadata arguments
- Provides expected tool call data for parser validation

### What this file must NOT do (boundaries)
**Out of scope:**
- Validate schema correctness (done in tests)
- Include runtime logic

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
| 2026-01-18 | AI Agent (Codex) | Documentation | Added fixture documentation | Low |
