# File Doc: `tests/unit/test_tool_parser.py`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `tests/unit/test_tool_parser.py` |
| Doc Path | `projects/personal-macos-ai-agent/files/tests/unit/test_tool_parser.md` |
| Language | Python 3.14+ |
| File Role | Unit Tests |
| Ownership | Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Updated runtime and pytest version references |
| Lines of Code (LOC) | ~400 |
| Cyclomatic Complexity | Low |
| Test Coverage | N/A (test file) |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:** Comprehensive unit tests for ToolCallParser and ToolCall classes, covering response parsing, error handling, and edge cases.

**Detailed responsibilities:**
- Test ToolCall dataclass creation and validation
- Test parsing valid function_call responses (both 'args' and 'arguments' keys)
- Test handling of missing function_call in responses
- Test handling of malformed responses (missing name, wrong types)
- Test parsing raw Gemini SDK response objects via mocking
- Test safe parsing methods
- Test edge cases with unknown response types

### What this file must NOT do (boundaries)
**Out of scope:**
- Test actual Gemini API calls
- Test schema validation
- Integration with other modules
- Performance testing

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| pytest | Test execution | On CI/CD and local dev | pytest handles failures |
| Developer | Manual testing | On demand | Console output |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
| `ToolCallParser` | Class under test | Tests exception raising | N/A |
| `ToolCall` | Dataclass under test | Tests exception raising | N/A |
| `unittest.mock.Mock` | Mock Gemini responses | Built-in | N/A |
| `pytest.raises` | Exception testing | Built-in assertion | N/A |

---

## Imports / Dependencies

### Internal Dependencies
| Import Path | What's Used | Why Needed | Coupling Level | Risk/Notes |
|---|---|---|---|---|
| `agent_host.tool_parser` | ToolCallParser, ToolCall, exceptions | Classes under test | High | Direct testing |

### External Dependencies
| Package | Version | License | What's Used | Why Needed | Security Risk | Alternatives |
|---|---|---|---|---|---|---|
| pytest | ^9.0.2 | MIT | test framework | Test execution | Low | unittest |
| unittest.mock | stdlib | PSF | Mock | Mock responses | Low | pytest-mock |

---

## Test Classes

### `TestToolCall`
Tests for the ToolCall dataclass.

| Test Method | Purpose | Expected Outcome |
|---|---|---|
| `test_create_valid_tool_call` | Valid creation | ToolCall created |
| `test_empty_name_raises_error` | Empty name validation | ValueError raised |
| `test_invalid_arguments_type_raises_error` | Non-dict args | ValueError raised |
| `test_to_dict` | Dict conversion | Correct dict structure |
| `test_str_representation` | String output | Contains name and args |
| `test_default_arguments` | Default empty dict | arguments == {} |
| `test_raw_response_stored` | Raw response storage | raw_response preserved |

### `TestParseValidResponse`
Tests for parsing valid function_call responses.

| Test Method | Purpose | Expected Outcome |
|---|---|---|
| `test_parse_dict_with_args` | Parse 'args' key | ToolCall with correct args |
| `test_parse_dict_with_arguments` | Parse 'arguments' key | ToolCall with correct args |
| `test_parse_with_both_args_and_arguments` | Precedence test | 'args' takes precedence |
| `test_parse_with_empty_args` | Empty arguments | ToolCall with empty dict |
| `test_parse_with_missing_args` | No args key | ToolCall with empty dict |
| `test_parse_complex_arguments` | Nested objects | All nested data preserved |

### `TestParseMissingFunctionCall`
Tests for handling responses without function_call.

| Test Method | Purpose | Expected Outcome |
|---|---|---|
| `test_none_response_returns_none` | None input | Returns None |
| `test_empty_dict_returns_none` | Empty dict | Returns None |
| `test_dict_without_function_call_returns_none` | Text response | Returns None |
| `test_function_call_is_none_returns_none` | function_call=None | Returns None |

### `TestParseMalformedResponse`
Tests for handling malformed responses.

| Test Method | Purpose | Expected Outcome |
|---|---|---|
| `test_function_call_not_dict_raises_error` | String function_call | MalformedResponseError |
| `test_function_call_is_list_raises_error` | List function_call | MalformedResponseError |
| `test_missing_name_raises_error` | No name field | MalformedResponseError |
| `test_empty_name_raises_error` | Empty name string | MalformedResponseError |
| `test_arguments_not_dict_raises_error` | String arguments | MalformedResponseError |
| `test_arguments_is_list_raises_error` | List arguments | MalformedResponseError |

### `TestParseRawResponse`
Tests for parsing raw Gemini SDK response objects.

| Test Method | Purpose | Expected Outcome |
|---|---|---|
| `test_parse_raw_response_with_function_call` | Valid raw response | ToolCall extracted |
| `test_parse_raw_response_empty_candidates` | Empty candidates | Returns None |
| `test_parse_raw_response_no_content` | No content | Returns None |
| `test_parse_raw_response_no_parts` | No parts | Returns None |
| `test_parse_raw_response_text_only` | Text without function call | Returns None |

### `TestSafeParsing`
Tests for parse_response_safe method.

| Test Method | Purpose | Expected Outcome |
|---|---|---|
| `test_successful_parse_returns_tool_call` | Valid response | (ToolCall, None) |
| `test_no_function_call_returns_none` | No function call | (None, None) |
| `test_malformed_response_returns_error` | Malformed | (None, error_message) |
| `test_invalid_args_returns_error` | Invalid args type | (None, error_message) |

### `TestUnknownResponseTypes`
Tests for handling unknown response types.

| Test Method | Purpose | Expected Outcome |
|---|---|---|
| `test_unknown_type_returns_none` | String input | Returns None |
| `test_number_returns_none` | Number input | Returns None |
| `test_list_returns_none` | List input | Returns None |

### `TestRawResponseStorage`
Tests for raw response storage in ToolCall.

| Test Method | Purpose | Expected Outcome |
|---|---|---|
| `test_dict_response_stored` | Dict preservation | All fields preserved |
| `test_raw_response_useful_for_debugging` | Debug info | Metadata accessible |

---

## Test Data / Fixtures

### Mock Objects Created
| Mock | Purpose | Structure |
|---|---|---|
| `mock_function_call` | Function call data | name, args attributes |
| `mock_part` | Response part | function_call attribute |
| `mock_content` | Content wrapper | parts list |
| `mock_candidate` | Candidate wrapper | content attribute |
| `mock_response` | Full response | candidates list |

### Shared Fixtures (from conftest.py)
| Fixture | Type | Purpose |
|---|---|---|
| `mock_api_key` | str | Test API key |

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `agent_host/tool_parser.py` | Tests | Class under test |
| `tests/conftest.py` | Uses | Shared fixtures |
| `tests/golden/test_golden_tool_calls.py` | Related | Also tests parsing |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Agent (Codex) | Dependency refresh | Updated Python and pytest version references | Low |
| 2026-01-16 | AI Agent | Initial implementation | Comprehensive unit tests for ToolCallParser | New file |
| 2026-01-18 | AI Agent (Codex) | Schema alignment | Update plan_ops example args to use ops/op fields | Low |
