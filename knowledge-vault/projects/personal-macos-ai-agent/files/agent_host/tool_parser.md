# File Doc: `agent_host/tool_parser.py`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `agent_host/tool_parser.py` |
| Doc Path | `projects/personal-macos-ai-agent/files/agent_host/tool_parser.md` |
| Language | Python 3.12 |
| File Role | Response Parsing |
| Ownership | Core Infrastructure |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-16 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-16 |
| Modified By | AI Agent (Claude) |
| WHY (Reason for last change) | Initial implementation for Phase 1 |
| Lines of Code (LOC) | ~220 |
| Cyclomatic Complexity | Low |
| Test Coverage | Pending |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:** Parses Gemini API responses to extract function/tool calls into structured ToolCall objects.

**Detailed responsibilities:**
- Parse dictionary responses from GeminiClient
- Parse raw Gemini SDK response objects
- Extract function call name and arguments
- Handle missing or malformed function calls gracefully
- Provide type-safe ToolCall dataclass

### What this file must NOT do (boundaries)
**Out of scope:**
- Should NOT validate argument values (schema_validator does that)
- Should NOT execute tool calls
- Should NOT communicate with APIs
- Should NOT modify responses

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| `main.py` | Parse Gemini response | Per API response | Handle None or error |
| Tests | Test parsing logic | Per test | Assert on results |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
| stdlib only | N/A | N/A | N/A |

---

## Imports / Dependencies

### Internal Dependencies
| Import Path | What's Used | Why Needed | Coupling Level | Risk/Notes |
|---|---|---|---|---|
| None | - | - | - | No internal deps |

### External Dependencies
| Package | Version | License | What's Used | Why Needed | Security Risk | Alternatives |
|---|---|---|---|---|---|---|
| stdlib `dataclasses` | 3.12 | PSF | `@dataclass`, `field` | ToolCall structure | Low | attrs |
| stdlib `logging` | 3.12 | PSF | Logger | Debug logging | Low | None |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `ToolCall` | dataclass | public | Stable | Parsed tool call data |
| `ToolCallParser` | class | public | Stable | Parser for Gemini responses |
| `ToolParserError` | class | public | Stable | Base exception |
| `MalformedResponseError` | class | public | Stable | Response structure invalid |

---

## Types (Classes / Structs / Enums / Interfaces)

### `ToolParserError`
| Metadata | Value |
|---|---|
| Kind | class (Exception) |
| Purpose | Base exception for parser errors |

#### Inheritance & Implementation
- **Extends:** `Exception`

### `MalformedResponseError`
| Metadata | Value |
|---|---|
| Kind | class (Exception) |
| Purpose | Response structure is invalid |

#### Inheritance & Implementation
- **Extends:** `ToolParserError`

### `ToolCall`
| Metadata | Value |
|---|---|
| Kind | dataclass |
| Purpose | Represent a parsed function call |
| Thread-Safe | Yes (immutable after init) |
| Immutable | Yes |
| Serializable | Yes (via to_dict) |
| Related Types | None |

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation |
|---|---|---|---|---|---|---|---|
| `name` | str | public | - | Yes | No | Tool/function name | Non-empty |
| `arguments` | Dict[str, Any] | public | {} | No | No | Function arguments | Must be dict |
| `raw_response` | Dict[str, Any] | public | {} | No | No | Original response | Must be dict |

#### Constructors
| Signature | Parameters | Preconditions | Postconditions | Throws/Errors |
|---|---|---|---|---|
| `__init__(name, arguments, raw_response)` | All fields | Valid values | Validated | ValueError |

#### Methods
| Method | Visibility | Returns | Throws | Side Effects | Thread-Safe | Complexity |
|---|---|---|---|---|---|---|
| `__post_init__` | private | None | ValueError | None | Yes | O(1) |
| `to_dict` | public | Dict[str, Any] | None | None | Yes | O(1) |
| `__str__` | public | str | None | None | Yes | O(n) |

#### Example Usage
```python
from agent_host.tool_parser import ToolCall

# Create directly
tool_call = ToolCall(
    name="search_files",
    arguments={"query": "python", "limit": 10},
    raw_response={"function_call": {...}}
)

# Use methods
print(tool_call)  # "search_files(query='python', limit=10)"
print(tool_call.to_dict())  # {"name": "search_files", "arguments": {...}}
```

### `ToolCallParser`
| Metadata | Value |
|---|---|
| Kind | class |
| Purpose | Parse Gemini responses to extract tool calls |
| Thread-Safe | Yes (stateless) |
| Immutable | Yes (no state) |
| Serializable | N/A |
| Related Types | ToolCall, MalformedResponseError |

#### Methods
| Method | Visibility | Returns | Throws | Side Effects | Thread-Safe | Complexity |
|---|---|---|---|---|---|---|
| `parse_response` | public | Optional[ToolCall] | MalformedResponseError | None | Yes | O(n) |
| `parse_response_safe` | public | Tuple[Optional[ToolCall], Optional[str]] | None | None | Yes | O(n) |
| `_parse_dict_response` | private | Optional[ToolCall] | MalformedResponseError | None | Yes | O(1) |
| `_parse_raw_response` | private | Optional[ToolCall] | None | None | Yes | O(n) |
| `_extract_tool_call` | private | ToolCall | MalformedResponseError | None | Yes | O(1) |
| `_response_to_dict` | private | Dict[str, Any] | None | None | Yes | O(n) |

#### Example Usage
```python
from agent_host.tool_parser import ToolCallParser

parser = ToolCallParser()

# Parse GeminiClient response
response = {"function_call": {"name": "search_files", "args": {"query": "python"}}}
tool_call = parser.parse_response(response)
if tool_call:
    print(f"Tool: {tool_call.name}")
    print(f"Args: {tool_call.arguments}")

# Safe parsing (no exceptions)
tool_call, error = parser.parse_response_safe(response)
if error:
    print(f"Parse error: {error}")
elif tool_call:
    print(f"Parsed: {tool_call}")
else:
    print("No function call in response")
```

---

## Functions (Document ALL Functions)

### `parse_response(response)`

#### Function Metadata
| Field | Value |
|---|---|
| Signature | `(response: Any) -> Optional[ToolCall]` |
| Visibility | public |
| Pure Function | Yes |
| Thread-Safe | Yes |
| Idempotent | Yes |
| Status | Stable |

#### Parameters
| Name | Type | Required | Default | Validation | Example |
|---|---|---|---|---|---|
| `response` | Any | Yes | - | dict or SDK object | {"function_call": {...}} |

#### Returns
| Type | Meaning | Possible Values |
|---|---|---|
| Optional[ToolCall] | Parsed tool call or None | ToolCall if found, None if no function_call |

#### Errors / Exceptions
| Error Type | Condition | Recovery Strategy |
|---|---|---|
| `MalformedResponseError` | Invalid structure | Use parse_response_safe |

#### Supported Response Formats
1. **Dictionary with function_call key** (from GeminiClient)
   ```python
   {"function_call": {"name": "...", "args": {...}}, "text": None}
   ```

2. **Raw Gemini SDK response**
   ```python
   GenerateContentResponse with candidates[0].content.parts[0].function_call
   ```

3. **None** - Returns None

### `parse_response_safe(response)`

#### Function Metadata
| Field | Value |
|---|---|
| Signature | `(response: Any) -> Tuple[Optional[ToolCall], Optional[str]]` |
| Visibility | public |
| Pure Function | Yes |
| Thread-Safe | Yes |
| Status | Stable |

#### Returns
| Type | Meaning |
|---|---|
| Tuple[Optional[ToolCall], Optional[str]] | (tool_call, error_message) |

Non-throwing alternative that returns error as string instead of raising.

---

## Error Handling Strategy

### Error Categories
| Category | Examples | Default Behavior | User Action |
|---|---|---|---|
| Malformed Response | Missing name field | Raise MalformedResponseError | Check response structure |
| No Function Call | Text-only response | Return None | Handle None case |
| Unknown Type | Unexpected response type | Return None | Log warning |

---

## Testing Documentation

### Unit Test Coverage
| Function/Class | Coverage | Test Location | Edge Cases Covered |
|---|---|---|---|
| `ToolCall` | Pending | `tests/unit/test_tool_parser.py` | Empty name, invalid args |
| `ToolCallParser.parse_response` | Pending | `tests/unit/test_tool_parser.py` | Valid, None, malformed |
| `ToolCallParser.parse_response_safe` | Pending | `tests/unit/test_tool_parser.py` | Error handling |

### Test Data
| Data Type | Source | Purpose |
|---|---|---|
| Mock responses | Fixture files | Test various response formats |
| Golden files | `tests/golden/fixtures/` | Regression testing |

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| [`agent_host/gemini_client.py`](gemini_client.md) | Produces | Creates responses we parse |
| [`agent_host/schema_validator.py`](schema_validator.md) | Consumes | Validates parsed calls |
| [`agent_host/audit_logger.py`](audit_logger.md) | Consumes | Logs parsed calls |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-16 | AI Agent (Claude) | Phase 1 implementation | Initial creation with ToolCall and ToolCallParser | Medium - bridges API and validation |
