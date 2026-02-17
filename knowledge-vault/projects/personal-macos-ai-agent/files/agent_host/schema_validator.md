# File Doc: `agent_host/schema_validator.py`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `agent_host/schema_validator.py` |
| Doc Path | `projects/personal-macos-ai-agent/files/agent_host/schema_validator.md` |
| Language | Python 3.14 |
| File Role | Validation |
| Ownership | Core Infrastructure |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Updated runtime and jsonschema version references |
| Lines of Code (LOC) | ~260 |
| Cyclomatic Complexity | Medium |
| Test Coverage | Pending |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:** Loads JSON Schema files and validates tool call arguments against them.

**Detailed responsibilities:**
- Load JSON Schema files from a directory
- Validate tool call arguments against loaded schemas
- Report detailed validation errors
- Format schemas for Gemini's function calling configuration
- Cache compiled validators for performance

### What this file must NOT do (boundaries)
**Out of scope:**
- Should NOT modify schemas at runtime
- Should NOT execute tool calls
- Should NOT communicate with external APIs
- Should NOT handle tool execution logic

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| `main.py` | Validate parsed tool calls | Per tool call | Display validation errors |
| `GeminiClient` | Get tools for API | On startup | Schema not found error |
| Tests | Test validation | Per test | Assert on validation results |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
| `jsonschema.Draft7Validator` | Validate against schema | Returns errors list | N/A |
| `json.load` | Parse JSON files | JSONDecodeError | Raise SchemaLoadError |
| `pathlib.Path.glob` | Find schema files | N/A | Empty list |

---

## Imports / Dependencies

### Internal Dependencies
| Import Path | What's Used | Why Needed | Coupling Level | Risk/Notes |
|---|---|---|---|---|
| None | - | - | - | - |

### External Dependencies
| Package | Version | License | What's Used | Why Needed | Security Risk | Alternatives |
|---|---|---|---|---|---|---|
| `jsonschema` | ^4.26.0 | MIT | Draft7Validator | Schema validation | Low | fastjsonschema |
| stdlib `json` | 3.14 | PSF | `load()` | Parse JSON files | Low | orjson |
| stdlib `pathlib` | 3.14 | PSF | `Path` | File path handling | Low | None |
| stdlib `logging` | 3.14 | PSF | Logger | Debug logging | Low | None |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `SchemaValidator` | class | public | Stable | Main validator class |
| `SchemaValidatorError` | class | public | Stable | Base exception |
| `SchemaLoadError` | class | public | Stable | Schema loading failed |
| `SchemaNotFoundError` | class | public | Stable | Schema doesn't exist |
| `ValidationFailedError` | class | public | Stable | Validation failed |

---

## Types (Classes / Structs / Enums / Interfaces)

### `SchemaValidatorError`
| Metadata | Value |
|---|---|
| Kind | class (Exception) |
| Purpose | Base exception for validator errors |

#### Inheritance & Implementation
- **Extends:** `Exception`

### `SchemaLoadError`
| Metadata | Value |
|---|---|
| Kind | class (Exception) |
| Purpose | Schema file cannot be loaded |

### `SchemaNotFoundError`
| Metadata | Value |
|---|---|
| Kind | class (Exception) |
| Purpose | Requested schema does not exist |

### `ValidationFailedError`
| Metadata | Value |
|---|---|
| Kind | class (Exception) |
| Purpose | Validation against schema failed |

#### Fields / Properties
| Name | Type | Visibility | Purpose |
|---|---|---|---|
| `errors` | List[str] | public | List of validation error messages |

### `SchemaValidator`
| Metadata | Value |
|---|---|
| Kind | class |
| Purpose | Load and validate against JSON Schemas |
| Thread-Safe | Yes (read-only after init) |
| Immutable | Effectively (schemas loaded once) |
| Serializable | No |
| Related Types | All error classes |

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose |
|---|---|---|---|---|---|---|
| `schemas_dir` | Path | public | - | Yes | No | Directory with schemas |
| `schemas` | Dict[str, Dict] | public | {} | No | Yes | Loaded schemas by name |
| `_validators` | Dict[str, Draft7Validator] | private | {} | No | Yes | Compiled validators |

#### Constructors
| Signature | Parameters | Preconditions | Postconditions | Throws/Errors |
|---|---|---|---|---|
| `__init__(schemas_dir)` | schemas_dir: Path | Directory exists | Schemas loaded | SchemaLoadError |

#### Methods
| Method | Visibility | Returns | Throws | Side Effects | Thread-Safe | Complexity |
|---|---|---|---|---|---|---|
| `_load_schemas` | private | None | SchemaLoadError | File I/O | Yes | O(n) |
| `_load_schema_file` | private | None | SchemaLoadError | File I/O | Yes | O(1) |
| `validate_tool_call` | public | bool | SchemaNotFoundError, ValidationFailedError | None | Yes | O(n) |
| `validate_tool_call_safe` | public | Tuple[bool, List[str]] | None | None | Yes | O(n) |
| `get_schema` | public | Dict | SchemaNotFoundError | None | Yes | O(1) |
| `get_all_tool_names` | public | List[str] | None | None | Yes | O(1) |
| `get_all_tools_for_gemini` | public | List[Dict] | None | None | Yes | O(n) |
| `reload_schemas` | public | None | SchemaLoadError | File I/O | Yes | O(n) |

#### Example Usage
```python
from pathlib import Path
from agent_host.schema_validator import SchemaValidator, ValidationFailedError

# Initialize validator
validator = SchemaValidator(Path("schemas"))

# Validate a tool call
try:
    validator.validate_tool_call("search_files", {"query": "python"})
    print("Valid!")
except ValidationFailedError as e:
    print(f"Invalid: {e.errors}")

# Safe validation (no exceptions)
is_valid, errors = validator.validate_tool_call_safe("search_files", {})
if not is_valid:
    print(f"Validation errors: {errors}")

# Get tools for Gemini
tools = validator.get_all_tools_for_gemini()
print(f"Loaded {len(tools)} tools")
```

---

## Functions (Document ALL Functions)

### `validate_tool_call(tool_name, arguments)`

#### Function Metadata
| Field | Value |
|---|---|
| Signature | `(tool_name: str, arguments: Dict[str, Any]) -> bool` |
| Visibility | public |
| Pure Function | Yes |
| Thread-Safe | Yes |
| Idempotent | Yes |
| Status | Stable |

#### Parameters
| Name | Type | Required | Default | Validation | Example |
|---|---|---|---|---|---|
| `tool_name` | str | Yes | - | Must exist in schemas | "search_files" |
| `arguments` | Dict[str, Any] | Yes | - | Against JSON Schema | {"query": "python"} |

#### Returns
| Type | Meaning | Possible Values |
|---|---|---|
| bool | Validation passed | True (if valid) |

#### Errors / Exceptions
| Error Type | Condition | Recovery Strategy |
|---|---|---|
| `SchemaNotFoundError` | Tool name not in schemas | Check tool name |
| `ValidationFailedError` | Arguments don't match schema | Fix arguments |

### `validate_tool_call_safe(tool_name, arguments)`

#### Function Metadata
| Field | Value |
|---|---|
| Signature | `(tool_name: str, arguments: Dict[str, Any]) -> Tuple[bool, Optional[List[str]]]` |
| Visibility | public |
| Pure Function | Yes |
| Thread-Safe | Yes |
| Status | Stable |

#### Returns
| Type | Meaning |
|---|---|
| Tuple[bool, Optional[List[str]]] | (is_valid, error_messages or None) |

Non-throwing alternative for validation.

### `get_all_tools_for_gemini()`

#### Function Metadata
| Field | Value |
|---|---|
| Signature | `() -> List[Dict[str, Any]]` |
| Visibility | public |
| Pure Function | Yes |
| Thread-Safe | Yes |
| Status | Stable |

#### Returns
| Type | Meaning |
|---|---|
| List[Dict] | Tools formatted for Gemini function calling |

Returns schemas formatted for `GeminiClient.send_prompt_with_tools()`.

---

## Error Handling Strategy

### Error Categories
| Category | Examples | Default Behavior | User Action |
|---|---|---|---|
| Schema Load Error | Invalid JSON, missing dir | Raise on init | Fix schema files |
| Schema Not Found | Unknown tool name | Raise | Check tool name |
| Validation Failed | Missing required field | Raise with errors | Fix arguments |

---

## Performance Profile

### Performance Characteristics
| Metric | Value | Notes |
|---|---|---|
| Schema Load Time | < 100ms | One-time at startup |
| Validation Time | < 1ms | Per validation |
| Memory Usage | Low | Schemas cached |

### Caching Strategy
| What's Cached | Invalidation | Storage |
|---|---|---|
| Parsed schemas | Manual reload | In-memory dict |
| Compiled validators | Manual reload | In-memory dict |

---

## Testing Documentation

### Unit Test Coverage
| Function/Class | Coverage | Test Location | Edge Cases Covered |
|---|---|---|---|
| `validate_tool_call` | Pending | `tests/unit/test_schema_validator.py` | Valid, missing required, extra fields |
| `get_all_tools_for_gemini` | Pending | `tests/unit/test_schema_validator.py` | Empty schemas, multiple tools |

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| [`agent_host/config.py`](config.md) | Provides | schemas_dir path |
| [`agent_host/gemini_client.py`](gemini_client.md) | Uses | Gets tools list |
| [`agent_host/tool_parser.py`](tool_parser.md) | Used with | Validates parsed calls |
| `schemas/*.json` | Data source | Schema definitions |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Agent (Codex) | Dependency refresh | Updated Python and jsonschema version references | Low |
| 2026-01-16 | AI Agent (Claude) | Phase 1 implementation | Initial creation with JSON Schema validation | High - validates all tool calls |
