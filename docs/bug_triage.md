# Bug Triage Workflow

## 1. Capture evidence

Run:

```bash
bash scripts/run_all.sh --duration 10 --concurrency 10
```

If failure occurs, collect:

- `artifacts/<run-id>/stress_report.json`
- `artifacts/<run-id>/replay_00.json` (or first replay file)
- `artifacts/<run-id>/backend.log`
- `artifacts/<run-id>/frontend.log`
- `artifacts/<run-id>/protocol_trace.jsonl`

## 2. Reproduce deterministically

Use the generated command:

```bash
cat artifacts/<run-id>/REPRO.txt
```

Or run directly:

```bash
poetry run python scripts/repro_replay.py --replay artifacts/<run-id>/replay_00.json --socket-path /tmp/<socket>.sock --bisect
```

## 3. Minimize the repro

1. Use `--bisect` to locate first failing step.
2. Build a focused unit/integration test that asserts the failing behavior.
3. Store details in a regression test using `tests/regression/REPRO_REGRESSION_TEMPLATE.md`.

## 4. Implement and verify fix

A fix is only considered complete when all pass:

1. Repro replay passes:
   - `poetry run python scripts/repro_replay.py --replay ... --socket-path ...`
2. Full Python suite passes:
   - `poetry run pytest -q`
3. Full harness smoke passes:
   - `bash scripts/run_all.sh --duration 10 --concurrency 10`
4. Frontend tests pass:
   - `swift test --package-path ui`

## 5. Confirmation rules

Do not close a bug until:

- deterministic replay no longer fails
- no new failures in harness artifacts
- no regressions in backend or frontend tests
