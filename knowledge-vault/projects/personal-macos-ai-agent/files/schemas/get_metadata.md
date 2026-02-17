# File Doc: `schemas/get_metadata.json`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `schemas/get_metadata.json` |
| Doc Path | `projects/personal-macos-ai-agent/files/schemas/get_metadata.md` |
| Language | JSON |
| File Role | Tool Schema Definition |
| Ownership | AI Agent Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-16 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-16 |
| Modified By | AI Agent (Claude) |
| WHY (Reason for last change) | Initial creation of get_metadata tool schema |
| Lines of Code (LOC) | 16 |
| Cyclomatic Complexity | N/A (Schema file) |
| Test Coverage | N/A (Validated by jsonschema library) |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
JSON Schema that validates the `get_metadata` tool call arguments for retrieving file size, dates, and permissions.

**Detailed responsibilities:**
- Defines the structure for get_metadata tool arguments
- Validates paths parameter is a non-empty array of strings
- Ensures at least one path is provided (minItems: 1)

### What this file must NOT do (boundaries)
**Out of scope:**
- Does not implement the metadata retrieval functionality
- Does not validate file system paths exist
- Does not check file permissions

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| [`SchemaValidator`](../../agent_host/schema_validator.md) | Validate tool call arguments | On every tool call | Returns validation errors |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
| N/A | Schema file is passive data | N/A | N/A |

---

## Schema Properties

### `paths` (Required)
| Field | Value |
|---|---|
| Type | `array` of `string` |
| Required | Yes |
| Min Items | 1 |
| Description | Array of file paths to get metadata for |
| Validation | Must be array with at least one string element |

---

## Example Valid Tool Calls

### Single Path
```json
{
  "paths": ["/Users/me/Documents/report.pdf"]
}
```

### Multiple Paths
```json
{
  "paths": [
    "/Users/me/Documents/report.pdf",
    "/Users/me/Documents/data.csv",
    "/Users/me/Desktop/notes.txt"
  ]
}
```

---

## Validation Rules

| Rule | Schema Element | Failure Message |
|---|---|---|
| Paths required | `required: ["paths"]` | `'paths' is a required property` |
| Paths must be array | `type: "array"` | `'...' is not of type 'array'` |
| Paths min items | `minItems: 1` | `[] is too short` |
| Each path string | `items: { type: "string" }` | `X is not of type 'string'` |

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| [`schemas/search_files.json`](./search_files.md) | Similar | Both are read-only tool schemas |
| [`schemas/read_text.json`](./read_text.md) | Similar | Both operate on file paths |
| [`agent_host/schema_validator.py`](../../agent_host/schema_validator.md) | Uses | Loads and validates against this schema |

### Related ADRs
| ADR | Decision | Relevance |
|---|---|---|
| N/A | N/A | N/A |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-16 | AI Agent (Claude) | Phase 1 implementation | Created initial schema for get_metadata tool | High - enables tool validation |
