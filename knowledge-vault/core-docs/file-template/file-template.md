# File Doc: `<relative/path/to/file.ext>`

## File Metadata
| Field | Value |
|---|---|
| Project |  |
| Code File Path | `<relative/path/to/file.ext>` |
| Doc Path | `projects/<slug>/files/<normalized_path>.md` |
| Language |  |
| File Role |  |
| Ownership |  |
| Status | Active |
| Last Edited (YYYY-MM-DD) |  |
| Last Major Edit (YYYY-MM-DD) |  |
| Modified By |  |
| WHY (Reason for last change) |  |
| Lines of Code (LOC) |  |
| Cyclomatic Complexity |  |
| Test Coverage | X% |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**

**Detailed responsibilities:**
- 
- 
- 

### What this file must NOT do (boundaries)
**Out of scope:**
- 
- 

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
|  |  | On every request / Periodic / Event-based |  |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
|  |  |  |  |

---

## Imports / Dependencies

### Internal Dependencies
| Import Path | What's Used | Why Needed | Coupling Level | Risk/Notes |
|---|---|---|---|---|
|  | Functions/Classes |  | Low/Medium/High |  |

### External Dependencies
| Package | Version | License | What's Used | Why Needed | Security Risk | Alternatives |
|---|---|---|---|---|---|---|
|  |  |  |  |  | Low/Medium/High |  |

### Dependency Risk Assessment
| Dependency | Maintenance Status | Security History | Breaking Change Risk | Replacement Plan |
|---|---|---|---|---|
|  | Active / Stale | Clean / Issues |  |  |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
|  |  | public/protected/internal | Stable/Experimental/Deprecated |  |

### API Stability
| Symbol | Introduced Version | Deprecated Version | Breaking Changes History |
|---|---|---|---|
|  |  |  |  |

---

## Types (Classes / Structs / Enums / Interfaces)

### `<TypeName>`
| Metadata | Value |
|---|---|
| Kind | class / struct / enum / interface / protocol / type alias |
| Purpose |  |
| Thread-Safe | Yes / No / Conditionally |
| Immutable | Yes / No |
| Serializable | Yes / No |
| Related Types |  |

#### Inheritance & Implementation
- **Extends:** 
- **Implements:** 
- **Used By:** 
- **Polymorphic Behavior:** 

#### Invariants & Constraints
| Invariant | Enforcement | Violation Consequences |
|---|---|---|
|  | Constructor / Runtime / Static |  |

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
|  |  | public/private/protected |  | Yes/No | Yes/No |  |  |  |

#### Constructors
| Signature | Parameters | Preconditions | Postconditions | Throws/Errors |
|---|---|---|---|---|
|  |  |  |  |  |

#### Methods
| Method | Signature | Visibility | Parameters | Returns | Throws/Errors | Side Effects | Thread-Safe | Complexity | Notes |
|---|---|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  | Yes/No | O(?) |  |

#### Static Members
| Member | Type | Purpose | Mutability | Thread-Safe |
|---|---|---|---|---|
|  |  |  | Immutable/Mutable | Yes/No |

#### Example Usage
```<language>
// Basic usage
const instance = new TypeName(params);

// Common patterns
instance.method();

// Edge cases
try {
  instance.edgeCaseMethod();
} catch (error) {
  // Handle error
}
```

*(Repeat this section for EVERY type in the file)*

---

## Functions (Document ALL Functions)

### `<function_name>(...)`

#### Function Metadata
| Field | Value |
|---|---|
| Signature |  |
| Visibility | public / internal / private |
| Pure Function | Yes / No |
| Thread-Safe | Yes / No / Conditionally |
| Idempotent | Yes / No |
| Status | Stable / Experimental / Deprecated |
| Performance Tier | Fast / Normal / Slow / Critical |

#### Parameters
| Name | Type | Required | Default | Validation | Constraints | Example |
|---|---|---|---|---|---|---|
|  |  | Yes/No |  | Regex/range/etc |  |  |

#### Returns
| Type | Meaning | Possible Values | Notes |
|---|---|---|---|
|  |  |  |  |

#### Errors / Exceptions
| Error Type | Condition | Recovery Strategy | Should Retry |
|---|---|---|---|
|  |  |  | Yes/No |

#### Side Effects
| Side Effect | Scope | Reversible | Impact |
|---|---|---|---|
| File I/O | Writes to /path |  | High |
| Network Call | HTTP to API |  | Medium |
| Database Operation | Writes to table |  | High |
| State Mutation | Modifies object |  | Low |
| Logging | Writes logs |  | Low |

#### Threading / Async Behavior
- **Concurrency Model:** Synchronous / Async / Parallel / Actor
- **Blocking Behavior:** Blocks / Non-blocking / Conditional
- **Lock Acquisition:** None / Read-lock / Write-lock / Custom
- **Race Condition Risk:** None / Low / High (details)

#### Performance Characteristics
| Aspect | Details |
|---|---|
| Time Complexity | O(?) - Best / Average / Worst |
| Space Complexity | O(?) |
| Hot Path | Yes / No |
| Caching | Used / Not used |
| Optimization Notes |  |

#### Security Considerations
| Concern | Details | Mitigation |
|---|---|---|
| Input Validation |  |  |
| Output Sanitization |  |  |
| Authorization Check |  |  |
| Data Exposure Risk |  |  |

#### Example Usage
```<language>
// Basic usage
const result = functionName(param1, param2);

// With error handling
try {
  const result = functionName(param1, param2);
  // Use result
} catch (error) {
  // Handle specific error
}

// Edge case example
functionName(edgeCaseValue);
```

#### Test Coverage
| Test Type | Coverage | Location | Notes |
|---|---|---|---|
| Unit | X% | `tests/unit/filename.test` |  |
| Integration | X% | `tests/integration/filename.test` |  |
| Edge Cases Covered |  |  |  |

*(Repeat this section for EVERY function in the file)*

---

## State Management

### Module-Level State
| Variable | Type | Scope | Mutability | Thread-Safe | Purpose | Risk |
|---|---|---|---|---|---|---|
|  |  | Global/Module | Mutable/Immutable | Yes/No |  |  |

### State Transitions
```
[Initial State] --action--> [Intermediate State] --action--> [Final State]
```

### State Invariants
| Invariant | Enforcement Point | Violation Handling |
|---|---|---|
|  |  |  |

---

## Error Handling Strategy

### Error Categories
| Category | Examples | Default Behavior | User Action |
|---|---|---|---|
| Validation Errors |  | Throw / Return error |  |
| Network Errors |  | Retry / Fail |  |
| System Errors |  | Log + Alert |  |
| Business Logic Errors |  | Return error code |  |

### Error Propagation
```
[Function A] --throws--> [Function B] --catches--> [Handler]
```

### Recovery Strategies
| Error Type | Recovery | Fallback | User Impact |
|---|---|---|---|
|  |  |  |  |

---

## Concurrency & Threading

### Concurrency Model
- **Thread Safety:** Thread-safe / Not thread-safe / Conditionally
- **Synchronization Primitives:** None / Locks / Semaphores / Atomic operations
- **Async Patterns:** Callbacks / Promises / Async-await / Observables

### Potential Race Conditions
| Location | Description | Likelihood | Mitigation | Status |
|---|---|---|---|---|
|  |  | Low/Medium/High |  | Fixed/Open |

### Deadlock Risks
| Scenario | Resources Involved | Prevention | Detection |
|---|---|---|---|
|  |  |  |  |

---

## Performance Profile

### Performance Characteristics
| Metric | Value | Target | Acceptable Range |
|---|---|---|---|
| Execution Time (p50) | X ms |  |  |
| Execution Time (p95) | X ms |  |  |
| Memory Usage | X MB |  |  |
| CPU Usage | X% |  |  |
| I/O Operations | X per call |  |  |

### Hot Paths
| Code Section | % of Total Runtime | Optimization Potential | Notes |
|---|---|---|---|
|  |  | Low/Medium/High |  |

### Performance Bottlenecks
| Bottleneck | Impact | Solution | Status |
|---|---|---|---|
|  | High/Medium/Low |  | Planned/In Progress/Fixed |

### Caching Strategy
| What's Cached | Invalidation | TTL | Hit Rate | Storage |
|---|---|---|---|---|
|  |  |  | X% |  |

---

## Security Analysis

### Trust Boundaries
| Boundary | Input Source | Validation Required | Sanitization |
|---|---|---|---|
|  | User / External API / Internal |  |  |

### Authentication & Authorization
| Check Point | Method | Roles Required | Bypass Risk |
|---|---|---|---|
|  |  |  | Low/Medium/High |

### Secrets & Credentials
| Secret Type | Storage | Access Method | Rotation Policy |
|---|---|---|---|
|  | Env var / Vault / Config |  |  |

### Input Validation
| Input | Validation Rules | Sanitization | Attack Vectors |
|---|---|---|---|
|  |  |  |  |

### Output Encoding
| Output | Encoding | Context | XSS Risk |
|---|---|---|---|
|  |  | HTML/JSON/SQL | Low/Medium/High |

### Known Vulnerabilities
| Vulnerability | Severity | Status | Mitigation | Discovered |
|---|---|---|---|---|
|  | S0-S3 | Open/Fixed |  | YYYY-MM-DD |

---

## Testing Documentation

### Unit Test Coverage
| Function/Class | Coverage | Test Location | Edge Cases Covered |
|---|---|---|---|
|  | X% |  |  |

### Integration Test Coverage
| Integration Point | Coverage | Test Location | Scenarios Covered |
|---|---|---|---|
|  | X% |  |  |

### Test Dependencies
| Dependency | Type | Purpose | Setup Required |
|---|---|---|---|
|  | Mock / Stub / Fixture |  |  |

### Test Data
| Data Type | Source | Volume | Refresh Policy |
|---|---|---|---|
|  | Fixture / Generated |  |  |

### Testing Gaps
| Untested Area | Risk | Reason | Plan to Address |
|---|---|---|---|
|  | Low/Medium/High |  |  |

### Flaky Tests
| Test Name | Flakiness Rate | Root Cause | Fix Status |
|---|---|---|---|
|  | X% |  | Open/In Progress/Fixed |

---

## Debugging & Observability

### Logging Strategy
| Log Level | What's Logged | Frequency | PII Risk |
|---|---|---|---|
| DEBUG |  |  | Yes/No |
| INFO |  |  | Yes/No |
| WARN |  |  | Yes/No |
| ERROR |  |  | Yes/No |

### Debugging Hooks
| Hook | Purpose | How to Enable | Impact |
|---|---|---|---|
|  |  |  |  |

### Metrics & Instrumentation
| Metric | Type | Unit | Alert Threshold |
|---|---|---|---|
|  | Counter/Gauge/Histogram |  |  |

### Common Debug Scenarios
| Scenario | Symptoms | Diagnostic Steps | Common Causes |
|---|---|---|---|
|  |  |  |  |

---

## Integration Points

### External Services
| Service | Purpose | Protocol | Endpoint | Auth Method | Rate Limits | Error Handling | Circuit Breaker |
|---|---|---|---|---|---|---|---|
|  |  | REST/gRPC/etc |  |  |  |  | Yes/No |

### Database Interactions
| Operation | Table/Collection | Query Pattern | Index Used | Performance | Lock Acquired |
|---|---|---|---|---|---|
|  |  |  |  | X ms | None/Read/Write |

### File System Operations
| Operation | Path Pattern | Permissions Needed | Error Handling | Cleanup |
|---|---|---|---|---|
|  |  |  |  |  |

### Message Queues
| Queue | Direction | Message Format | Retry Policy | Dead Letter Queue |
|---|---|---|---|---|
|  | Publish/Subscribe |  |  | Yes/No |

---

## Technical Debt & Known Issues

### Known Bugs
| Bug ID | Description | Severity | Confidence | Repro Steps | Workaround | Status |
|---|---|---|---|---|---|---|
|  |  | S0-S3 | Confirmed/Suspected |  |  | Open/Fixed |

### Technical Debt
| Item | Type | Impact | Effort to Fix | Priority | Notes |
|---|---|---|---|---|---|
|  | Code smell/Hack/Workaround | Low/Medium/High | Hours/Days/Weeks |  |  |

### TODOs & FIXMEs
| Location | Type | Description | Priority | Assigned | Target Date |
|---|---|---|---|---|---|
| Line X | TODO |  | Low/Medium/High |  |  |

### Refactoring Opportunities
| Opportunity | Benefit | Risk | Effort | Decision |
|---|---|---|---|---|
|  |  | Low/Medium/High |  | Yes/No/Deferred |

---

## Change History & Evolution

### File History
| Date | Change Type | Description | Impact | Modified By |
|---|---|---|---|---|
|  | Created/Modified/Refactored |  |  |  |

### API Evolution
| Version | Change | Breaking | Migration Path | Deprecated Features |
|---|---|---|---|---|
|  |  | Yes/No |  |  |

### Performance Evolution
| Date | Metric | Before | After | Reason |
|---|---|---|---|---|
|  |  |  |  |  |

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
|  | Uses / Used by / Similar |  |

### Related ADRs
| ADR | Decision | Relevance |
|---|---|---|
| [`ADR-XXXX`](../adr/ADR-XXXX.md) |  |  |

### Related Issues
| Issue ID | Title | Status | Link |
|---|---|---|---|
|  |  | Open/Closed |  |

---

## Maintainer Notes

### Ownership
| Team/Person | Role | Expertise Area | Contact |
|---|---|---|---|
|  |  |  |  |

### Review History
| Date | Reviewer | Findings | Actions |
|---|---|---|---|
|  |  |  |  |

### When to Update This Doc
- [ ] When adding/removing public functions
- [ ] When changing public API signatures
- [ ] When adding new dependencies
- [ ] When fixing bugs
- [ ] When discovering security issues
- [ ] When performance characteristics change
- [ ] When adding TODOs or technical debt

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
|  |  |  |  |  |
