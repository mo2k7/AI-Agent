# Regression Test Template From Repro

Use this template when a harness replay (`replay_*.json`) finds a bug.

## Checklist

1. Copy the failing replay file into `artifacts/<run>/`.
2. Reproduce with:
   - `poetry run python scripts/repro_replay.py --replay <replay.json> --socket-path <socket> --bisect`
3. Create a focused unit/integration test near the affected subsystem.
4. Assert the exact failure mode before the fix.
5. Apply fix and update the test to assert correct behavior.
6. Re-run:
   - `poetry run pytest -q`
   - `bash scripts/run_all.sh --duration 10 --concurrency 10`

## Python Test Skeleton

```python
def test_regression_<bug_slug>() -> None:
    # Arrange
    # - build request sequence from repro
    # Act
    # - execute sequence
    # Assert
    # - verify bug no longer reproduces
```

## Swift Test Skeleton

```swift
@Test
func regression_<bug_slug>() async throws {
    // Arrange
    // Act
    // Assert
}
```
