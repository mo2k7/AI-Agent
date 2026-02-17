# File Doc: `tests/unit/test_schema_validator.py`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `tests/unit/test_schema_validator.py` |
| Doc Path | `projects/personal-macos-ai-agent/files/tests/unit/test_schema_validator.md` |
| Language | Python 3.14+ |
| File Role | Unit Tests |
| Ownership | Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Updated runtime and pytest version references |
| Lines of Code (LOC) | ~350 |
| Cyclomatic Complexity | Low |
| Test Coverage | N/A (test file) |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:** Comprehensive unit tests for the SchemaValidator class, covering schema loading, validation, and Gemini format conversion.

**Detailed responsibilities:**
- Test schema loading from directory (success and failure cases)
- Test all 8 tool schemas are loaded correctly
- Test valid tool call validation for all tools
- Test rejection of invalid tool calls (missing required, wrong type)
- Test `get_all_tools_for_gemini()` format conversion
- Test safe validation methods
- Test edge cases (empty directory, invalid JSON, no $id)

### What this file must NOT do (boundaries)
**Out of scope:**
- Test actual Gemini API integration
- Test tool execution
- Performance testing
- Integration with other modules

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| pytest | Test execution | On CI/CD and local dev | pytest handles failures |
| Developer | Manual testing | On demand | Console output |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
| `SchemaValidator` | Class under test | Tests exception raising | N/A |
| `pytest.raises` | Exception testing | Built-in assertion | N/A |
| `pytest.fixture` | Test data setup | Built-in | N/A |

---

## Imports / Dependencies

### Internal Dependencies
| Import Path | What's Used | Why Needed | Coupling Level | Risk/Notes |
|---|---|---|---|---|
| `agent_host.schema_validator` | SchemaValidator, all exceptions | Class under test | High | Direct testing |

### External Dependencies
| Package | Version | License | What's Used | Why Needed | Security Risk | Alternatives |
|---|---|---|---|---|---|---|
| pytest | ^9.0.2 | MIT | test framework | Test execution | Low | unittest |
| pathlib | stdlib | PSF | Path | File paths | Low | os.path |

---

## Test Classes

### `TestSchemaLoading`
Tests for schema loading functionality.

| Test Method | Purpose | Expected Outcome |
|---|---|---|
| `test_load_schemas_from_directory` | Verify schemas load | schemas dict populated |
| `test_load_all_eight_schemas` | Verify all 8 tools | All tool names present |
| `test_nonexistent_directory_raises_error` | Missing dir handling | SchemaLoadError raised |
| `test_directory_is_file_raises_error` | Invalid path handling | SchemaLoadError raised |
| `test_empty_directory_warns` | Empty dir handling | Warning logged, no error |
| `test_invalid_json_raises_error` | Malformed JSON | SchemaLoadError raised |
| `test_invalid_schema_raises_error` | Invalid JSON Schema | SchemaLoadError raised |
| `test_reload_schemas` | Schema reload | New schemas loaded |

### `TestToolCallValidation`
Tests for tool call validation.

| Test Method | Purpose | Expected Outcome |
|---|---|---|
| `test_validate_search_files_valid` | Valid search_files | Returns True |
| `test_validate_search_files_with_optional` | Optional params | Returns True |
| `test_validate_search_files_missing_required` | Missing required | ValidationFailedError |
| `test_validate_get_metadata_valid` | Valid get_metadata | Returns True |
| `test_validate_get_metadata_wrong_type` | Wrong type | ValidationFailedError |
| `test_validate_read_text_valid` | Valid read_text | Returns True |
| `test_validate_extract_content_valid` | Valid extract_content | Returns True |
| `test_validate_plan_ops_valid` | Valid plan_ops | Returns True |
| `test_validate_apply_ops_valid` | Valid apply_ops | Returns True |
| `test_validate_open_item_valid` | Valid open_item | Returns True |
| `test_validate_run_automation_valid` | Valid run_automation | Returns True |
| `test_validate_unknown_tool_raises_error` | Unknown tool | SchemaNotFoundError |
| `test_validate_wrong_argument_type` | Type mismatch | ValidationFailedError |

### `TestSafeValidation`
Tests for non-throwing validation method.

| Test Method | Purpose | Expected Outcome |
|---|---|---|
| `test_valid_returns_true_none` | Valid call | (True, None) |
| `test_invalid_returns_false_errors` | Invalid call | (False, errors) |
| `test_unknown_tool_returns_false` | Unknown tool | (False, errors) |

### `TestGetSchema`
Tests for schema retrieval.

| Test Method | Purpose | Expected Outcome |
|---|---|---|
| `test_get_existing_schema` | Get valid schema | Schema dict returned |
| `test_get_nonexistent_schema_raises_error` | Missing schema | SchemaNotFoundError |

### `TestGeminiFormat`
Tests for Gemini format conversion.

| Test Method | Purpose | Expected Outcome |
|---|---|---|
| `test_gemini_format_structure` | Verify structure | name, description, parameters |
| `test_gemini_format_parameters` | Parameter formatting | Correct object structure |
| `test_gemini_format_all_tools` | All tools converted | 8 tools in output |
| `test_gemini_format_descriptions_present` | Non-empty descriptions | All have descriptions |

### `TestEdgeCases`
Tests for edge cases and special scenarios.

| Test Method | Purpose | Expected Outcome |
|---|---|---|
| `test_schema_without_id_uses_filename` | No $id handling | Uses filename as ID |
| `test_multiple_validation_errors` | Multiple errors | All errors captured |
| `test_extra_properties_allowed` | Extra props | Validation passes |

---

## Test Data / Fixtures

### Shared Fixtures (from conftest.py)
| Fixture | Type | Purpose |
|---|---|---|
| `schemas_dir` | Path | Path to schemas directory |
| `mock_api_key` | str | Test API key |
| `tmp_path` | Path | Temporary directory |

### Test Data Created In Tests
| Data | Purpose | Location |
|---|---|---|
| Invalid JSON schema | Test loading errors | tmp_path |
| Schema without $id | Test filename fallback | tmp_path |

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `agent_host/schema_validator.py` | Tests | Class under test |
| `schemas/*.json` | Uses | Real schema files |
| `tests/conftest.py` | Uses | Shared fixtures |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Agent (Codex) | Dependency refresh | Updated Python and pytest version references | Low |
| 2026-01-16 | AI Agent | Initial implementation | Comprehensive unit tests for SchemaValidator | New file |
| 2026-01-18 | AI Agent (Codex) | Schema alignment | Update plan_ops/extract_content/run_automation fixtures to match schema fields | Medium |
