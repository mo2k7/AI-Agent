# Live Debug Harness

## One command (full stack)

```bash
bash scripts/run_all.sh --duration 30 --concurrency 20
```

This command:

1. Creates `artifacts/<run-id>/`
2. Starts backend in debug mode
3. Starts frontend in debug mode
4. Starts macOS unified log stream capture
5. Runs deterministic RPC stress harness
6. Auto-captures a repro on failure
7. Cleans up child processes and prints artifact paths

## Backend + stress only

```bash
bash scripts/run_all.sh --duration 20 --concurrency 10 --skip-frontend
```

## Replay a captured failure

```bash
poetry run python scripts/repro_replay.py --replay artifacts/<run-id>/replay_00.json --socket-path /tmp/<socket>.sock --bisect
```

## Useful direct commands

```bash
# Initialize env + run metadata
bash scripts/dev_env.sh

# Backend only (foreground)
bash scripts/run_backend.sh

# Frontend only (foreground)
bash scripts/run_frontend.sh

# System log stream only
bash scripts/log_stream.sh

# Stress only
poetry run python scripts/stress_rpc.py --socket-path "$AI_AGENT_SOCKET_PATH" --duration 10 --concurrency 10 --seed 1337 --run-dir "$AI_AGENT_RUN_DIR"
```

## Artifacts

Each run writes to `artifacts/<run-id>/`:

- `env.snapshot`: effective debug env vars
- `backend.log`: backend output + structured JSON logs
- `frontend.log`: frontend stdout/stderr + debug logs
- `system.log`: macOS unified logs (`log stream`)
- `protocol_trace.jsonl`: redacted inbound/outbound JSON-RPC trace (when enabled)
- `stress_events.jsonl`: per-operation stress events
- `stress_report.json`: summary and first failing sequence
- `replay_*.json`: captured replay sequence (on failure)
- `REPRO.txt`: ready-to-run replay command (on failure)

## Troubleshooting

### Socket path exists / permission issue

- Symptom: backend fails to bind socket or frontend cannot connect.
- Fix:
  - confirm path is under `/tmp`
  - ensure no stale process owns it
  - rerun harness (backend script removes stale socket before start)

### Handshake failures

- Symptom: frontend starts but health check fails.
- Check:
  - `backend.log` for startup and IPC errors
  - `frontend.log` for socket path used and connection state transitions
  - `protocol_trace.jsonl` for request/response mismatches

### DB locked / contention

- Symptom: intermittent session/memory failures under load.
- Check:
  - `backend.log` events `sqlite_locked_or_busy_retry` and `sqlite_metrics`
  - retry counts and histogram spikes in `sqlite_metrics`

### Frontend stuck waiting

- Symptom: pending UI state without completion.
- Check:
  - frontend `request_complete` events with `duration_ms`
  - backend `rpc_message_complete` / timeout events
  - `protocol_trace.jsonl` for missing terminal messages
