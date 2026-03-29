# macOS AI Automation Agent

*A privacy-first, autonomous file management assistant powered by Google Gemini.*

This project implements a highly capable AI assistant that natively integrates with your macOS filesystem. Built entirely from scratch using a Hexagonal (Ports & Adapters) architecture, the agent can navigate, organize, search, and modify files based solely on natural language commands—all while treating the LLM as an untrusted operator within a strict defense-in-depth security sandbox.

## Key Features

- **Autonomous File Management**: Move, copy, rename, delete, and organize folders using natural context.
- **Strict Security Guardrails**: Path sandboxing, SSRF DNS-level prevention, and approval gates prevent catastrophic operations.
- **Encrypted Semantic Memory**: AES-256-GCM encrypted local state with macOS Keychain integration.
- **3 Execution Modes**: Run in *Direct* mode for speed, *Plan* mode for complex multi-step workflows via NLP clarification, or *Teacher* mode for active learning.
- **Cross-Platform IPC**: Native Swift macOS frontend with iOS connectivity via Tailscale.

## Quickstart

### Requirements
- Python 3.13+
- macOS (Tahoe or later recommended)
- Google Gemini API Key

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/mo2k7/Local-AI-Assistant.git
   cd Local-AI-Assistant
   ```

2. **Install dependencies:**
   ```bash
   poetry install
   ```

3. **Configure Environment:**
   ```bash
   cp .env.example .env
   # Add your GOOGLE_API_KEY inside the .env file
   ```

*(For advanced security configurations, hash-pin rotations, and explicit path sandboxing limits, refer to the `.env.example` file).*

## Development & Testing

Built with an emphasis on production-grade standards, the custom orchestration codebase is backed by rigid linting, type-checking, and comprehensive test coverage.

**Running the Test Suite:**
```bash
poetry run pytest
poetry run pytest --cov
```

**Quality Checks:**
```bash
poetry run ruff check .
poetry run mypy agent_host
```

## Architecture

- `agent_host/` - The core AI orchestration, tool execution, and memory managers.
- `schemas/` - Strict JSON schemas for sandboxed tool validation.
- `tests/` - High-leverage unit and golden snapshot tests.
- `ui/` - Native Swift frontend interface.

---

### License & Copyright

**Copyright © 2026 Muhammad Abdullah. All rights reserved.**  
Closed-source proprietary software. See the `LICENSE` file and `docs/licensing_policy.md` for complete operational policies and legal terms.
