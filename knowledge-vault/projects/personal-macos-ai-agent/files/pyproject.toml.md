# pyproject.toml

**Purpose:** Poetry project configuration and build settings

**Path:** `pyproject.toml`

**Last Updated:** 2026-01-18 (SESSION-0005) - Bumped runtime and dev dependency versions

---

## Overview

Defines the Python project using Poetry for dependency management. Contains project metadata, dependencies, and tool configurations.

## Current Configuration

```toml
[tool.poetry]
name = "macos-ai-agent"
version = "0.1.0"
description = "Personal AI agent for macOS file management"
authors = ["Developer"]
readme = "README.md"

[tool.poetry.dependencies]
python = "^3.14"
google-genai = "^1.59.0"    # NEW: replaces google-generativeai
jsonschema = "^4.26.0"
python-dotenv = "^1.2.1"

[tool.poetry.group.dev.dependencies]
pytest = "^9.0.2"
pytest-cov = "^7.0.0"
pytest-asyncio = "^1.3.0"
ruff = "^0.14.13"
mypy = "^1.19.1"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

[tool.ruff]
line-length = 100
target-version = "py314"

[tool.mypy]
python_version = "3.14"
strict = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --cov=agent_host --cov-report=term-missing"
```

## Key Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `google-genai` | ^1.59.0 | New Gemini API client (replaces `google-generativeai`) |
| `jsonschema` | ^4.26.0 | Tool schema validation |
| `python-dotenv` | ^1.2.1 | Environment variable loading |

## Python Version

The project now requires **Python 3.14+** to leverage:
- Latest type hints and language features
- Full compatibility with `google-genai` package
- Better asyncio support

### Setting Up Python with pyenv

```bash
# Install pyenv (if not already installed)
brew install pyenv

# Add to ~/.zshrc:
export PYENV_ROOT="$HOME/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init - zsh)"

# Install and set Python 3.14
pyenv install 3.14.2
pyenv global 3.14.2

# Verify
python --version  # Should show Python 3.14.2
```

## Package Migration Note

**Important:** The project migrated from `google-generativeai` to `google-genai`:

- **OLD**: `google-generativeai` - Uses `genai.GenerativeModel()` with fixed model at init
- **NEW**: `google-genai` - Uses `genai.Client()` with per-request model selection

To install:
```bash
pip install google-genai jsonschema python-dotenv
```

## Related Files

- [`gemini_client.py`](agent_host/gemini_client.md) - Uses google-genai package
- [`config.py`](agent_host/config.md) - Uses python-dotenv
- [`schema_validator.py`](agent_host/schema_validator.md) - Uses jsonschema

---

## Change Log

| Date | Session | Change |
|------|---------|--------|
| 2026-01-18 | SESSION-0005 | Bumped dependency versions (google-genai 1.59.0, jsonschema 4.26.0, python-dotenv 1.2.1, pytest 9.0.2, pytest-cov 7.0.0, pytest-asyncio 1.3.0, ruff 0.14.13, mypy 1.19.1) |
| 2026-01-18 | SESSION-0003 | Upgraded Python from 3.11 to 3.14 |
| 2026-01-18 | SESSION-0003 | Replaced `google-generativeai` with `google-genai>=1.0.0` |
| 2026-01-18 | SESSION-0003 | Updated ruff and mypy target to py314 |
| 2026-01-17 | SESSION-0001 | Initial creation |
