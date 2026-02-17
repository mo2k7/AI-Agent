# Regression Bug Matrix (2026-02-07)

Scope: IPC, prompt lifecycle, cancellation, session switching, memory load failure handling, tool-call flow.

## Matrix

| Area | Scenario | Status | Severity | Evidence |
|---|---|---|---|---|
| IPC lifecycle | Duplicate in-flight prompt request id | Not reproducible (guarded) | Medium | `tests/unit/test_ipc_regression_flows.py::test_rejects_duplicate_inflight_request_ids` |
| Cancellation | Cancel-all without `request_id` across concurrent prompts | Not reproducible (works) | High | `tests/unit/test_ipc_regression_flows.py::test_cancel_without_request_id_cancels_all_client_prompts` |
| Payload hardening | `prompt.params` malformed type (`list`) | Not reproducible (clean invalid request error) | Medium | `tests/unit/test_ipc_regression_flows.py::test_malformed_prompt_params_type_returns_invalid_request` |
| Payload hardening | Invalid UTF-8 transport payload | Not reproducible (parse error emitted) | High | `tests/unit/test_ipc_regression_flows.py::test_invalid_utf8_payload_returns_parse_error` |
| Request throughput | Rapid repeated sends (12 prompt requests back-to-back) | Not reproducible (all complete) | High | `tests/unit/test_ipc_regression_flows.py::test_rapid_repeated_sends_complete_all_requests` |
| Session switching | Rapid session A/B switching and transcript isolation | Not reproducible (isolated) | High | `tests/unit/test_ipc_regression_flows.py::test_rapid_session_switching_keeps_histories_isolated` |
| Tool-call flow | Schema-invalid tool call terminal sequence (`tool_call failed` + `error` + `complete`) | Not reproducible (UI-compatible flow present) | High | `tests/unit/test_ipc_regression_flows.py::test_tool_validation_failure_emits_ui_compatible_terminal_sequence` |
| Tool-call flow | Successful tool execution includes `result.content` + `result.tool_calls` | Not reproducible (present) | High | `tests/unit/test_ipc_regression_flows.py::test_tool_success_result_includes_tool_calls_payload_for_ui` |
| Memory load failures | Corrupted session DB quarantine and continued interaction | Not reproducible (self-heals) | High | `tests/unit/test_memory_regression_failures.py::test_corrupted_session_db_is_quarantined_and_interactions_continue` |
| Memory load failures | Corrupted index DB quarantine + session metadata restore | Not reproducible (self-heals) | High | `tests/unit/test_memory_regression_failures.py::test_corrupted_index_db_is_quarantined_on_reinit` |
| Memory resilience | Corrupted message row handling in session history | Not reproducible (bad row skipped, history survives) | Medium | `tests/unit/test_memory_regression_failures.py::test_manager_history_listing_survives_corrupted_message_rows` |

## Notes from validation runs

- New regression suites pass:
  - `./.venv/bin/python -m pytest -q tests/unit/test_ipc_regression_flows.py tests/unit/test_memory_regression_failures.py`
- Full Python suite currently fails in pre-existing tests outside this change scope:
  - `tests/unit/test_memory_store.py::test_index_schema_self_heals_when_index_file_is_recreated_empty`
  - `tests/unit/test_memory_store.py::test_index_schema_self_heals_when_sessions_table_is_missing`
- Failure shape: current storage behavior restores session metadata from per-session DBs, while those tests expect an empty index result.

## Deferred Swift checks (integration-stable run)

Run after concurrent UI production edits stabilize:

1. `cd ui && swift test --filter RegressionFlowTests`
2. `cd ui && swift test --filter MessageProtocolTests`
3. `cd ui && swift test --filter StreamingParserTests`
4. `cd ui && swift test --filter AgentStatusTests`
5. `cd ui && swift test` (full package)

