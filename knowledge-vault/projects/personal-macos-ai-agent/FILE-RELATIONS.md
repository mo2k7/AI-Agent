# File Relations Map

**Project:** Personal macOS AI Agent  
**Last Updated:** 2026-02-08  
**Purpose:** Current critical file-to-file relationships for runtime reliability, Plan Mode correctness, and startup/test stability.

## Core Runtime Relations
| From File | Relation | To File | Rationale |
|---|---|---|---|
| `agent_host/main.py` | orchestrates transport through | `agent_host/ipc/server.py` | Registers handlers and drives request lifecycle. |
| `agent_host/main.py` | emits protocol payloads from | `agent_host/ipc/protocol.py` | Builds status, result, and error messages. |
| `agent_host/main.py` | validates model tool calls through | `agent_host/schema_validator.py` | Rejects invalid tool payloads early. |
| `agent_host/main.py` | parses tool intents through | `agent_host/tool_parser.py` | Converts model output to executable tool calls. |
| `agent_host/main.py` | executes tools via | `agent_host/tools/executor.py` | Central execution gateway for all tool handlers. |
| `agent_host/tools/executor.py` | secures planner behavior with | `agent_host/planning/unified_planner.py` | Mandatory secure planning engine integration. |
| `agent_host/main.py` | scores plan clarification with | `agent_host/nlp/intent_classifier.py` | Dynamic confidence/scoring for clarification flow. |
| `agent_host/main.py` | records context via | `agent_host/memory/manager.py` | Session memory capture and retrieval.

## Plan Mode-Specific Relations
| From File | Relation | To File | Rationale |
|---|---|---|---|
| `agent_host/main.py` | constructs plan clarification text consumed by | `ui/AIAgentUI/Views/Components/ResponseBubble.swift` | UI parses Q/A structure into clickable options. |
| `agent_host/main.py` | suppresses planner tool cards in plan mode aligned with | `ui/AIAgentUI/State/AppState.swift` | Backend and frontend both gate planner card rendering. |
| `ui/AIAgentUI/State/AppState.swift` | tracks per-request mode in | `activePromptExecutionMode` | Ensures suppression logic matches actual request mode. |
| `agent_host/main.py` | injects unified-planning bootstrap context into | prompt sent to model | Keeps plan output query-aligned with complexity/privacy constraints. |

## Startup and Process Control Relations
| From File | Relation | To File | Rationale |
|---|---|---|---|
| `ui/AIAgentUI/App/AppDelegate.swift` | bootstrap re-exec launches | `scripts/start_latest_app.sh` | Ensures clean rebuild/start from latest code state. |
| `scripts/start_latest_app.sh` | starts backend via | `scripts/run_backend.sh` | Standardized backend launch sequence. |
| `scripts/run_backend.sh` | validates/installs required NLP model for | `agent_host/main.py` | Guarantees plan-mode NLP preload requirements are met. |

## UI Runtime Relations
| From File | Relation | To File | Rationale |
|---|---|---|---|
| `ui/AIAgentUI/State/AppState.swift` | drives transport through | `ui/AIAgentUI/IPC/IPCClient.swift` | State transitions originate from IPC callbacks/events. |
| `ui/AIAgentUI/IPC/IPCClient.swift` | sends bytes through | `ui/AIAgentUI/IPC/SocketManager.swift` | Socket manager handles NDJSON stream transport. |
| `ui/AIAgentUI/Views/MainPanelView.swift` | renders and triggers actions on | `ui/AIAgentUI/State/AppState.swift` | Main UI state binding surface. |
| `ui/AIAgentUI/Views/Components/ResponseBubble.swift` | submits clarification answers through | `ui/AIAgentUI/State/AppState.swift` | Structured response actions feed directly into prompt submission flow. |

## Test-to-Code Relations
| Test File | Validates | Focus |
|---|---|---|
| `tests/unit/test_main_verbosity.py` | `agent_host/main.py` | Plan-mode clarification behavior and profile signal handling. |
| `tests/unit/test_ipc_runtime.py` | `agent_host/main.py`, `agent_host/ipc/server.py` | Cancellation, error correlation, tool-chain depth behavior. |
| `tests/unit/test_memory_session_history_rpc_regression.py` | IPC runtime + session behavior | Plan-mode clarification regression coverage and fake-server stability. |
| `ui/Tests/AIAgentUITests/RegressionFlowTests.swift` | `AppState`/UI state flows | Runtime state and lifecycle regressions. |
| `ui/Tests/AIAgentUITests/ToolCallLifecycleStateTests.swift` | Tool-call state integration | Tool-call status transitions and UI lifecycle correctness. |

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-02-08 | AI Agent (Codex) | Codebase sync | Updated relation map for Plan Mode clarification pipeline, planner-card suppression path, unified-planning runtime integration, and bootstrap startup scripts | High |
| 2026-02-07 | AI Agent (Codex) | Reliability sync | Added memory/session and test-to-code relations | Medium |
