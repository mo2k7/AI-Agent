# Project: `<Project Name>`

## Project Metadata
| Field | Value |
|---|---|
| Project Slug | `<project_slug>` |
| Project Name | `<Full Project Name>` |
| Doc Path | `projects/<project_slug>/PROJECT.md` |
| Repository URL |  |
| Primary Language(s) |  |
| Framework(s) |  |
| Runtime/Platform |  |
| Version | `X.Y.Z` |
| Status | Draft / Active / Stable / Deprecated |
| Owner/Team |  |
| Created Date (YYYY-MM-DD) |  |
| Last Edited (YYYY-MM-DD) |  |
| Last Major Edit (YYYY-MM-DD) |  |
| Modified By |  |
| WHY (Reason for last change) |  |

---

## Executive Summary

### What This Project Does
**One-sentence description:**

**Key capabilities:**
- 
- 
- 

### Who Uses This Project
| User Type | Use Case | Frequency |
|---|---|---|
|  |  |  |

### Project Health
| Metric | Status | Notes |
|---|---|---|
| Build Status | ✅ / ⚠️ / ❌ |  |
| Test Coverage | X% |  |
| Security Scan | ✅ / ⚠️ / ❌ |  |
| Documentation | ✅ / ⚠️ / ❌ |  |
| Active Development | Yes / No |  |

---

## Project Structure & Directory Map

### High-Level Architecture
```
project-root/
├── src/              # Source code
│   ├── core/        # Core business logic
│   ├── api/         # API/interface layer
│   ├── data/        # Data access layer
│   └── utils/       # Utility functions
├── tests/           # Test suites
├── docs/            # Documentation
├── config/          # Configuration files
├── scripts/         # Build/deployment scripts
└── deployment/      # Deployment configs
```

### Directory Manifest
**Document EVERY directory:**

| Directory Path | Purpose | Contains | Owner | Status | Notes |
|---|---|---|---|---|---|
| `/src` | Source code |  |  | Active |  |
| `/tests` | Test suites |  |  | Active |  |
| `/docs` | Documentation |  |  | Active |  |

### Key Files Locations
| File Type | Location | Purpose |
|---|---|---|
| Entrypoint(s) | `src/main.*` |  |
| Config | `config/` |  |
| Environment Variables | `.env.example` |  |
| Dependencies | `package.json` / `requirements.txt` / etc |  |
| Build | `Makefile` / `build.sh` |  |
| Docker | `Dockerfile`, `docker-compose.yml` |  |
| CI/CD | `.github/workflows/` |  |

---

## Technology Stack

### Core Technologies
| Technology | Version | Purpose | Why Chosen | Risk Level | Notes |
|---|---|---|---|---|---|
|  |  |  |  | Low/Medium/High |  |

### Dependencies (Major)
| Package/Library | Version | License | Purpose | Risk Assessment | Alternatives Considered |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

### Infrastructure & Services
| Service | Purpose | Provider | SLA/Tier | Cost Impact | Backup Plan |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

---

## Architecture & Design

### System Architecture
**Describe the overall architecture pattern (monolith, microservices, serverless, etc.):**

### Component Diagram
```
[Component A] ---> [Component B]
      |
      v
[Component C] <--- [External Service]
```

### Data Flow
**How does data move through the system?**

1. Input: 
2. Processing: 
3. Storage: 
4. Output: 

### Integration Points
| Integration | Type | Protocol | Purpose | Error Handling | Rate Limits |
|---|---|---|---|---|---|
|  | Internal/External | REST/gRPC/Queue/etc |  |  |  |

---

## Development Guide

### Prerequisites
- **Required Software:**
  - [ ] Language runtime (version X.Y)
  - [ ] Package manager
  - [ ] Database (if applicable)
  - [ ] Other tools

### Setup Instructions
```bash
# Clone repository
git clone <repo-url>

# Install dependencies
<command>

# Configure environment
cp .env.example .env
# Edit .env with your values

# Run migrations/setup
<command>

# Start development server
<command>
```

### Development Workflow
1. **Create feature branch:** `git checkout -b feature/xyz`
2. **Make changes**
3. **Run tests:** `<test command>`
4. **Commit:** Follow commit message conventions
5. **Push & create PR**

### Coding Standards
| Standard | Requirement | Enforcement |
|---|---|---|
| Code Style | <style guide> | Linter: <tool> |
| Naming Conventions |  | Code review |
| Documentation | All public APIs | Required |
| Test Coverage | X% minimum | CI check |
| Security Checks | All PRs | SAST tool |

### Common Commands
```bash
# Development
<start dev server>

# Testing
<run tests>
<run specific test>
<coverage report>

# Build
<build for production>

# Deployment
<deploy command>
```

---

## Testing Strategy

### Test Pyramid
| Test Type | Coverage | Location | Run Frequency |
|---|---|---|---|
| Unit Tests | X% | `tests/unit/` | Every commit |
| Integration Tests | X% | `tests/integration/` | Every PR |
| E2E Tests | X% | `tests/e2e/` | Pre-deployment |
| Performance Tests |  | `tests/performance/` | Weekly |

### Test Data Strategy
- **Fixtures:** Located in `tests/fixtures/`
- **Mocks:** Strategy for external services
- **Test DB:** How test database is managed

### Known Test Gaps
| Area | Gap Description | Risk | Plan to Address |
|---|---|---|---|
|  |  |  |  |

---

## Security Considerations

### Authentication & Authorization
- **Auth Method:** 
- **Authorization Model:** 
- **Session Management:** 
- **Role-Based Access:** 

### Secrets Management
| Secret Type | Storage Method | Rotation Policy | Access Control |
|---|---|---|---|
|  |  |  |  |

### Security Boundaries
| Boundary | Trust Level | Validation Required | Notes |
|---|---|---|---|
| User Input | Untrusted | All inputs | Sanitization + validation |
| External APIs | Semi-trusted |  |  |

### Known Security Concerns
| Concern | Severity | Mitigation | Status |
|---|---|---|---|
|  | S0-S3 |  | Open/Resolved |

---

## Performance & Scalability

### Performance Requirements
| Metric | Target | Current | Acceptable Range |
|---|---|---|---|
| Response Time (p95) | X ms | Y ms | < Z ms |
| Throughput | X req/sec | Y req/sec | > Z req/sec |
| Memory Usage | X MB | Y MB | < Z MB |
| Database Queries | X ms | Y ms | < Z ms |

### Scalability Architecture
- **Horizontal Scaling:** 
- **Vertical Scaling:** 
- **Bottlenecks Identified:** 
- **Caching Strategy:** 

### Performance Monitoring
| Metric | Tool | Alert Threshold | Response Plan |
|---|---|---|---|
|  |  |  |  |

---

## Deployment & Operations

### Environments
| Environment | URL | Purpose | Deployment Frequency | Who Can Deploy |
|---|---|---|---|---|
| Local | localhost | Development | Continuous | Developers |
| Dev/Staging |  | Testing | Daily | CI/CD |
| Production |  | Live | Weekly | Ops team |

### Deployment Process
1. **Pre-deployment:**
   - [ ] Run full test suite
   - [ ] Security scan
   - [ ] Database migration (if needed)
   - [ ] Backup current state

2. **Deployment:**
   - [ ] Deploy to staging
   - [ ] Smoke tests
   - [ ] Deploy to production
   - [ ] Health check

3. **Post-deployment:**
   - [ ] Monitor error rates
   - [ ] Verify key metrics
   - [ ] Document deployment

### Rollback Procedure
```bash
# If issues detected:
1. <rollback command>
2. <verify rollback>
3. <incident report>
```

### Monitoring & Alerts
| What We Monitor | Tool | Alert Condition | On-Call Response |
|---|---|---|---|
| Server Health |  |  |  |
| Error Rates |  |  |  |
| Performance |  |  |  |

---

## Troubleshooting Guide

### Common Issues
| Issue | Symptoms | Cause | Solution |
|---|---|---|---|
|  |  |  |  |

### Debug Checklist
- [ ] Check application logs: `<location>`
- [ ] Check system resources
- [ ] Verify external service connectivity
- [ ] Check database connection
- [ ] Review recent deployments

### Log Locations
| Log Type | Location | Retention | Format |
|---|---|---|---|
| Application |  |  |  |
| Error |  |  |  |
| Access |  |  |  |

---

## Dependencies & References

### Internal Dependencies
| Project/Service | Required For | Version Constraint | Contact |
|---|---|---|---|
|  |  |  |  |

### External References
- **Documentation:** 
- **API Specs:** 
- **Design Documents:** 
- **Related Projects:** 

### Team Contacts
| Role | Name/Contact | Responsibility | Availability |
|---|---|---|---|
| Project Owner |  |  |  |
| Lead Developer |  |  |  |
| DevOps |  |  |  |
| On-Call |  |  |  |

---

## Technical Debt & Future Work

### Known Technical Debt
| Item | Severity | Impact | Effort | Plan to Address |
|---|---|---|---|---|
|  | S0-S3 | High/Medium/Low |  |  |

### Roadmap
| Feature/Improvement | Priority | Target Timeline | Status |
|---|---|---|---|
|  | High/Medium/Low |  | Planned/In Progress/Done |

### Deferred Decisions
| Decision Area | Why Deferred | Revisit Date | Notes |
|---|---|---|---|
|  |  |  |  |

---

## Change History

### Major Milestones
| Date | Version | Milestone | Impact |
|---|---|---|---|
|  |  |  |  |

### Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
|  |  |  |  |  |

---

## Related Documentation

### Project Documents
- [`PROJECT.md`](./PROJECT.md) - This file
- [`tests/TEST-STRATEGY.md`](./tests/TEST-STRATEGY.md) - Testing details
- [`security/SECURITY-AUDIT.md`](./security/SECURITY-AUDIT.md) - Security audit
- [`performance/PERF-NOTES.md`](./performance/PERF-NOTES.md) - Performance docs

### File Documentation
**All file-level docs are in:** `files/<normalized_path>.md`

### Architecture Decision Records
**All ADRs are in:** `adr/ADR-XXXX-<title>.md`

### Session Handoffs
**If session handoffs are enabled for the workspace:** `sessions/SESSION-XXXX.md`
