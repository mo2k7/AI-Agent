# File Doc: `agent_host/audit_logger.py`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `agent_host/audit_logger.py` |
| Doc Path | `projects/personal-macos-ai-agent/files/agent_host/audit_logger.md` |
| Language | Python 3.12 |
| File Role | Audit Logging |
| Ownership | Core Infrastructure |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-16 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-16 |
| Modified By | AI Agent (Claude) |
| WHY (Reason for last change) | Initial implementation for Phase 1 |
| Lines of Code (LOC) | ~280 |
| Cyclomatic Complexity | Low |
| Test Coverage | Pending |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:** Provides JSONL audit logging for tracking all agent operations, tool calls, errors, and validation failures.

**Detailed responsibilities:**
- Create and manage the audit log file
- Log events in JSONL (JSON Lines) format
- Support different event types (TOOL_CALL, ERROR, VALIDATION_FAIL)
- Include ISO 8601 timestamps
- Read events back for debugging/analysis
- Support log rotation

### What this file must NOT do (boundaries)
**Out of scope:**
- Should NOT log sensitive data (API keys, passwords)
- Should NOT block on log writes (best effort)
- Should NOT perform analysis on logs
- Should NOT sync logs to external services

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| `main.py` | Log all operations | Per operation | Log error, continue |
| Tests | Verify logging | Per test | Assert on logged events |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
| `json.dump` | Serialize events | TypeError for non-serializable | Custom serializer |
| `pathlib.Path.mkdir` | Create log directory | OSError | Raise AuditLogError |
| `open()` | Write to file | OSError | Raise AuditLogError |

---

## Imports / Dependencies

### Internal Dependencies
| Import Path | What's Used | Why Needed | Coupling Level | Risk/Notes |
|---|---|---|---|---|
| None | - | - | - | No internal deps |

### External Dependencies
| Package | Version | License | What's Used | Why Needed | Security Risk | Alternatives |
|---|---|---|---|---|---|---|
| stdlib `json` | 3.12 | PSF | `dump()`, `load()` | JSONL format | Low | orjson |
| stdlib `datetime` | 3.12 | PSF | `datetime`, `timezone` | Timestamps | Low | None |
| stdlib `pathlib` | 3.12 | PSF | `Path` | File handling | Low | None |
| stdlib `logging` | 3.12 | PSF | Logger | Debug logging | Low | None |
| stdlib `enum` | 3.12 | PSF | `Enum` | Event types | Low | None |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `AuditLogger` | class | public | Stable | Main logger class |
| `AuditLogError` | class | public | Stable | Logging error exception |
| `EventType` | enum | public | Stable | Event type constants |

---

## Types (Classes / Structs / Enums / Interfaces)

### `AuditLogError`
| Metadata | Value |
|---|---|
| Kind | class (Exception) |
| Purpose | Indicate audit logging failure |

#### Inheritance & Implementation
- **Extends:** `Exception`

### `EventType`
| Metadata | Value |
|---|---|
| Kind | enum (str) |
| Purpose | Define valid event types |
| Thread-Safe | Yes (immutable) |
| Serializable | Yes (str values) |

#### Enum Values
| Value | String | Description |
|---|---|---|
| `TOOL_CALL` | "TOOL_CALL" | Successful tool invocation |
| `ERROR` | "ERROR" | Error occurred |
| `VALIDATION_FAIL` | "VALIDATION_FAIL" | Schema validation failed |
| `API_REQUEST` | "API_REQUEST" | API request sent |
| `API_RESPONSE` | "API_RESPONSE" | API response received |
| `STARTUP` | "STARTUP" | Agent started |
| `SHUTDOWN` | "SHUTDOWN" | Agent stopped |

### `AuditLogger`
| Metadata | Value |
|---|---|
| Kind | class |
| Purpose | Append-only JSONL audit logging |
| Thread-Safe | Conditionally (file append is atomic on most systems) |
| Immutable | No |
| Serializable | No |
| Related Types | EventType, AuditLogError |

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose |
|---|---|---|---|---|---|---|
| `log_path` | Path | public | - | Yes | No | Path to JSONL log file |

#### Constructors
| Signature | Parameters | Preconditions | Postconditions | Throws/Errors |
|---|---|---|---|---|
| `__init__(log_path)` | log_path: Path | Valid path | Directory exists | AuditLogError |

#### Methods
| Method | Visibility | Returns | Throws | Side Effects | Thread-Safe | Complexity |
|---|---|---|---|---|---|---|
| `_ensure_directory` | private | None | AuditLogError | Creates dir | Yes | O(1) |
| `log_event` | public | None | AuditLogError | File write | Conditionally | O(n) |
| `log_tool_call` | public | None | AuditLogError | File write | Conditionally | O(n) |
| `log_error` | public | None | AuditLogError | File write | Conditionally | O(n) |
| `log_validation_fail` | public | None | AuditLogError | File write | Conditionally | O(n) |
| `read_events` | public | List[Dict] | None | File read | Yes | O(n) |
| `get_log_size` | public | int | None | File stat | Yes | O(1) |
| `rotate_log` | public | Optional[Path] | None | File rename | No | O(1) |

#### Example Usage
```python
from pathlib import Path
from agent_host.audit_logger import AuditLogger, EventType

# Initialize
logger = AuditLogger(Path("~/.local/share/ai-agent/audit.log"))

# Log a tool call
logger.log_tool_call(
    tool_name="search_files",
    arguments={"query": "python"},
    user_prompt="Find my Python files",
    validated=True
)

# Log an error
logger.log_error(
    error_type="API_ERROR",
    message="Rate limit exceeded",
    details={"status_code": 429}
)

# Log validation failure
logger.log_validation_fail(
    tool_name="search_files",
    arguments={},
    errors=["'query' is a required property"]
)

# Generic event logging
logger.log_event(EventType.STARTUP, {"version": "1.0.0"})

# Read events back
events = logger.read_events(EventType.TOOL_CALL, limit=10)
print(f"Found {len(events)} tool call events")
```

---

## Functions (Document ALL Functions)

### `log_event(event_type, data, timestamp)`

#### Function Metadata
| Field | Value |
|---|---|
| Signature | `(event_type: EventType | str, data: Dict[str, Any], timestamp: Optional[datetime] = None) -> None` |
| Visibility | public |
| Pure Function | No |
| Thread-Safe | Conditionally |
| Idempotent | No (appends new line) |
| Status | Stable |

#### Parameters
| Name | Type | Required | Default | Validation | Example |
|---|---|---|---|---|---|
| `event_type` | EventType \| str | Yes | - | EventType or string | EventType.TOOL_CALL |
| `data` | Dict[str, Any] | Yes | - | JSON-serializable | {"tool": "search"} |
| `timestamp` | Optional[datetime] | No | now(UTC) | datetime object | datetime.now(UTC) |

#### Side Effects
| Side Effect | Scope | Impact |
|---|---|---|
| File Write | Appends to audit.log | Low |

#### JSONL Output Format
```json
{"timestamp": "2026-01-16T00:30:00+00:00", "event": "TOOL_CALL", "data": {"tool": "search_files", "arguments": {"query": "python"}}}
```

### `log_tool_call(tool_name, arguments, user_prompt, validated)`

#### Function Metadata
| Field | Value |
|---|---|
| Signature | `(tool_name: str, arguments: Dict, user_prompt: Optional[str], validated: bool) -> None` |
| Visibility | public |
| Status | Stable |

Convenience method for TOOL_CALL events with standardized data structure.

### `log_error(error_type, message, details)`

#### Function Metadata
| Field | Value |
|---|---|
| Signature | `(error_type: str, message: str, details: Optional[Dict] = None) -> None` |
| Visibility | public |
| Status | Stable |

Convenience method for ERROR events.

### `log_validation_fail(tool_name, arguments, errors)`

#### Function Metadata
| Field | Value |
|---|---|
| Signature | `(tool_name: str, arguments: Dict, errors: List[str]) -> None` |
| Visibility | public |
| Status | Stable |

Convenience method for VALIDATION_FAIL events.

### `read_events(event_type, limit)`

#### Function Metadata
| Field | Value |
|---|---|
| Signature | `(event_type: Optional[EventType | str] = None, limit: Optional[int] = None) -> List[Dict]` |
| Visibility | public |
| Status | Stable |

Read events from log file with optional filtering.

### `rotate_log(max_size_bytes)`

#### Function Metadata
| Field | Value |
|---|---|
| Signature | `(max_size_bytes: int = 10 * 1024 * 1024) -> Optional[Path]` |
| Visibility | public |
| Status | Stable |

Rotate log file if it exceeds maximum size. Default 10MB.

---

## File System Operations

### Audit Log Location
| OS | Default Path |
|---|---|
| macOS | `~/.local/share/ai-agent/audit.log` |
| Linux | `~/.local/share/ai-agent/audit.log` |

### Log Format
- **Format:** JSONL (JSON Lines)
- **Encoding:** UTF-8
- **Line Terminator:** `\n`
- **Rotation:** Manual via `rotate_log()` method

---

## Error Handling Strategy

### Error Categories
| Category | Examples | Default Behavior | User Action |
|---|---|---|---|
| Directory Creation | Permission denied | Raise AuditLogError | Check permissions |
| File Write | Disk full | Raise AuditLogError | Free disk space |
| Serialization | Non-JSON-serializable | Use custom serializer | Fix data structure |

---

## Security Analysis

### Data Sensitivity
| Data Type | Logged | Risk | Mitigation |
|---|---|---|---|
| Tool names | Yes | Low | N/A |
| Tool arguments | Yes | Medium | May contain file paths |
| User prompts | Optional | Medium | Can be disabled |
| API keys | Never | N/A | Never logged |
| Error details | Yes | Low | Sanitize stack traces |

### File Permissions
| Path | Permissions | Purpose |
|---|---|---|
| Log directory | 0755 | Allow read by others |
| Log file | Default (0644) | Standard file |

---

## Testing Documentation

### Unit Test Coverage
| Function/Class | Coverage | Test Location | Edge Cases Covered |
|---|---|---|---|
| `AuditLogger.__init__` | Pending | `tests/unit/test_audit_logger.py` | Missing dir, invalid path |
| `AuditLogger.log_event` | Pending | `tests/unit/test_audit_logger.py` | All event types |
| `AuditLogger.read_events` | Pending | `tests/unit/test_audit_logger.py` | Filtering, limits |
| `AuditLogger.rotate_log` | Pending | `tests/unit/test_audit_logger.py` | Size threshold |

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| [`agent_host/config.py`](config.md) | Provides | audit_log_path setting |
| [`agent_host/tool_parser.py`](tool_parser.md) | Produces | Tool calls to log |
| [`agent_host/schema_validator.py`](schema_validator.md) | Produces | Validation failures to log |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-16 | AI Agent (Claude) | Phase 1 implementation | Initial creation with JSONL logging and event types | Medium - tracks all operations |
