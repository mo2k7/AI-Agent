# Browse-Web Incident Playbook

## Trigger Conditions
- Challenge/captcha spike threshold exceeded for a domain.
- Prompt-injection detection spikes with similar payload fingerprints.
- Unexpected egress-policy violations for known-good workflows.

## Immediate Actions
1. Enable kill switch:
   - `export AI_AGENT_BROWSE_DISABLED=true`
2. Collect incident artifacts:
   - Browse incident log: `~/Library/Application Support/AIAgent/security/browse_incidents.jsonl`
   - Audit log: `~/.local/share/ai-agent/audit.log`
3. Confirm integrity:
   - Run audit integrity verification (`AuditLogger.verify_integrity_chain`).

## Containment
1. Purge volatile browse cache:
   - `browse_web` with `compliance_action=purge_cache_all`
2. Acknowledge incident after triage:
   - `browse_web` with `compliance_action=acknowledge_incident`

## Recovery / Rollback
1. Revert signature/policy changes to last approved version.
2. Re-run security regression suite:
   - `bash scripts/run_browse_security_regression.sh`
3. Update `browse_security_attestation.json` timestamp/status.
4. Disable kill switch only after tests pass and reviewer sign-off.
