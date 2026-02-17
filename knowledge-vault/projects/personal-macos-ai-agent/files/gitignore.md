# File Doc: `.gitignore`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `.gitignore` |
| Doc Path | `projects/personal-macos-ai-agent/files/gitignore.md` |
| Language | gitignore (Git) |
| File Role | Configuration |
| Ownership | Project Infrastructure |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-16 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-16 |
| Modified By | AI Agent (Subtask 1) |
| WHY (Reason for last change) | Initial project setup - Phase 1 implementation |
| Lines of Code (LOC) | 50 |
| Cyclomatic Complexity | N/A |
| Test Coverage | N/A |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:** Specifies intentionally untracked files that Git should ignore.

**Detailed responsibilities:**
- Excludes Python bytecode and cache files (__pycache__, *.pyc)
- Excludes build artifacts (dist/, build/, *.egg-info/)
- Excludes virtual environment directories (.venv, venv/, env/)
- Excludes IDE configuration files (.idea/, .vscode/, *.swp)
- Excludes macOS system files (.DS_Store)
- Excludes test artifacts (.coverage, .pytest_cache/, .mypy_cache/)
- Excludes log files (*.log, logs/)
- Excludes local environment configuration (.env, .env.local)

### What this file must NOT do (boundaries)
**Out of scope:**
- Should not ignore source code files
- Should not ignore documentation
- Should not ignore JSON schemas
- Should not ignore test fixtures

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| Git | Filter untracked files | On every git operation | Git parses patterns |
| GitHub | Display ignored files status | On repository view | N/A |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
| N/A | Configuration file only | N/A | N/A |

---

## Pattern Categories

### Python Patterns
- `__pycache__/` - Python bytecode cache
- `*.py[cod]` - Compiled Python files
- `*$py.class` - Java-like Python class files
- `.Python` - Python installation marker
- `build/`, `dist/`, `*.egg-info/` - Package build artifacts
- `*.egg` - Python egg packages

### Virtual Environment Patterns
- `.env` - dotenv environment file (also local config)
- `.venv` - Poetry default virtual environment
- `env/`, `venv/`, `ENV/` - Common venv directories

### IDE Patterns
- `.idea/` - JetBrains IDEs (PyCharm)
- `.vscode/` - Visual Studio Code
- `*.swp`, `*.swo` - Vim swap files

### macOS Patterns
- `.DS_Store` - Finder metadata
- `.AppleDouble` - Resource forks
- `.LSOverride` - Launch Services override

### Testing Patterns
- `.coverage` - Coverage.py data file
- `htmlcov/` - Coverage HTML reports
- `.pytest_cache/` - Pytest cache
- `.mypy_cache/` - MyPy cache
- `.ruff_cache/` - Ruff linter cache

### Logging Patterns
- `*.log` - Log files
- `logs/` - Log directory

### Local Config Patterns
- `.env.local` - Local environment overrides

---

## Security Considerations

### Trust Boundaries
| Boundary | Input Source | Validation Required | Sanitization |
|---|---|---|---|
| N/A | Local configuration | N/A | N/A |

### Secrets & Credentials
| Secret Type | Storage | Access Method | Rotation Policy |
|---|---|---|---|
| API Keys | .env (ignored) | python-dotenv | User managed |
| Local overrides | .env.local (ignored) | python-dotenv | User managed |

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `pyproject.toml` | Related config | Both configure project |
| `.env` | Excluded | Environment secrets file |
| `tests/` | Related | Test artifacts excluded |

---

## Maintainer Notes

### When to Update This Doc
- [ ] When adding new ignore patterns
- [ ] When project structure changes
- [ ] When new build tools are added

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-16 | AI Agent (Subtask 1) | Initial project setup | Created .gitignore with Python/macOS patterns | New file |
