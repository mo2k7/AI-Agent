# Security Best Practices Review Report

## Executive Summary
This review focused on the Python backend/security-sensitive runtime paths (`browse_web`, tool execution, and audit logging). The initial assessment identified **5 issues**: **1 Critical**, **1 High**, **2 Medium**, and **1 Low**. All five findings are now remediated with secure-by-default controls and targeted regression tests.

## Remediation Status (2026-02-16)
- [SBP-001] Resolved
- [SBP-002] Resolved
- [SBP-003] Resolved
- [SBP-004] Resolved
- [SBP-005] Resolved

## Critical Findings

### [SBP-001] Redirects are validated after network access (SSRF control bypass)
- Rule ID: `AGENT-WEB-SSRF-REDIRECT-001`
- Severity: **Critical**
- Status: **Resolved (2026-02-16)**
- Location:
  - `agent_host/tools/browse_web.py:805`
  - `agent_host/tools/browse_web.py:836`
  - `agent_host/tools/browse_web.py:840`
- Evidence:
  - Previous behavior allowed urllib auto-redirects before policy validation.
  - Redirect target validation now happens before each follow-up request hop.
- Impact: An attacker-controlled URL could previously trigger requests to internal/private targets before validation, enabling SSRF-style probing or metadata access attempts.
- Resolution:
  - Added `_NoRedirectHandler` to disable auto-follow redirects.
  - Enforced manual redirect handling with per-hop URL/IP validation and redirect count controls.
  - Preserved DNS/IP validation and host pinning for each hop.
- Verification:
  - `tests/unit/test_browse_web_security.py:11`

## High Findings

### [SBP-002] `robots.txt` fetch bypasses SSRF validation pipeline
- Rule ID: `AGENT-WEB-SSRF-ROBOTS-002`
- Severity: **High**
- Status: **Resolved (2026-02-16)**
- Location:
  - `agent_host/tools/browse_web.py:490`
  - `agent_host/tools/browse_web.py:497`
- Evidence:
  - Previous `_fetch_robots_txt` path used direct urlopen without reuse of hardened fetch flow.
- Impact: DNS rebinding between URL validation and `robots.txt` retrieval could route traffic to private/reserved targets.
- Resolution:
  - Routed `robots.txt` retrieval through `_fetch_url(...)`, inheriting SSRF/DNS/IP controls.
- Verification:
  - `tests/unit/test_browse_web_security.py:48`

## Medium Findings

### [SBP-003] Audit logs persist raw prompts and tool arguments without redaction
- Rule ID: `AGENT-LOG-PII-003`
- Severity: **Medium**
- Status: **Resolved (2026-02-16)**
- Location:
  - `agent_host/audit_logger.py:15`
  - `agent_host/audit_logger.py:122`
  - `agent_host/audit_logger.py:130`
  - `agent_host/config.py:117`
  - `agent_host/config.py:249`
  - `agent_host/main.py:5582`
  - `agent_host/main.py:5740`
- Evidence:
  - Audit events previously serialized unredacted payloads and included prompt content by default.
- Impact: Sensitive input could be written to disk and exposed through backups, support bundles, or local compromise.
- Resolution:
  - Added `redact_value(...)` before writing any audit event payload.
  - Enforced owner-only log permissions (`0o600`) on audit log files.
  - Added `AI_AGENT_AUDIT_INCLUDE_PROMPT` opt-in control (default: false).
- Verification:
  - `tests/unit/test_audit_logger_security.py:12`
  - `tests/unit/test_audit_logger_security.py:31`
  - `tests/unit/test_config_security_defaults.py:8`

### [SBP-004] TLS verification can be disabled per request
- Rule ID: `AGENT-WEB-TLS-004`
- Severity: **Medium**
- Status: **Resolved (2026-02-16)**
- Location:
  - `agent_host/tools/browse_web.py:61`
  - `agent_host/tools/browse_web.py:1231`
  - `schemas/browse_web.json:54`
- Evidence:
  - `verify_ssl` input could previously disable certificate verification per request.
- Impact: Compromised/prompt-injected paths could force insecure TLS and enable MITM interception.
- Resolution:
  - Gated insecure TLS behind explicit debug env flag `AI_AGENT_ALLOW_INSECURE_TLS=true`.
  - Enforced secure default behavior and strict boolean validation for `verify_ssl`.
  - Updated tool schema description to document the debug-only gate.
- Verification:
  - `tests/unit/test_tool_executor_hardening_precision.py:767`

## Low Findings

### [SBP-005] Default runtime privileges are broad for local execution tools
- Rule ID: `AGENT-DEFAULTS-PRIV-005`
- Severity: **Low**
- Status: **Resolved (2026-02-16)**
- Location:
  - `agent_host/config.py:56`
  - `agent_host/config.py:116`
  - `agent_host/tools/executor.py:262`
  - `agent_host/tools/run_automation.py:32`
- Evidence:
  - Defaults previously allowed broad file scope and larger local-execution blast radius.
- Impact: Prompt injection or policy bypass could increase local system impact unnecessarily.
- Resolution:
  - Defaulted `allowed_roots` to workspace/project root.
  - Defaulted `enable_open_item=false` and removed Terminal from open-item allowlist.
  - Restricted automation subprocess environment to a minimal allowlist, with explicit opt-in passthrough (`AI_AGENT_AUTOMATION_ENV_ALLOWLIST`).
- Verification:
  - `tests/unit/test_config_security_defaults.py:8`
  - `tests/unit/test_tool_executor_hardening_precision.py:751`
  - `tests/unit/test_tool_executor_hardening_precision.py:781`

## Verification Runs
- `./.venv/bin/pytest tests/unit/test_browse_web_security.py tests/unit/test_audit_logger_security.py tests/unit/test_config_security_defaults.py tests/unit/test_tool_executor_hardening_precision.py -q` → **41 passed**
- `./.venv/bin/pytest tests/unit/test_audit_guard.py tests/unit/test_config_privacy.py tests/unit/test_tool_executor.py -q` → **25 passed**
