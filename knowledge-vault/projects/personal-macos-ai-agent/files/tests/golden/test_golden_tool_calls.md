# File Doc: `tests/golden/test_golden_tool_calls.py`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `tests/golden/test_golden_tool_calls.py` |
| Doc Path | `projects/personal-macos-ai-agent/files/tests/golden/test_golden_tool_calls.md` |
| Language | Python 3.14+ |
| File Role | Golden Tests |
| Ownership | Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Updated runtime and pytest version references |
| Lines of Code (LOC) | ~300 |
| Cyclomatic Complexity | Low |
| Test Coverage | N/A (test file) |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:** Golden tests that verify known prompt -> tool call mappings using JSON fixture files.

**Detailed responsibilities:**
- Load test fixtures from `tests/golden/fixtures/` directory
- Test parsing of mock Gemini responses (dict and raw response formats)
- Verify parsed tool calls match expected fixtures
- Validate fixture tool calls against actual schemas
- Test end-to-end flow: parse -> validate -> extract
- Verify fixture file format correctness
- Test ToolCall serialization roundtrip

### What this file must NOT do (boundaries)
**Out of scope:**
- Call actual Gemini API
- Execute tool functionality
- Test individual module internals (covered by unit tests)
- Generate new fixtures automatically

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| pytest | Test execution | On CI/CD and local dev | pytest handles failures |
| Developer | Manual testing | On demand | Console output |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
| `ToolCallParser` | Parse responses | Built-in | N/A |
| `SchemaValidator` | Validate tool calls | Built-in | N/A |
| `ToolCall` | Dataclass operations | Built-in | N/A |
| `unittest.mock.Mock` | Create mock responses | Built-in | N/A |

---

## Imports / Dependencies

### Internal Dependencies
| Import Path | What's Used | Why Needed | Coupling Level | Risk/Notes |
|---|---|---|---|---|
| `agent_host.tool_parser` | ToolCallParser, ToolCall | Parse responses | High | Integration test |
| `agent_host.schema_validator` | SchemaValidator | Validate tool calls | High | Integration test |

### External Dependencies
| Package | Version | License | What's Used | Why Needed | Security Risk | Alternatives |
|---|---|---|---|---|---|---|
| pytest | ^9.0.2 | MIT | parametrize, fixtures | Test execution | Low | unittest |
| json | stdlib | PSF | load | Fixture parsing | Low | None |
| pathlib | stdlib | PSF | Path | File paths | Low | os.path |
| unittest.mock | stdlib | PSF | Mock | Mock responses | Low | pytest-mock |

---

## Helper Functions

### `load_fixture(fixture_path: Path) -> Dict[str, Any]`
Loads a golden test fixture from a JSON file.

### `get_fixture_files(fixtures_dir: Path) -> List[Path]`
Returns all JSON fixture files from the fixtures directory.

### `create_mock_raw_response(fixture: Dict[str, Any]) -> Mock`
Creates a mock Gemini SDK response object from fixture data for testing raw response parsing.

### `create_dict_response(fixture: Dict[str, Any]) -> Dict[str, Any]`
Creates a dictionary response (GeminiClient processed format) from fixture data.

---

## Test Classes

### `TestGoldenToolCalls`
Golden tests for tool call parsing from fixtures.

| Test Method | Purpose | Parametrized |
|---|---|---|
| `test_fixture_files_exist` | Verify fixtures exist | No |
| `test_parse_fixture_dict_response` | Parse dict format | Yes (4 fixtures) |
| `test_parse_fixture_raw_response` | Parse raw format | Yes (4 fixtures) |
| `test_validate_fixture_tool_calls` | Schema validation | Yes (4 fixtures) |

### `TestGoldenFixtureFormat`
Tests to validate fixture file format.

| Test Method | Purpose | Expected Outcome |
|---|---|---|
| `test_all_fixtures_have_required_fields` | Required fields present | All have test_id, description, etc. |
| `test_all_fixtures_have_valid_expected_tool_call` | expected_tool_call format | name and arguments present |

### `TestGoldenEndToEnd`
End-to-end tests using fixtures.

| Test Method | Purpose | Expected Outcome |
|---|---|---|
| `test_complete_flow_search_files` | Full flow for search_files | Parse, validate, verify all pass |
| `test_complete_flow_all_fixtures` | Full flow for all fixtures | All fixtures process correctly |

### `TestGoldenToolCallRoundtrip`
Tests for ToolCall serialization roundtrip.

| Test Method | Purpose | Parametrized |
|---|---|---|
| `test_to_dict_roundtrip` | Serialization roundtrip | Yes (4 fixtures) |

---

## Test Fixtures

### JSON Fixture Files
| File | Tool | Description |
|---|---|---|
| `search_files_001.json` | search_files | Basic file search query |
| `get_metadata_001.json` | get_metadata | Get metadata for multiple paths |
| `open_item_001.json` | open_item | Open file with default app |
| `run_automation_001.json` | run_automation | Run Shortcuts automation |

### Fixture Schema
```json
{
  "test_id": "tool_name_NNN",
  "description": "Human readable description",
  "mock_gemini_response": {
    "candidates": [{
      "content": {
        "parts": [{
          "functionCall": {
            "name": "tool_name",
            "args": { ... }
          }
        }]
      }
    }]
  },
  "expected_tool_call": {
    "name": "tool_name",
    "arguments": { ... }
  }
}
```

### Shared Fixtures (from conftest.py)
| Fixture | Type | Purpose |
|---|---|---|
| `fixtures_dir` | Path | Path to fixtures directory |
| `schemas_dir` | Path | Path to schemas directory |
| `mock_api_key` | str | Test API key |

---

## Parametrized Tests

### Fixture Names Used
All parametrized tests use these fixture files:
- `search_files_001.json`
- `get_metadata_001.json`
- `open_item_001.json`
- `run_automation_001.json`

Tests will skip gracefully if a fixture file is not found.

---

## Usage Pattern

### Adding New Golden Tests
1. Create a new fixture file in `tests/golden/fixtures/`
2. Follow the fixture schema format
3. Add the fixture name to parametrized test lists
4. Run tests to verify

### Fixture File Naming Convention
`{tool_name}_{NNN}.json` where:
- `{tool_name}` matches the schema $id
- `{NNN}` is a sequential number (001, 002, etc.)

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `agent_host/tool_parser.py` | Uses | Parsing functionality |
| `agent_host/schema_validator.py` | Uses | Validation functionality |
| `tests/golden/fixtures/*.json` | Uses | Test data |
| `tests/unit/test_tool_parser.py` | Related | More detailed unit tests |
| `tests/conftest.py` | Uses | Shared fixtures |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Agent (Codex) | Dependency refresh | Updated Python and pytest version references | Low |
| 2026-01-16 | AI Agent | Initial implementation | Golden tests for tool call parsing | New file |
