# File Doc: `schemas/open_item.json`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `schemas/open_item.json` |
| Doc Path | `projects/personal-macos-ai-agent/files/schemas/open_item.md` |
| Language | JSON |
| File Role | Tool Schema Definition |
| Ownership | AI Agent Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-16 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-16 |
| Modified By | AI Agent (Claude) |
| WHY (Reason for last change) | Initial creation of open_item tool schema |
| Lines of Code (LOC) | 14 |
| Cyclomatic Complexity | N/A (Schema file) |
| Test Coverage | N/A (Validated by jsonschema library) |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
JSON Schema that validates the `open_item` tool call arguments for opening a file in its default application or revealing it in Finder.

**Detailed responsibilities:**
- Defines the structure for open_item tool arguments
- Validates path parameter is present and is a string
- Enables opening any file type with macOS default handler

### What this file must NOT do (boundaries)
**Out of scope:**
- Does not implement the file opening functionality
- Does not validate file system paths exist
- Does not specify which application opens the file

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
| Description | Path to the item to open |
| Validation | Must be string type |

---

## macOS Integration

The implementation will use macOS `open` command or equivalent:

| Item Type | Behavior |
|---|---|
| File | Opens in default application |
| Directory | Opens in Finder |
| URL | Opens in default browser |
| Application | Launches the application |

---

## Example Valid Tool Calls

### Open File
```json
{
  "path": "/Users/me/Documents/report.pdf"
}
```

### Open Directory
```json
{
  "path": "/Users/me/Documents"
}
```

### Open Application
```json
{
  "path": "/Applications/Safari.app"
}
```

---

## Validation Rules

| Rule | Schema Element | Failure Message |
|---|---|---|
| Path required | `required: ["path"]` | `'path' is a required property` |
| Path must be string | `type: "string"` | `'...' is not of type 'string'` |

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| [`schemas/read_text.json`](./read_text.md) | Similar | Both operate on file paths |
| [`schemas/get_metadata.json`](./get_metadata.md) | Similar | Both operate on file paths |
| [`agent_host/schema_validator.py`](../../agent_host/schema_validator.md) | Uses | Loads and validates against this schema |

### Related ADRs
| ADR | Decision | Relevance |
|---|---|---|
| N/A | N/A | N/A |

---

## Security Considerations

| Concern | Details | Mitigation |
|---|---|---|
| Arbitrary Execution | Opening executables could run malicious code | Implementation should warn on executables |
| Path Traversal | Paths outside allowed scope | Implementation should validate paths |
| Privacy | Opening files reveals private content | User must explicitly request open |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-16 | AI Agent (Claude) | Phase 1 implementation | Created initial schema for open_item tool | High - enables tool validation |
