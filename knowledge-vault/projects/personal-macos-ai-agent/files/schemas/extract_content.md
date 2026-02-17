# File Doc: `schemas/extract_content.json`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `schemas/extract_content.json` |
| Doc Path | `projects/personal-macos-ai-agent/files/schemas/extract_content.md` |
| Language | JSON |
| File Role | Tool Schema Definition |
| Ownership | AI Agent Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-16 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-16 |
| Modified By | AI Agent (Claude) |
| WHY (Reason for last change) | Initial creation of extract_content tool schema |
| Lines of Code (LOC) | 19 |
| Cyclomatic Complexity | N/A (Schema file) |
| Test Coverage | N/A (Validated by jsonschema library) |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
JSON Schema that validates the `extract_content` tool call arguments for extracting text from rich formats like PDF, code files, etc.

**Detailed responsibilities:**
- Defines the structure for extract_content tool arguments
- Validates path parameter is present and is a string
- Validates mode parameter is present and is one of: "text", "pdf", "code"
- Enables format-specific content extraction

### What this file must NOT do (boundaries)
**Out of scope:**
- Does not implement the content extraction functionality
- Does not validate file system paths exist
- Does not check file format compatibility

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
| Description | Path to the file |
| Validation | Must be string type |

### `mode` (Required)
| Field | Value |
|---|---|
| Type | `string` |
| Required | Yes |
| Enum Values | `"text"`, `"pdf"`, `"code"` |
| Description | Extraction mode |
| Validation | Must be one of the enum values |

---

## Extraction Modes

| Mode | Use Case | Typical File Types |
|---|---|---|
| `text` | Plain text extraction | .txt, .md, .log |
| `pdf` | PDF document parsing | .pdf |
| `code` | Source code with syntax | .py, .js, .swift, etc. |

---

## Example Valid Tool Calls

### Text Mode
```json
{
  "path": "/Users/me/Documents/notes.txt",
  "mode": "text"
}
```

### PDF Mode
```json
{
  "path": "/Users/me/Documents/report.pdf",
  "mode": "pdf"
}
```

### Code Mode
```json
{
  "path": "/Users/me/Projects/app.py",
  "mode": "code"
}
```

---

## Validation Rules

| Rule | Schema Element | Failure Message |
|---|---|---|
| Path required | `required: ["path", "mode"]` | `'path' is a required property` |
| Mode required | `required: ["path", "mode"]` | `'mode' is a required property` |
| Path must be string | `type: "string"` | `'...' is not of type 'string'` |
| Mode must be enum | `enum: ["text", "pdf", "code"]` | `'...' is not one of ['text', 'pdf', 'code']` |

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| [`schemas/read_text.json`](./read_text.md) | Similar | Both read file content |
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
| 2026-01-16 | AI Agent (Claude) | Phase 1 implementation | Created initial schema for extract_content tool | High - enables tool validation |
