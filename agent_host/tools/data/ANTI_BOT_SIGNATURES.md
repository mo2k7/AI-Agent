# Anti-Bot Signature Workflow

This file documents the maintenance workflow for `anti_bot_signatures.json`.

## Goals
- Keep anti-bot detection current as vendors evolve challenge pages.
- Require deterministic evidence (headers/body/scripts/cookies) before classification.
- Treat challenge responses as terminal tool errors (no bypass and no retries).

## Weekly Update Process
1. Review vendor documentation updates for challenge/captcha behavior:
   - Cloudflare Challenges / Turnstile
   - AWS WAF challenge & captcha actions
   - reCAPTCHA / hCaptcha docs
2. Review known WAF fingerprint changes from trusted signature projects.
3. Add or adjust provider signatures in a candidate JSON file.
4. Validate candidate format:
   - `python scripts/refresh_anti_bot_signatures.py --source /path/to/candidate.json --validate`
5. Promote candidate into tool data and bump version:
   - `python scripts/refresh_anti_bot_signatures.py --source /path/to/candidate.json --bump-version`
6. Run regression tests:
   - `poetry run pytest tests/unit/test_browse_web_security.py tests/unit/test_tool_executor_hardening_precision.py -q`

## Provider Entry Requirements
- Required fields: `id`, `error_class`, `confidence`, `min_signals`.
- Prefer at least one high-confidence deterministic signal:
  - vendor-specific response header
  - vendor-specific cookie marker
  - known challenge script URL
- Keep `min_signals` strict enough to avoid false positives.
