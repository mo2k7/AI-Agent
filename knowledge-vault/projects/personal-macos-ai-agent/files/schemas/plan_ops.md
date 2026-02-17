# File Doc: `schemas/plan_ops.json`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `schemas/plan_ops.json` |
| Doc Path | `projects/personal-macos-ai-agent/files/schemas/plan_ops.md` |
| Language | JSON |
| File Role | Tool Schema Definition |
| Ownership | AI Agent Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-16 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-16 |
| Modified By | AI Agent (Claude) |
| WHY (Reason for last change) | Initial creation of plan_ops tool schema |
| Lines of Code (LOC) | 31 |
| Cyclomatic Complexity | N/A (Schema file) |
| Test Coverage | N/A (Validated by jsonschema library) |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
JSON Schema that validates the `plan_ops` tool call arguments for proposing file modifications (move, delete, rename).

**Detailed responsibilities:**
- Defines the structure for plan_ops tool arguments
- Validates ops array contains at least one operation
- Validates each operation has `op` and `src` fields
- Uses conditional schema: `dest` required for move/rename, not required for delete
- Enforces operation types via enum constraint

### What this file must NOT do (boundaries)
**Out of scope:**
- Does not implement the file operation functionality
- Does not validate file system paths exist
- Does not execute any operations (planning only)

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

### `ops` (Required)
| Field | Value |
|---|---|
| Type | `array` of operation objects |
| Required | Yes |
| Min Items | 1 |
| Description | Array of planned operations |

### Operation Object Properties

#### `op` (Required)
| Field | Value |
|---|---|
| Type | `string` |
| Required | Yes |
| Enum Values | `"move"`, `"delete"`, `"rename"` |
| Description | The type of operation to perform |

#### `src` (Required)
| Field | Value |
|---|---|
| Type | `string` |
| Required | Yes |
| Description | Source path for the operation |

#### `dest` (Conditionally Required)
| Field | Value |
|---|---|
| Type | `string` |
| Required | Yes for `move` and `rename`; No for `delete` |
| Description | Destination path (not needed for delete) |

---

## Conditional Schema Logic

The schema uses JSON Schema `if/then/else` to conditionally require `dest`:

```
if op == "delete" → dest not required
else → dest required
```

---

## Example Valid Tool Calls

### Move Operation
```json
{
  "ops": [
    {
      "op": "move",
      "src": "/Users/me/Downloads/file.pdf",
      "dest": "/Users/me/Documents/file.pdf"
    }
  ]
}
```

### Delete Operation
```json
{
  "ops": [
    {
      "op": "delete",
      "src": "/Users/me/Downloads/temp.txt"
    }
  ]
}
```

### Rename Operation
```json
{
  "ops": [
    {
      "op": "rename",
      "src": "/Users/me/Documents/old_name.pdf",
      "dest": "/Users/me/Documents/new_name.pdf"
    }
  ]
}
```

### Multiple Operations
```json
{
  "ops": [
    {
      "op": "move",
      "src": "/Users/me/Downloads/report.pdf",
      "dest": "/Users/me/Documents/2024/report.pdf"
    },
    {
      "op": "delete",
      "src": "/Users/me/Downloads/temp.log"
    },
    {
      "op": "rename",
      "src": "/Users/me/Documents/draft.txt",
      "dest": "/Users/me/Documents/final.txt"
    }
  ]
}
```

---

## Validation Rules

| Rule | Schema Element | Failure Message |
|---|---|---|
| Ops required | `required: ["ops"]` | `'ops' is a required property` |
| Ops must be array | `type: "array"` | `'...' is not of type 'array'` |
| Ops min items | `minItems: 1` | `[] is too short` |
| Op required | `required: ["op", "src"]` | `'op' is a required property` |
| Src required | `required: ["op", "src"]` | `'src' is a required property` |
| Op must be enum | `enum: ["move", "delete", "rename"]` | `'...' is not one of ['move', 'delete', 'rename']` |
| Dest required (non-delete) | `if/then/else` conditional | `'dest' is a required property` |

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| [`schemas/apply_ops.json`](./apply_ops.md) | Companion | apply_ops executes planned ops |
| [`agent_host/schema_validator.py`](../../agent_host/schema_validator.md) | Uses | Loads and validates against this schema |

### Related ADRs
| ADR | Decision | Relevance |
|---|---|---|
| N/A | N/A | N/A |

---

## Security Considerations

| Concern | Details | Mitigation |
|---|---|---|
| Path Traversal | Operations could target sensitive paths | Implementation should validate paths |
| Mass Delete | Large ops array could delete many files | UI should confirm destructive operations |
| Plan Expiry | Old plans shouldn't be executable indefinitely | Implementation should expire plans |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-16 | AI Agent (Claude) | Phase 1 implementation | Created initial schema for plan_ops tool | High - enables tool validation |
