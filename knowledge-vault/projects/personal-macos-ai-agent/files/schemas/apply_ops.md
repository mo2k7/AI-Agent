# File Doc: `schemas/apply_ops.json`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `schemas/apply_ops.json` |
| Doc Path | `projects/personal-macos-ai-agent/files/schemas/apply_ops.md` |
| Language | JSON |
| File Role | Tool Schema Definition |
| Ownership | AI Agent Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-16 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-16 |
| Modified By | AI Agent (Claude) |
| WHY (Reason for last change) | Initial creation of apply_ops tool schema |
| Lines of Code (LOC) | 14 |
| Cyclomatic Complexity | N/A (Schema file) |
| Test Coverage | N/A (Validated by jsonschema library) |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
JSON Schema that validates the `apply_ops` tool call arguments for executing a previously planned set of file operations.

**Detailed responsibilities:**
- Defines the structure for apply_ops tool arguments
- Validates plan_id parameter is present and is a string
- Enables execution of plans created by plan_ops tool

### What this file must NOT do (boundaries)
**Out of scope:**
- Does not implement the operation execution functionality
- Does not validate plan_id exists or is valid
- Does not define the operations themselves (that's plan_ops)

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

### `plan_id` (Required)
| Field | Value |
|---|---|
| Type | `string` |
| Required | Yes |
| Description | ID of the plan to execute |
| Validation | Must be string type |

---

## Workflow

The `apply_ops` tool is the second step in a two-step file operation workflow:

```
1. User requests file operations
2. Agent calls plan_ops → returns plan_id
3. User confirms plan
4. Agent calls apply_ops with plan_id
5. Operations are executed
```

---

## Example Valid Tool Calls

### Standard Usage
```json
{
  "plan_id": "plan_abc123"
}
```

### UUID-Style Plan ID
```json
{
  "plan_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

## Validation Rules

| Rule | Schema Element | Failure Message |
|---|---|---|
| Plan ID required | `required: ["plan_id"]` | `'plan_id' is a required property` |
| Plan ID must be string | `type: "string"` | `'...' is not of type 'string'` |

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| [`schemas/plan_ops.json`](./plan_ops.md) | Companion | plan_ops creates plans that apply_ops executes |
| [`agent_host/schema_validator.py`](../../agent_host/schema_validator.md) | Uses | Loads and validates against this schema |

### Related ADRs
| ADR | Decision | Relevance |
|---|---|---|
| N/A | N/A | N/A |

---

## Security Considerations

| Concern | Details | Mitigation |
|---|---|---|
| Plan Replay | Reusing plan_id could re-execute operations | Implementation should invalidate used plans |
| Plan Tampering | Modified plans shouldn't be executable | Implementation should verify plan integrity |
| Plan Expiry | Old plans shouldn't be executable indefinitely | Implementation should expire plans after timeout |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-16 | AI Agent (Claude) | Phase 1 implementation | Created initial schema for apply_ops tool | High - enables tool validation |
