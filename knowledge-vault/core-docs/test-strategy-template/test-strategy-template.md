# Test Strategy: `<Project Name>`

## Document Metadata
| Field | Value |
|---|---|
| Project | `<project_slug>` |
| Doc Path | `projects/<project_slug>/tests/TEST-STRATEGY.md` |
| Status | Active |
| Last Edited (YYYY-MM-DD) |  |
| Last Major Edit (YYYY-MM-DD) |  |
| Modified By |  |
| WHY (Reason for last change) |  |
| Overall Test Coverage | X% |
| Test Maturity Level | Level 1-5 |

---

## Overview

### Testing Philosophy
**Our approach to testing:**

**Quality vs Speed trade-offs:**

**Risk tolerance:**

---

## Test Pyramid

### Distribution
```
          /\
         /E2E\      (5-10%)  - End-to-End
        /______\
       /        \
      /Integration\ (20-30%) - Integration
     /____________\
    /              \
   /  Unit Tests    \ (60-75%) - Unit
  /__________________\
```

### Current vs Target Distribution
| Test Type | Current % | Target % | Gap | Action Plan |
|---|---|---|---|---|
| Unit | X% | 70% | ±Y% |  |
| Integration | X% | 25% | ±Y% |  |
| E2E | X% | 5% | ±Y% |  |
| Performance | X% | - | - |  |
| Security | X% | - | - |  |

---

## Unit Testing

### Scope
**What we test at the unit level:**
- Individual functions
- Methods in isolation
- Pure logic
- Edge cases
- Error handling

### Unit Test Standards
| Standard | Requirement | Enforcement |
|---|---|---|
| Coverage Threshold | X% | CI blocks < X% |
| Test File Location | `tests/unit/` | Enforced by tooling |
| Naming Convention | `*.test.ext` | Linter check |
| Isolated | No external dependencies | Code review |
| Fast | < 1 second per test | Automated check |

### Unit Test Structure
```<language>
describe('ComponentName', () => {
  describe('methodName', () => {
    it('should handle normal case', () => {
      // Arrange
      const input = setupInput();
      
      // Act
      const result = methodName(input);
      
      // Assert
      expect(result).toBe(expected);
    });
    
    it('should handle edge case', () => { });
    it('should throw error when invalid', () => { });
  });
});
```

### Mocking Strategy
| What to Mock | How | Tool | Rationale |
|---|---|---|---|
| External APIs | Mock service | Jest/Sinon |  |
| Database | Mock repository | In-memory DB |  |
| File System | Virtual FS | mock-fs |  |
| Time/Date | Fixed time | timekeeper |  |

### Unit Test Checklist
- [ ] Tests follow AAA pattern (Arrange, Act, Assert)
- [ ] Each test tests ONE thing
- [ ] Tests are independent
- [ ] Tests are deterministic (no flakiness)
- [ ] Edge cases covered
- [ ] Error paths tested
- [ ] No actual I/O (network, disk, DB)

---

## Integration Testing

### Scope
**What we test at the integration level:**
- Component interactions
- Database operations
- External API calls (with test instances)
- Message queue processing
- File system operations

### Integration Test Standards
| Standard | Requirement | Enforcement |
|---|---|---|
| Coverage Goal | X% | Manual review |
| Test File Location | `tests/integration/` | Enforced by tooling |
| Test Data | Clean up after tests | CI check |
| Test Environment | Isolated | Docker compose |
| Run Time | < 5 minutes total | Monitored |

### Test Database Strategy
| Aspect | Approach | Rationale |
|---|---|---|
| Database Type | Same as production / Test DB |  |
| Data Isolation | Per-test transaction rollback |  |
| Schema Management | Migrations run before tests |  |
| Seed Data | Fixtures loaded per test |  |
| Cleanup | Automatic rollback / Manual |  |

### External Service Testing
| Service | Test Strategy | Tool |
|---|---|---|
| Third-party API | Mock server | WireMock/Nock |
| Internal API | Test instance | Docker |
| Message Queue | Test instance | TestContainers |

### Integration Test Checklist
- [ ] Real dependencies used (DB, cache, queues)
- [ ] Test data isolated between tests
- [ ] Cleanup after each test
- [ ] Network calls made to test services
- [ ] Tests can run in parallel
- [ ] Flaky tests are fixed or quarantined

---

## End-to-End (E2E) Testing

### Scope
**What we test end-to-end:**
- Complete user workflows
- Critical business paths
- Cross-system integrations
- UI interactions (if applicable)

### E2E Test Standards
| Standard | Requirement | Enforcement |
|---|---|---|
| Critical Paths Only | Top 10 user journeys | Manual curation |
| Test File Location | `tests/e2e/` | Enforced by tooling |
| Environment | Staging-like | CI/CD |
| Run Frequency | Pre-deployment | Mandatory gate |
| Timeout | < 15 minutes | CI config |

### E2E Test Framework
| Tool | Purpose | Version |
|---|---|---|
|  | Browser automation |  |
|  | API testing |  |
|  | Test orchestration |  |

### Critical User Journeys
| Journey | Priority | Frequency | Last Run | Status |
|---|---|---|---|---|
|  | P0/P1/P2 | Every deploy / Daily / Weekly | YYYY-MM-DD | ✅ / ❌ |

### E2E Test Checklist
- [ ] Tests mimic real user behavior
- [ ] Tests use production-like data
- [ ] Tests verify user-visible outcomes
- [ ] Tests include error scenarios
- [ ] Screenshots on failure
- [ ] Video recording available
- [ ] Clear failure messages

---

## Performance Testing

### Performance Test Types
| Type | What | When | Tool | Threshold |
|---|---|---|---|---|
| Load Testing | Sustained load | Weekly |  |  |
| Stress Testing | Breaking point | Monthly |  |  |
| Spike Testing | Sudden load | Monthly |  |  |
| Endurance Testing | Long duration | Quarterly |  |  |

### Performance Benchmarks
| Metric | Target | Acceptable | Critical | Current |
|---|---|---|---|---|
| Response Time (p50) | X ms | Y ms | Z ms |  |
| Response Time (p95) | X ms | Y ms | Z ms |  |
| Response Time (p99) | X ms | Y ms | Z ms |  |
| Throughput | X req/s | Y req/s | Z req/s |  |
| Error Rate | < 0.1% | < 1% | < 5% |  |
| Resource Usage | X% | Y% | Z% |  |

### Load Test Scenarios
| Scenario | Users | Duration | Ramp-Up | Purpose |
|---|---|---|---|---|
| Normal Load | X | Y min | Z min |  |
| Peak Load | X | Y min | Z min |  |
| Sustained Load | X | Y hours | Z min |  |

### Performance Test Checklist
- [ ] Tests run against staging environment
- [ ] Production-like data volume
- [ ] Realistic user behavior patterns
- [ ] Monitoring in place during tests
- [ ] Results compared to baseline
- [ ] Regressions investigated

---

## Security Testing

### Security Test Types
| Type | What | Frequency | Tool | Owner |
|---|---|---|---|---|
| SAST | Static code analysis | Every PR |  |  |
| DAST | Dynamic scanning | Weekly |  |  |
| Dependency Scan | Vulnerable dependencies | Daily |  |  |
| Penetration Test | Manual security test | Quarterly | External firm |  |
| Security Audit | Code review | Release | Security team |  |

### Security Test Coverage
| Attack Vector | Test Exists | Last Test | Last Vulnerability | Status |
|---|---|---|---|---|
| SQL Injection | Yes/No | YYYY-MM-DD | YYYY-MM-DD | Secure/At Risk |
| XSS | Yes/No |  |  |  |
| CSRF | Yes/No |  |  |  |
| Auth Bypass | Yes/No |  |  |  |
| Privilege Escalation | Yes/No |  |  |  |
| Data Exposure | Yes/No |  |  |  |

### Security Test Checklist
- [ ] Input validation tested
- [ ] Output encoding verified
- [ ] Authentication mechanisms tested
- [ ] Authorization rules verified
- [ ] Session management tested
- [ ] Cryptography tested
- [ ] No secrets in code/logs

---

## Test Data Management

### Test Data Strategy
| Data Type | Source | Refresh Frequency | PII Handling |
|---|---|---|---|
| Unit Test Data | Fixtures (code) | On-demand | None |
| Integration Test Data | Seed scripts | Per test run | Synthetic/Masked |
| E2E Test Data | Test DB | Daily | Fully anonymized |
| Performance Test Data | Data generator | Weekly | Synthetic only |

### Test Data Privacy
- [ ] No production data in tests
- [ ] PII fully anonymized
- [ ] Synthetic data generators used
- [ ] Test data access controlled
- [ ] Regular data audits

### Fixtures & Factories
| Purpose | Tool | Location | Usage |
|---|---|---|---|
| Simple objects | Factory pattern | `tests/factories/` |  |
| Complex scenarios | Fixtures | `tests/fixtures/` |  |
| API responses | JSON files | `tests/mocks/` |  |

---

## Test Environments

### Environment Matrix
| Environment | Purpose | Data | Deployment | Who Can Use |
|---|---|---|---|---|
| Local | Dev testing | Mocked/fixtures | Manual | Developers |
| CI | Automated tests | Test DB | Auto on PR | CI system |
| Staging | Pre-prod testing | Sanitized prod data | Auto on merge | Team |
| Production | - | Real data | Real deployment | End users only |

### Environment Parity
| Aspect | Dev | CI | Staging | Production | Gap |
|---|---|---|---|---|---|
| Infrastructure |  |  |  |  |  |
| Dependencies |  |  |  |  |  |
| Configuration |  |  |  |  |  |
| Data Volume |  |  |  |  |  |

---

## Test Automation

### CI/CD Integration
| Stage | Tests Run | Duration | Pass Threshold | Failure Action |
|---|---|---|---|---|
| Pre-commit | Linting | < 10s | 100% | Block commit |
| On PR | Unit + Integration | < 5 min | 100% | Block merge |
| Pre-deploy | All tests + E2E | < 15 min | 100% | Block deployment |
| Post-deploy | Smoke tests | < 2 min | 100% | Auto rollback |

### Test Commands
```bash
# Run all tests
<command>

# Run unit tests only
<command>

# Run integration tests
<command>

# Run specific test file
<command>

# Run with coverage
<command>

# Generate coverage report
<command>
```

### Flaky Test Management
| Test Name | Flakiness Rate | Root Cause | Fix Attempts | Status |
|---|---|---|---|---|
|  | X% |  | Count | Quarantined/Fixed/Investigating |

**Flaky Test Policy:**
- Tests with > 5% flakiness rate are quarantined
- Quarantined tests don't block CI
- Flaky tests must be fixed within 1 week or deleted
- Root cause analysis required for all flaky tests

---

## Test Coverage

### Coverage Goals
| Component | Current % | Target % | Gap | Priority |
|---|---|---|---|---|
| Overall | X% | Y% | ±Z% | High/Medium/Low |
| Core Logic | X% | Y% | ±Z% |  |
| API Layer | X% | Y% | ±Z% |  |
| Data Layer | X% | Y% | ±Z% |  |
| Utilities | X% | Y% | ±Z% |  |

### Coverage Enforcement
| Rule | Threshold | Enforcement | Exception Process |
|---|---|---|---|
| New code | X% | CI check | Team lead approval |
| Modified code | X% | CI check | Documented reason |
| Overall | X% | Weekly report | Improvement plan |

### Untested Areas
| Area | Why Untested | Risk | Plan to Address | Target Date |
|---|---|---|---|---|
|  |  | Low/Medium/High |  |  |

---

## Test Maintenance

### Test Ownership
| Test Suite | Owner | Backup | Last Review | Health |
|---|---|---|---|---|
| Unit tests | Dev team | - | YYYY-MM-DD | ✅ / ⚠️ / ❌ |
| Integration tests |  |  |  |  |
| E2E tests |  |  |  |  |
| Performance tests |  |  |  |  |

### Test Health Metrics
| Metric | Value | Trend | Target | Action Needed |
|---|---|---|---|---|
| Pass Rate | X% | ↑/→/↓ | 100% |  |
| Flakiness Rate | X% | ↑/→/↓ | < 1% |  |
| Avg Duration | X min | ↑/→/↓ | < Y min |  |
| Coverage | X% | ↑/→/↓ | Y% |  |

### Test Refactoring Needs
| Area | Issue | Impact | Effort | Priority |
|---|---|---|---|---|
|  |  | Low/Medium/High |  |  |

---

## Test Documentation

### Test Case Documentation
**All tests MUST have:**
- Clear test name describing what's being tested
- Arrange-Act-Assert structure
- Comments explaining WHY (not what)
- Expected behavior documented
- Edge cases listed

### Test Report Format
| Section | Content |
|---|---|
| Summary | Pass/fail counts, duration, coverage |
| Failures | Failed tests with stack traces |
| Flaky Tests | Tests that failed then passed |
| Coverage | Coverage change vs previous run |
| Performance | Duration change vs previous run |

---

## Debugging Failed Tests

### Debugging Checklist
- [ ] Read the full error message and stack trace
- [ ] Check if test is flaky (re-run)
- [ ] Verify test data setup
- [ ] Check for state leakage from other tests
- [ ] Verify mock setup
- [ ] Check environment configuration
- [ ] Review recent code changes
- [ ] Run test locally
- [ ] Add debug logging

### Common Test Failures
| Symptom | Likely Cause | Solution |
|---|---|---|---|
| Intermittent failure | Race condition, timing | Add proper async handling |
| Fails in CI only | Environment difference | Align CI with local |
| Fails after refactor | Test coupled to implementation | Rewrite to test behavior |
| All tests fail | Setup issue | Check test runner config |

---

## Testing Best Practices

### DO
- ✅ Test behavior, not implementation
- ✅ Use descriptive test names
- ✅ Keep tests simple and focused
- ✅ Make tests independent
- ✅ Use AAA pattern
- ✅ Test edge cases
- ✅ Clean up after tests
- ✅ Keep tests fast

### DON'T
- ❌ Test private methods directly
- ❌ Couple tests to implementation details
- ❌ Let tests depend on each other
- ❌ Test multiple things in one test
- ❌ Use production data
- ❌ Skip tests locally
- ❌ Ignore flaky tests
- ❌ Make tests too complex

---

## Continuous Improvement

### Testing Metrics to Track
| Metric | Current | Goal | Tracking Method |
|---|---|---|---|
| Test Coverage |  |  |  |
| Test Pass Rate |  |  |  |
| Test Duration |  |  |  |
| Flakiness Rate |  |  |  |
| Bug Escape Rate |  |  |  |

### Review Schedule
| Review Type | Frequency | Participants | Focus |
|---|---|---|---|
| Test Health | Weekly | Team | Pass rate, flakiness |
| Coverage Review | Sprint | Team | Gaps, improvement |
| Strategy Review | Quarterly | Team + Leads | Approach, tools |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
|  |  |  |  |  |
