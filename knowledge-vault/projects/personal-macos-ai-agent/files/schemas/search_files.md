# File Doc: `schemas/search_files.json`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `schemas/search_files.json` |
| Doc Path | `projects/personal-macos-ai-agent/files/schemas/search_files.md` |
| Language | JSON |
| File Role | Tool Schema Definition |
| Ownership | AI Agent Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-16 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-16 |
| Modified By | AI Agent (Claude) |
| WHY (Reason for last change) | Initial creation of search_files tool schema |
| Lines of Code (LOC) | 24 |
| Cyclomatic Complexity | N/A (Schema file) |
| Test Coverage | N/A (Validated by jsonschema library) |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
JSON Schema that validates the `search_files` tool call arguments when Gemini returns a function call.

**Detailed responsibilities:**
- Defines the structure for search_files tool arguments
- Validates query parameter is present and is a string
- Enforces limit constraints (1-100, default 10)
- Allows optional path_filter for scoping searches

### What this file must NOT do (boundaries)
**Out of scope:**
- Does not implement the search functionality itself
- Does not validate file system paths exist

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

### `query` (Required)
| Field | Value |
|---|---|
| Type | `string` |
| Required | Yes |
| Description | Search query string |
| Validation | Must be string type |

### `path_filter` (Optional)
| Field | Value |
|---|---|
| Type | `string` |
| Required | No |
| Description | Optional path filter pattern |
| Validation | Must be string type if provided |

### `limit` (Optional)
| Field | Value |
|---|---|
| Type | `integer` |
| Required | No |
| Default | 10 |
| Minimum | 1 |
| Maximum | 100 |
| Description | Maximum number of results |

---

## Example Valid Tool Calls

### Minimal
```json
{
  "query": "Python files"
}
```

### With Path Filter
```json
{
  "query": "*.pdf",
  "path_filter": "~/Documents"
}
```

### Full Parameters
```json
{
  "query": "invoice 2024",
  "path_filter": "~/Documents/Finance",
  "limit": 25
}
```

---

## Validation Rules

| Rule | Schema Element | Failure Message |
|---|---|---|
| Query required | `required: ["query"]` | `'query' is a required property` |
| Query must be string | `type: "string"` | `'...' is not of type 'string'` |
| Limit min value | `minimum: 1` | `X is less than the minimum of 1` |
| Limit max value | `maximum: 100` | `X is greater than the maximum of 100` |
| Limit must be integer | `type: "integer"` | `'...' is not of type 'integer'` |

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| [`schemas/get_metadata.json`](./get_metadata.md) | Similar | Both are read-only tool schemas |
| [`agent_host/schema_validator.py`](../../agent_host/schema_validator.md) | Uses | Loads and validates against this schema |

### Related ADRs
| ADR | Decision | Relevance |
|---|---|---|
| N/A | N/A | N/A |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-16 | AI Agent (Claude) | Phase 1 implementation | Created initial schema for search_files tool | High - enables tool validation |
