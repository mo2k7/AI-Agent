# File Doc: `agent_host/config.py`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `agent_host/config.py` |
| Doc Path | `projects/personal-macos-ai-agent/files/agent_host/config.md` |
| Language | Python 3.12 |
| File Role | Configuration management |
| Ownership | Core Infrastructure |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Raise ConfigurationError for invalid numeric env values |
| Lines of Code (LOC) | ~150 |
| Cyclomatic Complexity | Low |
| Test Coverage | Pending |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:** Provides configuration management for the AI Agent through a Config dataclass with environment variable loading.

**Detailed responsibilities:**
- Define configuration schema via Config dataclass
- Load configuration from environment variables
- Validate configuration values on creation
- Provide sensible defaults for optional settings
- Error on missing required configuration (API key)

### What this file must NOT do (boundaries)
**Out of scope:**
- Should NOT store secrets in files
- Should NOT manage runtime state
- Should NOT perform business logic
- Should NOT make API calls

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| `main.py` | Initialize application config | On startup | Exit on ConfigurationError |
| Tests | Create test configurations | Per test | Catch ConfigurationError |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
| `os.environ` | Read environment variables | Returns None | Uses defaults |
| `pathlib.Path` | Handle file paths | N/A | N/A |

---

## Imports / Dependencies

### Internal Dependencies
| Import Path | What's Used | Why Needed | Coupling Level | Risk/Notes |
|---|---|---|---|---|
| None | - | - | - | - |

### External Dependencies
| Package | Version | License | What's Used | Why Needed | Security Risk | Alternatives |
|---|---|---|---|---|---|---|
| stdlib `os` | 3.12 | PSF | `environ.get()` | Read env vars | Low | None |
| stdlib `pathlib` | 3.12 | PSF | `Path` | Path handling | Low | None |
| stdlib `dataclasses` | 3.12 | PSF | `@dataclass`, `field` | Config structure | Low | attrs, pydantic |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `Config` | class | public | Stable | Main configuration dataclass |
| `ConfigurationError` | class | public | Stable | Exception for config errors |

---

## Types (Classes / Structs / Enums / Interfaces)

### `ConfigurationError`
| Metadata | Value |
|---|---|
| Kind | class (Exception) |
| Purpose | Indicate missing or invalid configuration |
| Thread-Safe | Yes |
| Immutable | Yes |
| Serializable | Yes (standard Exception) |
| Related Types | Exception |

#### Inheritance & Implementation
- **Extends:** `Exception`
- **Implements:** N/A
- **Used By:** `Config.__post_init__()`, `Config.from_env()`

### `Config`
| Metadata | Value |
|---|---|
| Kind | dataclass |
| Purpose | Hold all configuration values for the agent |
| Thread-Safe | Yes (immutable after init) |
| Immutable | Effectively (no mutations expected) |
| Serializable | Yes |
| Related Types | ConfigurationError |

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `gemini_api_key` | str | public | - | Yes | No | Google API key | Non-empty | Required |
| `model_name` | str | public | "gemini-2.0-flash-exp" | No | No | Gemini model name | None | - |
| `schemas_dir` | Path | public | project/schemas | No | No | Schema files location | Path object | Factory default |
| `audit_log_path` | Path | public | ~/.local/share/ai-agent/audit.log | No | No | Audit log file path | Path object | Factory default |
| `max_retries` | int | public | 3 | No | No | API retry attempts | >= 0 | - |
| `retry_delay` | float | public | 1.0 | No | No | Initial retry delay | >= 0 | Seconds |

#### Methods
| Method | Signature | Visibility | Parameters | Returns | Throws/Errors | Side Effects | Thread-Safe | Complexity | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `__post_init__` | `() -> None` | public | - | None | ConfigurationError | None | Yes | O(1) | Validates fields |
| `from_env` | `(env_prefix, api_key_var) -> Config` | public | 2 opt | Config | ConfigurationError | Reads env | Yes | O(1) | Class method |
| `validate_schemas_dir` | `() -> bool` | public | - | bool | None | Reads fs | Yes | O(n) | Checks dir exists |

#### Example Usage
```python
# Load from environment (typical usage)
config = Config.from_env()

# Direct instantiation for testing
config = Config(
    gemini_api_key="test-key",
    model_name="gemini-pro",
    schemas_dir=Path("./test-schemas"),
)

# Validate schemas directory
if not config.validate_schemas_dir():
    print("Warning: schemas directory missing or empty")
```

---

## Functions (Document ALL Functions)

### `_get_project_root()`
| Field | Value |
|---|---|
| Signature | `() -> Path` |
| Visibility | internal |
| Pure Function | Yes |
| Thread-Safe | Yes |
| Status | Stable |

Returns the project root directory (parent of agent_host).

### `_default_schemas_dir()`
| Field | Value |
|---|---|
| Signature | `() -> Path` |
| Visibility | internal |
| Pure Function | Yes |
| Thread-Safe | Yes |
| Status | Stable |

Returns default path to schemas directory.

### `_default_audit_log_path()`
| Field | Value |
|---|---|
| Signature | `() -> Path` |
| Visibility | internal |
| Pure Function | Yes |
| Thread-Safe | Yes |
| Status | Stable |

Returns default path to audit log file.

---

## Error Handling Strategy

### Error Categories
| Category | Examples | Default Behavior | User Action |
|---|---|---|---|
| Missing API Key | GOOGLE_API_KEY not set | Raise ConfigurationError | Set env var |
| Invalid Values | negative max_retries | Raise ConfigurationError | Fix config |

---

## Security Analysis

### Secrets & Credentials
| Secret Type | Storage | Access Method | Rotation Policy |
|---|---|---|---|
| GOOGLE_API_KEY | Environment variable | `os.environ.get()` | User-managed |

### Security Considerations
- API key never logged or printed
- API key never included in error messages
- Uses environment variables (12-factor app pattern)

---

## Testing Documentation

### Unit Test Coverage
| Function/Class | Coverage | Test Location | Edge Cases Covered |
|---|---|---|---|
| `Config` | Pending | `tests/unit/test_config.py` | Missing key, invalid values |
| `Config.from_env` | Pending | `tests/unit/test_config.py` | Env var presence/absence |

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| [`agent_host/gemini_client.py`](gemini_client.md) | Uses | Receives API key and settings |
| [`agent_host/schema_validator.py`](schema_validator.md) | Uses | Uses schemas_dir path |
| [`agent_host/audit_logger.py`](audit_logger.md) | Uses | Uses audit_log_path |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-16 | AI Agent (Claude) | Phase 1 implementation | Initial creation with Config dataclass and from_env() | High - core infrastructure |
| 2026-01-18 | AI Agent (Codex) | Env validation fix | Convert invalid retry values to ConfigurationError with clear messages | Medium - safer config parsing |
