# Security Audit: `<Project Name>`

## Document Metadata
| Field | Value |
|---|---|
| Project | `<project_slug>` |
| Doc Path | `projects/<project_slug>/security/SECURITY-AUDIT.md` |
| Audit Date (YYYY-MM-DD) |  |
| Auditor |  |
| Status | Active |
| Security Level | Low / Medium / High / Critical |
| Last Edited (YYYY-MM-DD) |  |
| Last Major Edit (YYYY-MM-DD) |  |
| Modified By |  |
| WHY (Reason for last change) |  |
| Next Audit Date |  |

---

## Executive Summary

### Security Posture
| Aspect | Rating | Trend | Notes |
|---|---|---|---|
| Overall Security | Low / Medium / High / Critical | ↑/→/↓ |  |
| Authentication | ✅ / ⚠️ / ❌ |  |  |
| Authorization | ✅ / ⚠️ / ❌ |  |  |
| Data Protection | ✅ / ⚠️ / ❌ |  |  |
| Input Validation | ✅ / ⚠️ / ❌ |  |  |
| Dependency Security | ✅ / ⚠️ / ❌ |  |  |

### Critical Findings Summary
| Severity | Count | Addressed | Remaining | Target Remediation |
|---|---|---|---|---|
| Critical (S0) |  |  |  | Immediate |
| High (S1) |  |  |  | < 7 days |
| Medium (S2) |  |  |  | < 30 days |
| Low (S3) |  |  |  | Next release |

---

## Authentication Security

### Authentication Mechanisms
| Mechanism | Implementation | Strength | Issues Found | Status |
|---|---|---|---|---|
|  | Password / OAuth / JWT / SAML / API Key |  |  | Secure / At Risk |

### Authentication Checklist
- [ ] Passwords hashed with modern algorithm (bcrypt, argon2)
- [ ] Salt unique per user
- [ ] Password complexity requirements enforced
- [ ] Account lockout after failed attempts
- [ ] Multi-factor authentication available
- [ ] Session tokens  cryptographically secure
- [ ] Tokens expire appropriately
- [ ] Refresh token rotation implemented
- [ ] No credentials in code/logs/URLs

### Password Security
| Aspect | Implementation | Standard | Compliant |
|---|---|---|---|
| Hashing Algorithm |  | bcrypt/argon2/scrypt | Yes/No |
| Salt | Per-user unique | Required | Yes/No |
| Min Length | X chars | ≥ 12 | Yes/No |
| Complexity | Requirements | Mixed case + numbers + symbols | Yes/No |
| Storage | Where | Never plaintext | Yes/No |

### Session Management
| Aspect | Implementation | Security Level | Issues |
|---|---|---|---|
| Session ID Generation |  | Secure/Weak |  |
| Session Storage |  | Secure/At Risk |  |
| Session Expiry | X minutes |  |  |
| Session Invalidation on Logout | Yes/No |  |  |
| Concurrent Session Handling |  |  |  |

---

## Authorization Security

### Authorization Model
**Model used:** RBAC / ABAC / ACL / Custom

### Role Definitions
| Role | Permissions | Users | Risk Level | Review Frequency |
|---|---|---|---|---|
|  |  | Count | Low/Medium/High | Monthly/Quarterly |

### Authorization Checklist
- [ ] All endpoints have authorization checks
- [ ] Principle of least privilege enforced
- [ ] No authorization in frontend only
- [ ] Vertical privilege escalation prevented
- [ ] Horizontal privilege escalation prevented
- [ ] Direct object references protected
- [ ] Admin functions properly secured
-[ ] API endpoints rate-limited

### Authorization Vulnerabilities
| Endpoint/Function | Vulnerability | Severity | Exploit Scenario | Mitigation | Status |
|---|---|---|---|---|---|
|  | IDOR / Privilege Escalation / Missing AuthZ | S0-S3 |  |  | Open/Fixed |

---

## Data Protection

### Data Classification
| Data Type | Classification | Storage | Encryption | Backup | Retention |
|---|---|---|---|---|---|
|  | Public/Internal/Confidential/Secret |  | At rest/In transit |  |  |

### Data Protection Checklist
- [ ] Data encrypted at rest
- [ ] Data encrypted in transit (TLS 1.2+)
- [ ] PII identified and protected
- [ ] Sensitive data not logged
- [ ] Database credentials encrypted
- [ ] API keys stored securely
- [ ] Backup data encrypted
- [ ] Data deletion process exists
- [ ] GDPR/compliance requirements met

### Encryption Implementation
| Data Type | Algorithm | Key Management | Rotation Policy | Status |
|---|---|---|---|---|
|  | AES-256 / RSA |  | Frequency | Secure / At Risk |

### PII Handling
| PII Type | Purpose | Minimization | Encryption | Retention | Deletion Process |
|---|---|---|---|---|---|
|  |  | Adequate/Excessive | Yes/No |  |  |

---

## Input Validation & Output Encoding

### Input Validation
| Input Point | Validation Type | Whitelist/Blacklist | Sanitization | Status |
|---|---|---|---|---|
|  | Schema/Regex/Type |  |  | Secure / At Risk |

### Input Validation Checklist
- [ ] All user input validated
- [ ] Whitelist validation used
- [ ] Input length limits enforced
- [ ] Special characters handled
- [ ] File uploads restricted (type, size)
- [ ] SQL injection prevented (parameterized queries)
- [ ] Command injection prevented
- [ ] Path traversal prevented
- [ ] XXE attacks prevented (XML parsing)

### Output Encoding
| Output Context | Encoding Method | XSS Risk | Status |
|---|---|---|---|
| HTML |  | Low/Medium/High | Secure / At Risk |
| JavaScript |  |  |  |
| URL |  |  |  |
| CSS |  |  |  |
| JSON |  |  |  |

### Known Injection Vulnerabilities
| Vulnerability Type | Location | Severity | Exploit | Mitigation | Status |
|---|---|---|---|---|---|
| SQL Injection |  | S0-S3 |  |  | Open/Fixed |
| XSS |  |  |  |  |  |
| Command Injection |  |  |  |  |  |
| LDAP Injection |  |  |  |  |  |

---

## Network Security

### Network Architecture
```
[Internet] ---> [WAF/CDN] ---> [Load Balancer] ---> [App Servers]
                                                           |
                                                           v
                                                    [Database]
```

### Network Security Checklist
- [ ] WAF/firewall in place
- [ ] TLS 1.2+ enforced
- [ ] HTTPS enforced (HTTP redirects)
- [ ] HSTS header set
- [ ] Certificate pinning (mobile apps)
- [ ] Internal services not exposed
- [ ] Rate limiting implemented
- [ ] DDoS protection in place
- [ ] Network segmentation implemented

### TLS/SSL Configuration
| Aspect | Configuration | Standard | Compliant |
|---|---|---|---|
| Min TLS Version | TLS 1.x | ≥ TLS 1.2 | Yes/No |
| Cipher Suites |  | Strong only | Yes/No |
| Certificate Validity |  | Valid | Yes/No |
| Certificate Issuer |  | Trusted CA | Yes/No |

### API Security
| Aspect | Implementation | Status |
|---|---|---|
| Authentication | API Keys / OAuth / JWT |  |
| Rate Limiting | X requests per Y time |  |
| Input Validation | All endpoints |  |
| CORS Policy | Restrictive list |  |
| API Versioning | Yes/No |  |

---

## Secrets Management

### Secrets Inventory
| Secret Type | Count | Storage Method | Rotation | Access Control | Risk |
|---|---|---|---|---|---|
| API Keys |  | Vault/Env/Code | Frequency | Who can access | Low/Medium/High |
| DB Credentials |  |  |  |  |  |
| Encryption Keys |  |  |  |  |  |
| Certificates |  |  |  |  |  |

### Secrets Management Checklist
- [ ] No secrets in source code
- [ ] No secrets in version control
- [ ] No secrets in logs
- [ ] No secrets in error messages
- [ ] No secrets in URLs
- [ ] Secrets stored in vault/secret manager
- [ ] Secrets rotated regularly
- [ ] Expired secrets revoked
- [ ] Access to secrets monitored

### Secret Rotation
| Secret Type | Current Rotation | Target Rotation | Last Rotated | Next Rotation |
|---|---|---|---|---|
|  | Every X days | Every Y days | YYYY-MM-DD | YYYY-MM-DD |

---

## Dependency Security

### Dependency Inventory
| Dependency | Version | License | Known Vulnerabilities | Last Updated | Status |
|---|---|---|---|---|---|
|  |  |  | CVE-XXXX-XXXX | YYYY-MM-DD | Secure / At Risk |

### Dependency Security Checklist
- [ ] Dependency scanning automated
- [ ] No known vulnerable dependencies
- [ ] Dependencies updated regularly
- [ ] Dependency licenses compatible
- [ ] Minimal dependencies used
- [ ] Transitive dependencies reviewed
- [ ] Lock files committed
- [ ] Private registry used (if applicable)

### Known Vulnerable Dependencies
| Dependency | Current Version | Vulnerable Version | CVE | Severity | Fixed Version | Upgrade Plan | Status |
|---|---|---|---|---|---|---|---|
|  |  |  |  | S0-S3 |  |  | Open/Fixed |

---

## Application Security

### Security Headers
| Header | Value | Purpose | Status |
|---|---|---|---|
| Content-Security-Policy |  | XSS prevention | Set / Missing |
| X-Frame-Options |  | Clickjacking prevention | Set / Missing |
| X-Content-Type-Options |  | MIME sniffing prevention | Set / Missing |
| Strict-Transport-Security |  | Force HTTPS | Set / Missing |
| X-XSS-Protection |  | XSS filter | Set / Missing |
| Referrer-Policy |  | Referrer control | Set / Missing |

### OWASP Top 10 Assessment
| Risk | Vulnerability | Present | Severity | Mitigation | Status |
|---|---|---|---|---|---|
| A01 Broken Access Control |  | Yes/No | S0-S3 |  | Secure/At Risk |
| A02 Cryptographic Failures |  | Yes/No |  |  |  |
| A03 Injection |  | Yes/No |  |  |  |
| A04 Insecure Design |  | Yes/No |  |  |  |
| A05 Security Misconfiguration |  | Yes/No |  |  |  |
| A06 Vulnerable Components |  | Yes/No |  |  |  |
| A07 Auth Failures |  | Yes/No |  |  |  |
| A08 Data Integrity Failures |  | Yes/No |  |  |  |
| A09 Logging Failures |  | Yes/No |  |  |  |
| A10 SSRF |  | Yes/No |  |  |  |

### CSRF Protection
| Form/Endpoint | CSRF Token | SameSite Cookie | Status |
|---|---|---|---|
|  | Yes/No | Strict/Lax/None | Secure / At Risk |

---

## Logging & Monitoring

### Security Logging
| Event Type | Logged | Retention | Monitored | Alerted |
|---|---|---|---|---|
| Failed login attempts | Yes/No |  | Yes/No | Yes/No |
| Successful logins |  |  |  |  |
| Authorization failures |  |  |  |  |
| Input validation failures |  |  |  |  |
| Security exceptions |  |  |  |  |
| Admin actions |  |  |  |  |
| Data access |  |  |  |  |

### Security Monitoring Checklist
- [ ] Failed authentication logged
- [ ] Authorization failures logged
- [ ] Security events monitored
- [ ] Anomaly detection in place
- [ ] Real-time security alerts
- [ ] Log aggregation implemented
- [ ] Logs immutable (WORM)
- [ ] No PII in logs
- [ ] Log retention policy defined

### Security Alerts
| Alert Type | Trigger | Recipient | Response Time | Status |
|---|---|---|---|---|
|  |  |  | X minutes | Active / Needs Setup |

---

## Incident Response

### Incident Response Plan
| Phase | Actions | Responsible | Documented |
|---|---|---|---|
| Detection |  |  | Yes/No |
| Analysis |  |  | Yes/No |
| Containment |  |  | Yes/No |
| Eradication |  |  | Yes/No |
| Recovery |  |  | Yes/No |
| Post-Incident |  |  | Yes/No |

### Security Contacts
| Role | Name/Contact | Availability | Backup |
|---|---|---|---|
| Security Lead |  | 24/7 / Business hours |  |
| Incident Manager |  |  |  |
| On-Call Engineer |  |  |  |
| Legal Contact |  |  |  |

### Past Security Incidents
| Date | Incident | Severity | Impact | Root Cause | Resolution | Prevented Recurrence |
|---|---|---|---|---|---|---|
| YYYY-MM-DD |  | S0-S3 |  |  |  | Yes/No |

---

## Compliance & Standards

### Compliance Requirements
| Standard | Applies | Status | Last Audit | Next Audit | Gaps |
|---|---|---|---|---|---|
| GDPR | Yes/No | Compliant / Non-compliant | YYYY-MM-DD | YYYY-MM-DD |  |
| HIPAA |  |  |  |  |  |
| PCI-DSS |  |  |  |  |  |
| SOC 2 |  |  |  |  |  |
| ISO 27001 |  |  |  |  |  |

### Compliance Checklist (GDPR Example)
- [ ] Privacy policy published
- [ ] Cookie consent implemented
- [ ] Right to erasure implemented
- [ ] Right to portability implemented
- [ ] Data processing agreements signed
- [ ] Data breach notification process
- [ ] DPO appointed (if required)
- [ ] DPIA done (if required)

---

## Penetration Testing

### Test History
| Date | Tester | Scope | Findings (S0/S1/S2/S3) | Status | Report |
|---|---|---|---|---|---|
| YYYY-MM-DD | Internal/External | Full/Partial | 0/2/5/10 | Complete | Link |

### Pentest Findings
| Finding | Severity | Description | Reproduction | Remediation | Status | Verified |
|---|---|---|---|---|---|---|
|  | S0-S3 |  |  |  | Open/Fixed | Yes/No |

### Next Pentest
| Aspect | Details |
|---|---|
| Scheduled Date | YYYY-MM-DD |
| Scope |  |
| Tester | Internal / External firm |
| Focus Areas |  |

---

## Third-Party Security

### Third-Party Integrations
| Service | Data Shared | Security Review | Last Review | Compliance | Risk |
|---|---|---|---|---|---|
|  |  | Yes/No | YYYY-MM-DD | GDPR/HIPAA/etc | Low/Medium/High |

### Vendor Security Checklist
- [ ] Security questionnaire completed
- [ ] SOC 2 report reviewed
- [ ] DPA signed
- [ ] SLA includes security terms
- [ ] Incident notification process defined
- [ ] Data location documented
- [ ] Vendor access monitored
- [ ] Regular security reviews

---

## Security Training

### Team Security Awareness
| Team Member | Last Training | Topics Covered | Next Training | Status |
|---|---|---|---|---|
|  | YYYY-MM-DD |  | YYYY-MM-DD | Current / Overdue |

### Required Training Topics
- [ ] Secure coding practices
- [ ] OWASP Top 10
- [ ] Authentication best practices
- [ ] Data protection
- [ ] Incident response
- [ ] Phishing awareness
- [ ] Social engineering
- [ ] Compliance requirements

---

## Remediation Plan

### Critical Issues (S0-S1)
| Issue | Severity | Owner | Target Date | Status | Blocker |
|---|---|---|---|---|---|
|  | S0/S1 |  | YYYY-MM-DD | Open/In Progress/Fixed |  |

### Medium/Low Issues (S2-S3)
| Issue | Severity | Owner | Target Date | Status | Priority |
|---|---|---|---|---|---|
|  | S2/S3 |  | YYYY-MM-DD | Open/In Progress/Fixed | High/Medium/Low |

### Security Improvements
| Improvement | Benefit | Effort | Priority | Target Release |
|---|---|---|---|---|
|  |  | Low/Medium/High |  |  |

---

## Security Metrics

### Security KPIs
| Metric | Current | Target | Trend | Notes |
|---|---|---|---|---|
| Known vulnerabilities |  | 0 | ↑/→/↓ |  |
| Avg time to patch critical |  | < 24h |  |  |
| Security test coverage |  | 100% |  |  |
| Failed login rate |  | < 1% |  |  |
| Incident response time |  | < 1h |  |  |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
|  |  |  |  |  |
