# File Doc: `ui/AIAgentUI/IPC/BackendLauncher.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | personal-macos-ai-agent |
| Code File Path | `ui/AIAgentUI/IPC/BackendLauncher.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/IPC/BackendLauncher.swift.md` |
| Language | Swift 6 |
| File Role | networking |
| Ownership | @individual-developer |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Claude) |
| WHY (Reason for last change) | Swift 6 concurrency fixes: @MainActor isolation, ProcessRef wrapper with NSLock |
| Lines of Code (LOC) | 423 |
| Cyclomatic Complexity | Medium |
| Test Coverage | 0% (UI component) |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:** Manages the lifecycle of the Python backend process, including spawning, monitoring output, and graceful termination.

**Detailed responsibilities:**
- Finds the Python environment (venv, Poetry, or system Python)
- Locates the project root by searching for `pyproject.toml`
- Spawns the Python backend with `--server` flag for IPC mode
- Monitors stdout/stderr from the backend process
- Detects when the backend server is ready via log parsing
- Manages socket path for Unix domain socket IPC
- Provides graceful and forced termination of the backend

### What this file must NOT do (boundaries)
**Out of scope:**
- Does NOT handle the actual IPC communication (see `SocketManager.swift`)
- Does NOT parse IPC messages (see `IPCClient.swift`, `MessageProtocol.swift`)
- Does NOT manage UI state directly (see `AppState.swift`)
- Does NOT implement the backend server logic (Python code)

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| `AppState.swift` | Start backend on app launch | Once per app lifecycle | Updates startup phase to `.failed` |
| `StartupModal.swift` | Displays backend startup progress | Observes state changes | Shows error message |
| `AppDelegate.swift` | Terminates backend on app quit | Once on app termination | Fire-and-forget |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
| `Foundation.Process` | Spawns Python subprocess | Catches launch errors | Returns `.failure` result |
| `Foundation.FileManager` | Checks for files/directories | N/A | Tries fallback paths |
| `Foundation.Pipe` | Captures stdout/stderr | N/A | Logs to console |

---

## Imports / Dependencies

### Internal Dependencies
| Import Path | What's Used | Why Needed | Coupling Level | Risk/Notes |
|---|---|---|---|---|
| None | - | Self-contained | None | - |

### External Dependencies
| Package | Version | License | What's Used | Why Needed | Security Risk | Alternatives |
|---|---|---|---|---|---|---|
| Foundation | System | Apple | Process, Pipe, FileManager, URL | Process management, file operations | Low | None |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `BackendLauncher` | class | internal (default) | Stable | Main class for backend process management |
| `BackendLauncher.State` | enum | internal | Stable | State machine for launcher lifecycle |
| `ProcessRef` | class | internal | Stable | Thread-safe Process wrapper |
| `BackendError` | enum | internal | Stable | Error types for backend operations |

---

## Types (Classes / Structs / Enums / Interfaces)

### `BackendLauncher`
| Metadata | Value |
|---|---|
| Kind | class |
| Purpose | Manages Python backend process lifecycle |
| Thread-Safe | Yes (@MainActor isolated) |
| Immutable | No |
| Serializable | No |
| Related Types | `BackendLauncher.State`, `ProcessRef`, `BackendError` |

#### Inheritance & Implementation
- **Extends:** None
- **Implements:** None
- **Used By:** `AppState`, `StartupModal`
- **Polymorphic Behavior:** None

#### Invariants & Constraints
| Invariant | Enforcement | Violation Consequences |
|---|---|---|
| State transitions follow state machine | Runtime | Ignores invalid transitions |
| Only one process at a time | Logic in `start()` | Early return if already running |

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `state` | `State` | private(set) | `.notStarted` | Yes | Yes | Current launcher state | N/A | Published via callback |
| `processRef` | `ProcessRef?` | private | `nil` | No | Yes | Reference to running process | N/A | Wrapped for thread safety |
| `socketPath` | `String?` | private(set) | `nil` | No | Yes | Unix socket path | N/A | Set after process starts |
| `onStateChange` | closure | public | `nil` | No | Yes | State change callback | N/A | `@MainActor @Sendable` |
| `onServerReady` | closure | public | `nil` | No | Yes | Server ready callback | N/A | Passes socket path |
| `onLogOutput` | closure | public | `nil` | No | Yes | Stdout callback | N/A | For debugging |
| `onErrorOutput` | closure | public | `nil` | No | Yes | Stderr callback | N/A | For debugging |

#### Methods
| Method | Signature | Visibility | Parameters | Returns | Throws/Errors | Side Effects | Thread-Safe | Complexity | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `start` | `func start(customSocketPath: String?) async throws` | public | Optional socket path | Void | `BackendError` | Spawns process | Yes | O(1) | Main entry point |
| `terminate` | `func terminate()` | public | None | Void | None | Kills process | Yes | O(1) | Graceful shutdown |
| `isRunning` | `var isRunning: Bool` | public | N/A | Bool | None | None | Yes | O(1) | Computed property |
| `findPythonEnvironment` | `private nonisolated func` | private | None | Tuple | `BackendError` | File I/O | Yes | O(n) | Searches directories |
| `findPoetryPython` | `private nonisolated func` | private | projectPath | String? | None | Runs `poetry` | Yes | O(1) | Poetry venv lookup |
| `waitForSocket` | `private func` | private | path, timeout | Void | None | File I/O | Yes | O(n) | Polls for socket file |

### `BackendLauncher.State`
| Metadata | Value |
|---|---|
| Kind | enum |
| Purpose | Represents backend launcher state machine |
| Thread-Safe | Yes (Sendable) |
| Immutable | Yes |
| Serializable | No |
| Related Types | `BackendLauncher` |

#### Cases
| Case | Associated Values | Meaning |
|---|---|---|
| `.notStarted` | None | Initial state |
| `.starting` | None | Process being launched |
| `.running(pid:)` | `Int32` | Process running with PID |
| `.failed(_:)` | `String` | Launch failed with error message |
| `.terminated` | None | Process exited normally |

### `ProcessRef`
| Metadata | Value |
|---|---|
| Kind | class |
| Purpose | Thread-safe wrapper for Foundation.Process |
| Thread-Safe | Yes (@unchecked Sendable with NSLock) |
| Immutable | No |
| Serializable | No |
| Related Types | `BackendLauncher` |

#### Invariants & Constraints
| Invariant | Enforcement | Violation Consequences |
|---|---|---|
| Lock must be held when accessing `process` | Manual with NSLock | Data race |
| Callbacks captured before closure execution | Code structure | Avoids actor isolation issues |

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `process` | `Process?` | internal | `nil` | No | Yes | The actual Process | N/A | Protected by lock |
| `outputPipe` | `Pipe?` | internal | `nil` | No | Yes | Stdout pipe | N/A | For output capture |
| `errorPipe` | `Pipe?` | internal | `nil` | No | Yes | Stderr pipe | N/A | For error capture |
| `lock` | `NSLock` | private | `NSLock()` | Yes | No | Thread safety | N/A | Protects process access |
| `onTermination` | closure | internal | `nil` | No | Yes | Termination callback | N/A | `@Sendable` |
| `onOutput` | closure | internal | `nil` | No | Yes | Output callback | N/A | `@Sendable` |
| `onError` | closure | internal | `nil` | No | Yes | Error callback | N/A | `@Sendable` |

#### Methods
| Method | Signature | Visibility | Parameters | Returns | Throws/Errors | Side Effects | Thread-Safe | Complexity | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `startProcess` | `func startProcess(...) async -> Result<Int32, Error>` | internal | pythonPath, projectPath, arguments | Result | None | Spawns process | Yes | O(1) | Async, runs on background thread |
| `terminateSync` | `func terminateSync()` | internal | None | Void | None | Kills process | Yes | O(1) | Synchronous, blocks up to 2s |
| `isRunning` | `var isRunning: Bool` | internal | N/A | Bool | None | None | Yes | O(1) | Lock-protected |

### `BackendError`
| Metadata | Value |
|---|---|
| Kind | enum |
| Purpose | Error types for backend operations |
| Thread-Safe | Yes (Sendable) |
| Immutable | Yes |
| Serializable | No |
| Related Types | `BackendLauncher` |

#### Cases
| Case | Associated Values | Error Description |
|---|---|---|
| `.projectNotFound` | None | "Could not find project root (pyproject.toml)" |
| `.pythonNotFound` | None | "Could not find Python interpreter" |
| `.launchFailed(_:)` | `String` | "Failed to start backend: {reason}" |
| `.socketTimeout` | None | "Backend server did not start in time" |

---

## Concurrency & Threading

### Concurrency Model
- **Thread Safety:** Thread-safe via `@MainActor` isolation for `BackendLauncher`
- **Synchronization Primitives:** `NSLock` in `ProcessRef` for cross-thread access
- **Async Patterns:** `async/await` for `start()`, `withCheckedContinuation` for bridging to callbacks

### Swift 6 Concurrency Patterns
| Pattern | Location | Purpose |
|---|---|---|
| `@MainActor` | `BackendLauncher` class | All UI-related callbacks stay on main thread |
| `@unchecked Sendable` | `ProcessRef` class | Manual thread safety with NSLock |
| `@MainActor @Sendable` | Callback types | Callbacks can cross isolation boundaries |
| `nonisolated` | `init()`, `findPythonEnvironment()` | Allow synchronous calls from any context |
| Callback capture before closure | `startProcess()` | Avoid capturing `self` in `@Sendable` closures |

### Potential Race Conditions
| Location | Description | Likelihood | Mitigation | Status |
|---|---|---|---|---|
| Process access | Multiple threads accessing Process | Low | NSLock in ProcessRef | Fixed |
| Callback invocation | Callbacks called from background thread | Low | Task { @MainActor } wrapper | Fixed |

---

## Performance Profile

### Performance Characteristics
| Metric | Value | Target | Acceptable Range |
|---|---|---|---|
| Process spawn time | ~100-500ms | <1s | <2s |
| Socket ready detection | ~200-500ms | <1s | <2s |
| Memory usage (running) | ~1MB | N/A | <5MB |

---

## Change History & Evolution

### File History
| Date | Change Type | Description | Impact | Modified By |
|---|---|---|---|---|
| 2026-01-18 | Created | Initial implementation | High | AI Agent (Claude) |
| 2026-01-18 | Refactored | Swift 6 concurrency fixes | High | AI Agent (Claude) |

### Swift 6 Concurrency Migration
| Before | After | Reason |
|---|---|---|
| Class without isolation | `@MainActor final class` | All UI callbacks on main thread |
| Direct Process access | `ProcessRef` wrapper | Thread-safe cross-isolation access |
| Capturing `self` in closures | Capture callbacks as `let` | Avoid actor-isolated capture in `@Sendable` |
| Inline callback handling | `Task { @MainActor in }` | Proper actor hop for UI updates |

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `ui/AIAgentUI/IPC/SocketManager.swift` | Uses | Connects to socket path from launcher |
| `ui/AIAgentUI/IPC/IPCClient.swift` | Uses | Uses socket manager to communicate |
| `ui/AIAgentUI/State/AppState.swift` | Used by | Manages launcher lifecycle |
| `ui/AIAgentUI/Views/Components/StartupModal.swift` | Used by | Displays launcher state |
| `agent_host/main.py` | Launches | The Python backend being spawned |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Agent (Claude) | Initial creation | Created BackendLauncher for Python process management | High |
| 2026-01-18 | AI Agent (Claude) | Swift 6 concurrency | Added @MainActor, ProcessRef, fixed Sendable issues | High |
