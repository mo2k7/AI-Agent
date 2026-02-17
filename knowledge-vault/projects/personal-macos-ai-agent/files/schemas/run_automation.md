# File Doc: `schemas/run_automation.json`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `schemas/run_automation.json` |
| Doc Path | `projects/personal-macos-ai-agent/files/schemas/run_automation.md` |
| Language | JSON |
| File Role | Tool Schema Definition |
| Ownership | AI Agent Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-16 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-16 |
| Modified By | AI Agent (Claude) |
| WHY (Reason for last change) | Initial creation of run_automation tool schema |
| Lines of Code (LOC) | 18 |
| Cyclomatic Complexity | N/A (Schema file) |
| Test Coverage | N/A (Validated by jsonschema library) |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
JSON Schema that validates the `run_automation` tool call arguments for executing predefined, allowlisted AppleScript or Shell scripts.

**Detailed responsibilities:**
- Defines the structure for run_automation tool arguments
- Validates name parameter is present and is a string
- Supports optional inputs object for script parameters
- Uses additionalProperties: true to allow flexible input schemas

### What this file must NOT do (boundaries)
**Out of scope:**
- Does not implement the script execution functionality
- Does not define the allowlist of scripts
- Does not validate script names against allowlist (implementation responsibility)

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

### `name` (Required)
| Field | Value |
|---|---|
| Type | `string` |
| Required | Yes |
| Description | Name of the predefined automation |
| Validation | Must be string type |

### `inputs` (Optional)
| Field | Value |
|---|---|
| Type | `object` |
| Required | No |
| Additional Properties | true (allows any key-value pairs) |
| Description | Input parameters for the automation |
| Validation | Must be object type if provided |

---

## Allowlist Concept

The `run_automation` tool only executes **predefined, allowlisted** scripts:

| Aspect | Policy |
|---|---|
| Script Source | Predefined in agent configuration |
| Dynamic Scripts | Not allowed |
| User Scripts | Must be added to allowlist first |
| Validation | Implementation checks name against allowlist |

---

## Example Valid Tool Calls

### No Inputs
```json
{
  "name": "toggle_dark_mode"
}
```

### With String Input
```json
{
  "name": "send_notification",
  "inputs": {
    "title": "Reminder",
    "message": "Meeting in 10 minutes"
  }
}
```

### With Mixed Inputs
```json
{
  "name": "backup_folder",
  "inputs": {
    "source": "/Users/me/Documents",
    "compress": true,
    "max_size_mb": 500
  }
}
```

### Complex Inputs
```json
{
  "name": "batch_rename_files",
  "inputs": {
    "directory": "/Users/me/Photos",
    "pattern": "IMG_{date}_{index}",
    "extensions": ["jpg", "png"],
    "dry_run": false
  }
}
```

---

## Validation Rules

| Rule | Schema Element | Failure Message |
|---|---|---|
| Name required | `required: ["name"]` | `'name' is a required property` |
| Name must be string | `type: "string"` | `'...' is not of type 'string'` |
| Inputs must be object | `type: "object"` | `'...' is not of type 'object'` |

---

## Potential Automation Examples

| Name | Description | Inputs |
|---|---|---|
| `toggle_dark_mode` | Switch macOS appearance | None |
| `empty_trash` | Empty Finder trash | None |
| `send_notification` | Show macOS notification | title, message |
| `create_reminder` | Add Reminders item | title, due_date, list |
| `screenshot_to_clipboard` | Capture screenshot | None |
| `set_do_not_disturb` | Toggle Focus mode | enabled |

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| [`schemas/open_item.json`](./open_item.md) | Similar | Both trigger macOS actions |
| [`agent_host/schema_validator.py`](../../agent_host/schema_validator.md) | Uses | Loads and validates against this schema |

### Related ADRs
| ADR | Decision | Relevance |
|---|---|---|
| N/A | N/A | N/A |

---

## Security Considerations

| Concern | Details | Mitigation |
|---|---|---|
| Code Execution | Scripts execute arbitrary code | Only allowlisted scripts permitted |
| Input Injection | Malicious inputs could compromise scripts | Scripts must sanitize inputs |
| Permission Escalation | Scripts run with user permissions | Audit allowlisted scripts |
| Data Exfiltration | Scripts could send data externally | Network monitoring for scripts |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-16 | AI Agent (Claude) | Phase 1 implementation | Created initial schema for run_automation tool | High - enables tool validation |
