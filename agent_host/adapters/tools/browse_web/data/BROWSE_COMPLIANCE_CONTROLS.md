# Browse-Web Compliance Controls

This document maps implemented controls to runtime enforcement:

1. **ToS / access restrictions**
   - Account/paywall/legal/login path/content gates block fetches as `access_restricted`.
2. **Data privacy**
   - PII regex detection + redaction on returned content and raw HTML.
3. **Retention**
   - In-memory cache TTL/cap from policy; compliance actions for cache purge + subject deletion.
   - Audit log retention pruning (days).
4. **Jurisdiction**
   - Jurisdiction inference + blocked TLD gates before fetch.
5. **Copyright/licensing**
   - Excerpt limit enforcement + source attribution metadata.
6. **Egress governance**
   - Domain/path/suffix denylist and optional allowlist mode.
7. **Auditability**
   - Tamper-evident hash chain on audit records + browse decision metadata logging.
8. **Security testing cadence**
   - Attestation file with max-age gate; regression scripts included.
9. **Change management**
   - Signature provenance metadata + release hash verification.
10. **Incident response**
   - Kill switch, challenge spike monitor, cooldown, incident log, and playbook.
