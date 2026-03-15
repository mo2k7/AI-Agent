# macOS AI Agent

Personal AI agent for macOS file management, powered by Google's Gemini AI.

## Overview

This project implements an AI-powered file management assistant for macOS that can:
- Navigate and organize files on your system
- Perform file operations (move, copy, rename, delete)
- Search for files based on natural language queries
- Create organized folder structures

## Requirements

- Python 3.13 or higher
- macOS (Tahoe or later recommended)
- Google API key for Gemini AI

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd macos-ai-agent
   ```

2. Install dependencies using Poetry:
   ```bash
   poetry install
   ```

3. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env and add your GOOGLE_API_KEY
   ```

4. (Optional, recommended) Review security-related runtime defaults:
   ```bash
   # File operations default to the project root. Set explicit roots as needed.
   AI_AGENT_ALLOWED_ROOTS=/absolute/path/one,/absolute/path/two

   # open_item is disabled by default; enable only if needed.
   AI_AGENT_ENABLE_OPEN_ITEM=false

   # Raw prompts are excluded from audit logs by default.
   AI_AGENT_AUDIT_INCLUDE_PROMPT=false

   # Keep TLS verification on by default.
   # Only for local debugging:
   # AI_AGENT_ALLOW_INSECURE_TLS=true

   # Automation scripts run with a minimal environment by default.
   # Optional comma-separated passthrough list:
   # AI_AGENT_AUTOMATION_ENV_ALLOWLIST=MY_VAR,ANOTHER_VAR
   ```

5. (Optional, recommended) Pin `unified-planning` package hash with rotation support:
   ```bash
   # Comma-separated SHA-256 digests: current + next allowed digest
   AI_AGENT_UNIFIED_PLANNING_HASH_PIN=<current_digest>,<next_digest>
   ```

6. (Optional, advanced) Enable secure automatic hash rotation:
   ```bash
   # Enables signed local trust-store updates after successful verification
   AI_AGENT_UNIFIED_PLANNING_HASH_PIN_AUTO_ROTATE=true
   AI_AGENT_UNIFIED_PLANNING_HASH_PIN_STORE_HMAC_KEY=<strong-secret>

   # Optional tuning
   AI_AGENT_UNIFIED_PLANNING_HASH_PIN_MAX_HISTORY=6
   # AI_AGENT_UNIFIED_PLANNING_HASH_PIN_STORE=~/.local/share/ai-agent/security/unified_planning_hash_store.json
   ```

7. (Optional) Tune Plan-mode planner-first behavior:
   ```bash
   # For actionable file-operation prompts in PLAN mode, this controls how many
   # discovery calls are allowed before planner/plan_ops is required.
   AI_AGENT_PLAN_MODE_DISCOVERY_BEFORE_PLANNER=2

   # Ask clarification questions first in PLAN mode when prompt requirements
   # are incomplete, so plans are not based on assumptions.
   AI_AGENT_PLAN_MODE_CLARIFICATION_REQUIRED=true
   ```

## Development

### Running Tests

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov

# Run specific test file
poetry run pytest tests/unit/test_specific.py
```

### Code Quality

```bash
# Lint with ruff
poetry run ruff check .

# Type check with mypy
poetry run mypy agent_host
```

## Project Structure

```
.
├── agent_host/          # Main package
│   ├── core/           # AI agent orchestration
│   └── tools/          # File system operations
├── schemas/            # JSON schemas for tool definitions
├── tests/
│   ├── unit/          # Unit tests
│   └── golden/        # Golden/snapshot tests
│       └── fixtures/  # Test fixtures
├── pyproject.toml     # Project configuration
└── README.md          # This file
```

## License

Closed-source proprietary software.

- Legal terms: [LICENSE](/Users/muhammadabdullah/AI%20Automation%20Agent%20macOS/LICENSE)
- Operational policy summary: [docs/licensing_policy.md](/Users/muhammadabdullah/AI%20Automation%20Agent%20macOS/docs/licensing_policy.md)
