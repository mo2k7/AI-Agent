# File Doc: `schemas/read_text.json`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `schemas/read_text.json` |
| Doc Path | `projects/personal-macos-ai-agent/files/schemas/read_text.md` |
| Language | JSON |
| File Role | Tool Schema Definition |
| Ownership | AI Agent Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-16 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-16 |
| Modified By | AI Agent (Claude) |
| WHY (Reason for last change) | Initial creation of read_text tool schema |
| Lines of Code (LOC) | 20 |
| Cyclomatic Complexity | N/A (Schema file) |
| Test Coverage | N/A (Validated by jsonschema library) |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
JSON Schema that validates the `read_text` tool call arguments for reading plain text content from a file.

**Detailed responsibilities:**
- Defines the structure for read_text tool arguments
- Validates path parameter is present and is a string
- Supports optional byte_range for partial file reads (array of exactly 2 integers)

### What this file must NOT do (boundaries)
**Out of scope:**
- Does not implement the file reading functionality
- Does not validate file system paths exist
- Does not check file permissions or encoding

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

### `path` (Required)
| Field | Value |
|---|---|
| Type | `string` |
| Required | Yes |
| Description | Path to the file to read |
| Validation | Must be string type |

### `byte_range` (Optional)
| Field | Value |
|---|---|
| Type | `array` of 2 `integer` |
| Required | No |
| Min Items | 2 |
| Max Items | 2 |
| Description | Optional [start, end] byte range for partial reads |
| Validation | Must be array of exactly 2 integers if provided |

---

## Example Valid Tool Calls

### Full File Read
```json
{
  "path": "/Users/me/Documents/notes.txt"
}
```

### Partial Read (Byte Range)
```json
{
  "path": "/Users/me/Documents/large_log.txt",
  "byte_range": [0, 1024]
}
```

### Read Middle Section
```json
{
  "path": "/Users/me/data.csv",
  "byte_range": [5000, 10000]
}
```

---

## Validation Rules

| Rule | Schema Element | Failure Message |
|---|---|---|
| Path required | `required: ["path"]` | `'path' is a required property` |
| Path must be string | `type: "string"` | `'...' is not of type 'string'` |
| Byte range must be array | `type: "array"` | `'...' is not of type 'array'` |
| Byte range exact length | `minItems: 2, maxItems: 2` | `[...] is too short/long` |
| Byte range elements integer | `items: { type: "integer" }` | `X is not of type 'integer'` |

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| [`schemas/extract_content.json`](./extract_content.md) | Similar | Both read file content |
| [`schemas/get_metadata.json`](./get_metadata.md) | Similar | Both operate on file paths |
| [`agent_host/schema_validator.py`](../../agent_host/schema_validator.md) | Uses | Loads and validates against this schema |

### Related ADRs
| ADR | Decision | Relevance |
|---|---|---|
| N/A | N/A | N/A |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-16 | AI Agent (Claude) | Phase 1 implementation | Created initial schema for read_text tool | High - enables tool validation |
