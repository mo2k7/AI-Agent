# File Doc: `tests/conftest.py`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `tests/conftest.py` |
| Doc Path | `projects/personal-macos-ai-agent/files/tests/conftest.py.md` |
| Language | Python |
| File Role | Test Configuration |
| Ownership | Test Infrastructure |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Updated pytest version reference |
| Lines of Code (LOC) | 27 |
| Cyclomatic Complexity | 1 |
| Test Coverage | N/A (test infrastructure) |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:** Provides pytest configuration and shared fixtures for all tests in the test suite.

**Detailed responsibilities:**
- Provides `schemas_dir` fixture returning path to JSON schemas directory
- Provides `fixtures_dir` fixture returning path to golden test fixtures
- Provides `mock_api_key` fixture for testing without real API credentials
- Automatically sets up `GOOGLE_API_KEY` environment variable for all tests
- Centralizes test configuration to avoid duplication across test files

### What this file must NOT do (boundaries)
**Out of scope:**
- Should not contain actual test cases
- Should not contain application logic
- Should not contain real API credentials
- Should not perform file system operations outside test fixtures

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| pytest | Load fixtures and configuration | On every test run | pytest handles fixture errors |
| Individual test files | Use shared fixtures | Per test function | Fixture failure fails test |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
| `pathlib.Path` | File path manipulation | N/A | N/A |
| `pytest.fixture` | Register fixtures | N/A | N/A |
| `monkeypatch.setenv` | Set environment variables | N/A | N/A |

---

## Imports / Dependencies

### Internal Dependencies
| Import Path | What's Used | Why Needed | Coupling Level | Risk/Notes |
|---|---|---|---|---|
| N/A | No internal imports | Standalone test config | N/A | N/A |

### External Dependencies
| Package | Version | License | What's Used | Why Needed | Security Risk | Alternatives |
|---|---|---|---|---|---|---|
| pytest | ^9.0.2 | MIT | `pytest.fixture`, `monkeypatch` | Test framework | Low | unittest |
| pathlib | stdlib | PSF | `Path` | File path handling | None | os.path |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `schemas_dir` | fixture | public | Stable | Returns Path to schemas/ directory |
| `fixtures_dir` | fixture | public | Stable | Returns Path to tests/golden/fixtures/ |
| `mock_api_key` | fixture | public | Stable | Returns mock API key string |
| `env_setup` | fixture | public (autouse) | Stable | Auto-sets GOOGLE_API_KEY env var |

---

## Functions (Document ALL Functions)

### `schemas_dir()`

#### Function Metadata
| Field | Value |
|---|---|
| Signature | `schemas_dir() -> Path` |
| Visibility | public (pytest fixture) |
| Pure Function | Yes |
| Thread-Safe | Yes |
| Idempotent | Yes |
| Status | Stable |
| Performance Tier | Fast |

#### Parameters
| Name | Type | Required | Default | Validation | Constraints | Example |
|---|---|---|---|---|---|---|
| N/A | N/A | N/A | N/A | N/A | N/A | N/A |

#### Returns
| Type | Meaning | Possible Values | Notes |
|---|---|---|---|
| `Path` | Absolute path to schemas directory | `<project_root>/schemas` | Computed relative to conftest.py |

#### Example Usage
```python
def test_schema_exists(schemas_dir):
    """Test that schemas directory exists."""
    assert schemas_dir.exists()
    schema_file = schemas_dir / "tool_call.schema.json"
    assert schema_file.exists()
```

---

### `fixtures_dir()`

#### Function Metadata
| Field | Value |
|---|---|
| Signature | `fixtures_dir() -> Path` |
| Visibility | public (pytest fixture) |
| Pure Function | Yes |
| Thread-Safe | Yes |
| Idempotent | Yes |
| Status | Stable |
| Performance Tier | Fast |

#### Parameters
| Name | Type | Required | Default | Validation | Constraints | Example |
|---|---|---|---|---|---|---|
| N/A | N/A | N/A | N/A | N/A | N/A | N/A |

#### Returns
| Type | Meaning | Possible Values | Notes |
|---|---|---|---|
| `Path` | Absolute path to golden fixtures directory | `<project_root>/tests/golden/fixtures` | Computed relative to conftest.py |

#### Example Usage
```python
def test_golden_fixture_exists(fixtures_dir):
    """Test loading golden fixture."""
    fixture_file = fixtures_dir / "sample_input.json"
    assert fixture_file.exists()
```

---

### `mock_api_key()`

#### Function Metadata
| Field | Value |
|---|---|
| Signature | `mock_api_key() -> str` |
| Visibility | public (pytest fixture) |
| Pure Function | Yes |
| Thread-Safe | Yes |
| Idempotent | Yes |
| Status | Stable |
| Performance Tier | Fast |

#### Parameters
| Name | Type | Required | Default | Validation | Constraints | Example |
|---|---|---|---|---|---|---|
| N/A | N/A | N/A | N/A | N/A | N/A | N/A |

#### Returns
| Type | Meaning | Possible Values | Notes |
|---|---|---|---|
| `str` | Mock API key for testing | `"test-api-key-12345"` | Never a real API key |

#### Security Considerations
| Concern | Details | Mitigation |
|---|---|---|
| Credential Exposure | Returns fake API key | Hardcoded test value, never real |

#### Example Usage
```python
def test_api_initialization(mock_api_key):
    """Test API client initialization."""
    client = APIClient(api_key=mock_api_key)
    assert client.api_key == "test-api-key-12345"
```

---

### `env_setup(monkeypatch, mock_api_key)`

#### Function Metadata
| Field | Value |
|---|---|
| Signature | `env_setup(monkeypatch, mock_api_key) -> None` |
| Visibility | public (pytest fixture, autouse=True) |
| Pure Function | No (modifies environment) |
| Thread-Safe | Yes (scoped per test) |
| Idempotent | Yes |
| Status | Stable |
| Performance Tier | Fast |

#### Parameters
| Name | Type | Required | Default | Validation | Constraints | Example |
|---|---|---|---|---|---|---|
| `monkeypatch` | `pytest.MonkeyPatch` | Yes (injected) | N/A | N/A | pytest builtin fixture | N/A |
| `mock_api_key` | `str` | Yes (injected) | N/A | N/A | From mock_api_key fixture | `"test-api-key-12345"` |

#### Returns
| Type | Meaning | Possible Values | Notes |
|---|---|---|---|
| `None` | Sets up environment, no return value | N/A | N/A |

#### Side Effects
| Side Effect | Scope | Reversible | Impact |
|---|---|---|---|
| Sets GOOGLE_API_KEY env var | Test function scope | Yes (monkeypatch cleans up) | Low |

#### Notes
This fixture has `autouse=True`, meaning it automatically runs for every test function without needing to be explicitly requested.

---

## Testing Documentation

### Test Dependencies
| Dependency | Type | Purpose | Setup Required |
|---|---|---|---|
| pytest | Framework | Test runner | Install via `poetry install` |
| monkeypatch | Builtin fixture | Environment variable isolation | None |

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `pyproject.toml` | Configures | pytest configuration in [tool.pytest.ini_options] |
| `tests/__init__.py` | Parent package | Test suite root |
| `tests/unit/` | Uses fixtures | Unit tests consume these fixtures |
| `tests/golden/` | Uses fixtures | Golden tests consume these fixtures |
| `tests/golden/fixtures/` | Referenced | fixtures_dir points here |
| `schemas/` | Referenced | schemas_dir points here |

---

## Maintainer Notes

### When to Update This Doc
- [ ] When adding new fixtures
- [ ] When modifying fixture behavior
- [ ] When adding new autouse fixtures
- [ ] When changing environment variable setup

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Agent (Codex) | Dependency refresh | Updated pytest version reference | Low |
| 2026-01-16 | AI Agent (Subtask 1) | Initial project setup | Created conftest.py with core fixtures | New file |
