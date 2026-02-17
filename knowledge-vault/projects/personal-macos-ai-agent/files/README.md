# File Doc: `README.md`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `README.md` |
| Doc Path | `projects/personal-macos-ai-agent/files/README.md` |
| Language | Markdown |
| File Role | Documentation |
| Ownership | Project Infrastructure |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Updated runtime requirement to Python 3.14 |
| Lines of Code (LOC) | 81 |
| Cyclomatic Complexity | N/A |
| Test Coverage | N/A |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:** Provides project overview, installation instructions, and usage documentation for developers.

**Detailed responsibilities:**
- Introduces the macOS AI Agent project and its capabilities
- Documents system requirements (Python 3.14+, macOS, Google API key)
- Provides step-by-step installation instructions using Poetry
- Documents environment variable configuration
- Shows how to run tests (pytest commands)
- Documents code quality tools (ruff, mypy)
- Displays project directory structure
- States license information

### What this file must NOT do (boundaries)
**Out of scope:**
- Should not contain API documentation (use separate API docs)
- Should not contain detailed architecture documentation
- Should not contain troubleshooting guides (separate wiki/docs)
- Should not contain changelog (use CHANGELOG.md)

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| Developers | Understand project and setup | On first access | N/A |
| GitHub | Repository homepage display | On repository view | N/A |
| pyproject.toml | Referenced as readme | On package build | N/A |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
| N/A | Documentation file only | N/A | N/A |

---

## Documentation Sections

### Overview
High-level introduction describing:
- Project purpose (AI-powered file management)
- Core capabilities (navigate, organize, search, create folders)
- Technology stack (Python, Google Gemini AI)

### Requirements
System prerequisites:
- Python 3.14 or higher
- macOS (Tahoe or later recommended)
- Google API key for Gemini AI access

### Installation
Step-by-step setup guide:
1. Clone repository
2. Install dependencies with Poetry
3. Configure environment variables (.env file)

### Development
Developer workflow documentation:
- Running tests with pytest
- Code coverage reporting
- Running specific test files
- Linting with ruff
- Type checking with mypy

### Project Structure
Directory tree showing:
- `agent_host/` - Main application package
- `agent_host/core/` - AI agent orchestration
- `agent_host/tools/` - File system operations
- `schemas/` - JSON schema definitions
- `tests/` - Test suite
- `tests/unit/` - Unit tests
- `tests/golden/` - Golden/snapshot tests

### License
MIT License reference

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `pyproject.toml` | References | README specified as package readme |
| `LICENSE` | Referenced | License details mentioned |
| `.env.example` | Referenced | Environment config template (to be created) |
| `agent_host/` | Documented | Main package described in structure |
| `tests/` | Documented | Test suite described in structure |

### Related ADRs
| ADR | Decision | Relevance |
|---|---|---|
| N/A | Poetry for package management | Installation instructions |

---

## Maintainer Notes

### When to Update This Doc
- [ ] When adding major features
- [ ] When changing installation steps
- [ ] When adding new commands/tools
- [ ] When project structure changes
- [ ] When requirements change

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Agent (Codex) | Update runtime requirement | Updated documented Python requirement to 3.14+ | Medium |
| 2026-01-16 | AI Agent (Subtask 1) | Initial project setup | Created README.md with full documentation | New file |
