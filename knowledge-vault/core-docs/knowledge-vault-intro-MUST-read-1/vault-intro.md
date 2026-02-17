# AI Onboarding: Knowledge Vault (MUST READ FIRST)

## Metadata
| Field | Value |
|---|---|
| Doc Path | `core-docs/knowledge-vault-intro-MUST-read-1/vault-intro.md` |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-02-08 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-15 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Normalized session continuity protocol to match local override that disables SESSION-*.md handoff files |

---

## Prime Directive (NON-NEGOTIABLE)

### Local Override (2026-02-08)
- Session handoff files are disabled by explicit user preference in this workspace.
- Do not create `projects/*/sessions/SESSION-*.md` files unless the user explicitly re-enables them.
- Keep run-level history in this file's Agent Run Log and in change-history index entries instead.

### The Documentation Imperative
You do **not** get to "summarize what matters."
You must document **everything** that exists in scope: every file, every public-facing symbol (functions/classes/methods), and every convention.

**If a file exists and isn't in the registry, that is a failure.**

### The Laziness Prohibition
- **NO SHORTCUTS**: Do not skip documentation because "it's obvious"
- **NO ASSUMPTIONS**: Do not assume future agents will "figure it out"
- **NO DEFERRAL**: Do not defer documentation to "later" - document NOW
- **NO CHERRY-PICKING**: Document ALL files, not just "important" ones
- **NO SKELETONS**: Do not leave placeholder text - fill in REAL content

### Agent Accountability Principle
Every agent session inherits responsibility for maintaining documentation completeness. If you find gaps, YOU must fix them. "Previous agent didn't do it" is not an excuse.

---

## Vault Structure (Required)

### Core Documentation Hierarchy
```
knowledge-vault/
├── core-docs/                           # Templates and policies
│   ├── knowledge-vault-intro-MUST-read-1/
│   │   └── vault-intro.md              # THIS FILE - read first
│   ├── change-log-tracking-yaml/
│   │   └── log-tracker-yaml.yaml       # Change tracking policy
│   ├── knowledge-change-history-index-ALL-EDITS/
│   │   └── change-history-index.md     # Master vault index
│   ├── project-template/
│   │   └── project-template.md         # Template for new projects
│   ├── file-template/
│   │   └── file-template.md            # Template for file docs
│   └── ADR-template/
│       └── adr-template.md             # Template for decisions
├── projects/                            # Per-project documentation
│   └── <project_slug>/
│       ├── PROJECT.md                   # Project overview + directory map
│       ├── files/
│       │   └── <normalized_path>.md    # One doc per code file
│       ├── adr/
│       │   └── ADR-XXXX-<title>.md     # Architecture decisions
│       ├── sessions/
│       │   └── SESSION-XXXX.md         # Agent session handoffs
│       ├── tests/
│       │   └── TEST-STRATEGY.md        # Testing documentation
│       ├── security/
│       │   └── SECURITY-AUDIT.md       # Security documentation
│       └── performance/
│           └── PERF-NOTES.md           # Performance documentation
└── archive/                             # Deprecated/historical docs
```

---

## Operating Rules (Non-Negotiable)

### 1) Read Order (EVERY Session Start)
**You MUST read these files in this exact order before doing ANY work:**

| Priority | Document | Purpose | Required Action |
|---|---|---|---|
| 1 | `vault-intro.md` | Operating instructions | Internalize rules |
| 2 | `log-tracker-yaml.yaml` | Change tracking policy | Understand audit requirements |
| 3 | `change-history-index.md` | Master registry | Check what exists, find gaps |
| 4 | `PROJECT.md` (relevant) | Project context | Understand scope |
| 5 | `files/*.md` (relevant) | File documentation | Understand implementation |
| 6 | `adr/*.md` (relevant) | Past decisions | Understand WHY things are how they are |
| 7 | Agent Run Log (latest entry in this file) | Previous session continuity | Continue where predecessor stopped |

### 2) "Document Everything" Checklist (MANDATORY)

For **EACH** code file you touch, you MUST record ALL of the following:

#### A) File Identity & Context
| Item | What to Document | Example |
|---|---|---|
| File path | Full relative path from project root | `src/auth/login.ts` |
| Purpose | Single-sentence file responsibility | "Handles user authentication flow" |
| Boundaries | What this file must NOT do | "Does not handle session management" |
| Callers | Who/what invokes this file | "Called by Router, ExpressApp" |
| Ownership | Team/person responsible | "@backend-team" |

#### B) Dependencies & Imports
| Item | What to Document | Why It Matters |
|---|---|---|
| Internal imports | Other project files imported | Understand coupling |
| External dependencies | npm/pip/cargo packages used | Track security surface |
| Version constraints | Specific version requirements | Prevent breaking changes |
| Why each dependency | Reason for inclusion | Avoid zombie dependencies |
| Risk level per dependency | Security/maintenance risk | Prioritize updates |

#### C) Public Interface (EXHAUSTIVE)
Document EVERY exported/public symbol:

| Symbol Type | Required Fields |
|---|---|
| Functions | name, params (type+default+required), return type, throws/errors, side effects |
| Classes | name, purpose, inheritance, implements, constructors, all methods, all properties |
| Constants | name, type, value, why it exists |
| Types/Interfaces | name, fields with types, constraints, usage notes |
| Enums | name, all values, what each value means |

#### D) Implementation Details
| Category | What to Document |
|---|---|
| Algorithms | What algorithm is used, complexity (time/space) |
| Data structures | What structures are used, why chosen |
| State management | What state is held, how it changes, who mutates it |
| Control flow | Major decision points, loop invariants |
| Error handling | What errors can occur, how they're handled |

#### E) Runtime Behavior
| Category | What to Document |
|---|---|
| Side effects | File I/O, network calls, DB operations, logging |
| Concurrency | Threading model, async patterns, locks, race conditions |
| Resource usage | Memory allocation, connection pools, file handles |
| Caching | What is cached, invalidation strategy, TTL |
| Retries | Retry logic, backoff strategy, failure modes |

#### F) Security Surface
| Category | What to Document |
|---|---|
| Auth/AuthZ | Authentication checks, authorization rules |
| Input validation | What is validated, sanitization applied |
| Secrets handling | What secrets are used, how they're stored/accessed |
| Trust boundaries | Where trust assumptions change |
| Attack surface | Potential vulnerabilities, mitigations |

#### G) Testing & Quality
| Category | What to Document |
|---|---|
| Unit tests | What is tested, what is NOT tested, coverage gaps |
| Integration tests | What integrations are tested |
| Test dependencies | Mocks, stubs, fixtures needed |
| Test data | Sample data requirements, generators |
| Known test failures | Flaky tests, skipped tests, why |

#### H) Bugs & Technical Debt
| Category | What to Document |
|---|---|
| Known bugs | Confirmed issues with severity and repro steps |
| Suspected bugs | Potential issues with confidence level |
| Tech debt | Shortcuts, workarounds, "temporary" hacks |
| Refactoring opportunities | What should be improved |
| Future risks | What might break with scale/time |

### 3) Edit Metadata Rules (ENFORCED)

**Every Documentation Change MUST Include:**

| Action | When | How |
|---|---|---|
| Update "Last Edited" | EVERY change | Overwrite with today's date |
| Update "Last Major Edit" | Significant changes | Overwrite with today's date |
| Append to Major Edits Log | Significant changes | Add new row, NEVER delete old rows |
| Fill "Modified By" | EVERY change | Your agent identifier |
| Fill "WHY" | EVERY change | Why you made this change |

**What Counts as "Major"?**
- Architecture/behavior changed
- New module/file added or removed
- Public API changed
- New dependency added
- Significant bug discovered or resolved
- Security posture changed
- Performance characteristics changed
- Breaking changes introduced

### 4) Status Vocabulary (STRICT)

| Status | Meaning | When to Use |
|---|---|---|
| `Draft` | Initial creation, incomplete | New docs being written |
| `Active` | Current, in use, maintained | Most docs |
| `Stable` | Mature, rarely changes | Well-established code |
| `Needs Review` | Requires verification | After major changes |
| `Deprecated` | Being phased out | Scheduled for removal |
| `Broken` | Known to be non-functional | Urgent fix needed |

### 5) Bugs & Risks Vocabulary (STRICT)

**Severity Levels:**
| Level | Meaning | Response Time |
|---|---|---|
| `S0` | Critical - system unusable | Immediate |
| `S1` | High - major feature broken | Same day |
| `S2` | Medium - workaround exists | This week |
| `S3` | Low - minor inconvenience | When convenient |

**Confidence Levels:**
| Level | Meaning | Evidence Required |
|---|---|---|
| `Confirmed` | Reproduced, verified | Repro steps, logs |
| `Suspected` | Strong evidence | Stack trace, user reports |
| `Hypothesis` | Theoretical | Code analysis, gut feeling |

---

## Session Continuity Protocol (CRITICAL)

Every agent session MUST append a run-log entry in this file before ending.

### Session Start Checklist
- [ ] Read latest Agent Run Log entry (if exists)
- [ ] Review vault index for gaps
- [ ] Identify incomplete documentation
- [ ] Plan session scope
- [ ] Log session start in Agent Run Log

### Session End Checklist
- [ ] Update all touched documentation
- [ ] Append Agent Run Log entry
- [ ] Log session in Agent Run Log
- [ ] Verify all files in registry
- [ ] Document any blockers for next session

### Required Run Log Entry Fields
| Section | Content |
|---|---|
| Session ID | Unique identifier |
| Date | Session date |
| Agent/Model | What agent ran |
| What was done | Specific accomplishments |
| What was NOT done | Deferred items with reasons |
| Blockers encountered | Issues that prevented progress |
| Recommendations | Suggestions for next session |
| Files touched | List of all modified files |
| Files that need work | Priority list for next session |

---

## Agent Run Log (Fill Per Session)

| Run ID | Date (YYYY-MM-DD) | Agent/Model | Scope (what you touched) | Outcome | Notes |
|---|---|---|---|---|---|
| RUN-0001 | 2026-01-15 | AI Agent | vault-intro.md expansion | Completed | Initial comprehensive expansion |
| RUN-0002 | 2026-01-18 | AI Agent (Codex) | IPC parsing, ping handling, schema/test alignment, fixture docs, UI streaming cursor | Completed | Bug fixes + vault updates |
| RUN-0003 | 2026-01-18 | AI Agent (Codex) | Dependency version refresh, pyproject/Package.swift/README updates, vault registry updates | Completed | Updated dependency baselines and documentation |
| RUN-0004 | 2026-01-18 | AI Agent (Codex) | UI enhancement plan implementation + vault updates | Completed | Smooth drag snapping, animation standardization, streaming debounce |
| RUN-0005 | 2026-01-18 | AI Agent (Codex) | UI build warnings fixes + test path updates + vault sync | Completed | Fixed SwiftUI accessibility hint, onChange deprecations, SPM test path warning |
| RUN-0006 | 2026-02-08 | AI Agent (Codex) | Plan Mode/unified-planning/startup/test baseline documentation + knowledge graph refresh | Completed | Synced docs to current codebase state and recorded latest passing test baselines |

---

## Enforcement Mechanisms

### Self-Check Questions (Ask Before Ending Session)

1. **Completeness Check**: Have I documented EVERY file I touched?
2. **Registry Check**: Are all files in the change-history-index.md?
3. **Metadata Check**: Does every doc have Last Edited, Modified By, WHY filled?
4. **Handoff Check**: Did I create a session handoff for the next agent?
5. **Gap Check**: Did I identify and document any gaps I found but couldn't fix?

### Red Flags (Stop and Fix)
- Empty or placeholder sections in documentation
- Files in codebase not in registry
- Missing "WHY" explanations
- Status still showing "Draft" after work is complete
- No session handoff document

### Quality Gates
| Gate | Requirement | Failure Action |
|---|---|---|
| Pre-commit | All touched files documented | Block commit |
| Session end | Handoff document created | Block session end |
| Weekly audit | No files missing from registry | Create missing docs |
| Monthly review | All "Draft" statuses resolved | Escalate for review |

---

## Definition of Done (Per Update)

You are done **ONLY** when ALL of the following are true:

### Documentation Completeness
- [ ] Every file in the project is present in `change-history-index.md` registry
- [ ] Every code file has a matching `files/*.md` doc
- [ ] Every doc has ALL metadata tables filled (no empty cells)
- [ ] Every change has WHY + Modified by
- [ ] Known/suspected bugs are logged with severity and confidence

### Quality Standards
- [ ] No placeholder text remains
- [ ] All public symbols are documented
- [ ] Dependencies are listed with risk assessment
- [ ] Testing gaps are identified
- [ ] Security considerations are documented

### Session Hygiene
- [ ] Agent Run Log updated
- [ ] Session handoff document created
- [ ] Next steps clearly documented
- [ ] Blockers clearly documented

---

## Anti-Patterns (AVOID)

| Anti-Pattern | Why It's Bad | What To Do Instead |
|---|---|---|
| "Self-explanatory code" | Future context is lost | Document anyway |
| "Will document later" | Later never comes | Document now |
| "Only important files" | All files matter | Document all |
| "Copy-paste same doc" | Masks real differences | Customize per file |
| "Just the happy path" | Errors are critical | Document all paths |
| "Obvious dependencies" | Nothing is obvious later | List everything |
| "Anyone can figure it out" | Not true across time | Be explicit |

---

## Major Edits Log (Append-Only)

| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-15 | AI Agent | Comprehensive expansion for thorough documentation | Added detailed checklists, enforcement mechanisms, anti-patterns, session handoff protocol | High - establishes complete agent documentation standards |
