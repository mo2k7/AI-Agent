"""Policy-level tests for unified-planning privacy boundaries."""

from __future__ import annotations

import socket
import threading

import pytest

from agent_host.planning.unified_planner import (
    UnifiedPlanningEngine,
    UnifiedPlanningSecurityError,
)


def _engine_for_policy_tests() -> UnifiedPlanningEngine:
    # Bypass __init__ to avoid requiring installed unified-planning in policy tests.
    return UnifiedPlanningEngine.__new__(UnifiedPlanningEngine)


def test_assert_no_text_payload_accepts_numeric_boolean_structures() -> None:
    engine = _engine_for_policy_tests()
    engine._assert_no_text_payload(1)
    engine._assert_no_text_payload(True)
    engine._assert_no_text_payload([(0, 1, True), (1, 4, False)])
    engine._assert_no_text_payload({1: (2, 3), 4: [5, 6, False]})


@pytest.mark.parametrize(
    "value",
    [
        "/Users/name/secret.txt",
        "../private.txt",
        "C:\\Users\\name\\Desktop\\secret.txt",
        "\\\\server\\share\\a.txt",
        "file:///Users/name/token.txt",
        "%2FUsers%2Fname%2Fsecret.txt",
        "L1VzZXJzL25hbWUvc2VjcmV0LnR4dA==",
        "dir\u200b/hidden.txt",
        "name\x00hidden.txt",
        b"/Users/name/secret.txt",
        bytearray(b"secret"),
        memoryview(b"secret"),
        None,
        1.25,
    ],
)
def test_assert_no_text_payload_rejects_sensitive_or_non_numeric_values(value: object) -> None:
    engine = _engine_for_policy_tests()
    with pytest.raises(UnifiedPlanningSecurityError):
        engine._assert_no_text_payload(value)


def test_normalize_abstract_steps_requires_strict_tuple_shapes_and_types() -> None:
    engine = _engine_for_policy_tests()
    with pytest.raises(UnifiedPlanningSecurityError, match="Invalid abstract step payload"):
        engine._normalize_abstract_steps([(0, 1)])  # type: ignore[list-item]
    with pytest.raises(UnifiedPlanningSecurityError, match="Invalid step identifier"):
        engine._normalize_abstract_steps([(-1, 1, True)])
    with pytest.raises(UnifiedPlanningSecurityError, match="Invalid op code"):
        engine._normalize_abstract_steps([(0, True, True)])  # bool is not allowed for op_code
    with pytest.raises(UnifiedPlanningSecurityError, match="Out-of-range op code"):
        engine._normalize_abstract_steps([(0, 100, True)])
    with pytest.raises(UnifiedPlanningSecurityError, match="Invalid step validity flag"):
        engine._normalize_abstract_steps([(0, 1, 1)])  # bool required


def test_analyze_complexity_requires_integer_dependency_count() -> None:
    engine = _engine_for_policy_tests()
    with pytest.raises(UnifiedPlanningSecurityError, match="dependency_count must be an integer"):
        engine.analyze_complexity(steps=[(0, 1, True)], dependency_count="1")  # type: ignore[arg-type]


def test_plan_order_rejects_self_dependency() -> None:
    engine = _engine_for_policy_tests()
    engine.version = "test"
    with pytest.raises(UnifiedPlanningSecurityError, match="Self-dependencies"):
        engine.plan_order(step_count=1, dependencies=[(0, 0)])


def test_policy_checksum_matches_expected_constant() -> None:
    engine = _engine_for_policy_tests()
    computed = engine._compute_policy_checksum()
    assert computed == UnifiedPlanningEngine._POLICY_ATTESTATION_CHECKSUM


def test_network_guard_is_thread_scoped_not_process_global() -> None:
    engine = _engine_for_policy_tests()
    inside_ready = threading.Event()
    release_inside = threading.Event()
    outside_error: list[Exception] = []

    def _inside_guard() -> None:
        with engine._network_guard():
            inside_ready.set()
            with pytest.raises(UnifiedPlanningSecurityError):
                socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            release_inside.wait(timeout=2.0)

    def _outside_guard() -> None:
        inside_ready.wait(timeout=2.0)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.close()
        except Exception as exc:  # pragma: no cover - assertion guard
            outside_error.append(exc)
        finally:
            release_inside.set()

    t_inside = threading.Thread(target=_inside_guard)
    t_outside = threading.Thread(target=_outside_guard)
    t_inside.start()
    t_outside.start()
    t_inside.join(timeout=3.0)
    t_outside.join(timeout=3.0)

    assert not t_inside.is_alive()
    assert not t_outside.is_alive()
    assert not outside_error


def test_verify_policy_attestation_rejects_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine_for_policy_tests()
    engine.policy_checksum = "0" * 64
    monkeypatch.setattr(
        UnifiedPlanningEngine,
        "_POLICY_ATTESTATION_CHECKSUM",
        "f" * 64,
    )
    with pytest.raises(UnifiedPlanningSecurityError, match="policy checksum attestation failed"):
        engine._verify_policy_attestation()


def test_verify_package_hash_pin_accepts_match(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine_for_policy_tests()
    pinned = "a" * 64
    monkeypatch.setenv(UnifiedPlanningEngine._HASH_PIN_ENV_VAR, pinned)
    assert engine._verify_package_hash_pin(pinned) is True


def test_verify_package_hash_pin_accepts_comma_separated_rotations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _engine_for_policy_tests()
    old_hash = "a" * 64
    new_hash = "b" * 64
    monkeypatch.setenv(
        UnifiedPlanningEngine._HASH_PIN_ENV_VAR,
        f"{old_hash}, {new_hash}",
    )
    assert engine._verify_package_hash_pin(new_hash) is True


def test_verify_package_hash_pin_rejects_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine_for_policy_tests()
    monkeypatch.setenv(UnifiedPlanningEngine._HASH_PIN_ENV_VAR, "a" * 64)
    with pytest.raises(UnifiedPlanningSecurityError, match="hash pin verification failed"):
        engine._verify_package_hash_pin("b" * 64)


def test_verify_package_hash_pin_rejects_invalid_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine_for_policy_tests()
    monkeypatch.setenv(UnifiedPlanningEngine._HASH_PIN_ENV_VAR, "not-a-hash")
    with pytest.raises(UnifiedPlanningSecurityError, match="SHA-256 hex digests"):
        engine._verify_package_hash_pin("a" * 64)


def test_verify_package_hash_pin_auto_rotate_requires_store_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _engine_for_policy_tests()
    monkeypatch.setenv(UnifiedPlanningEngine._HASH_PIN_AUTO_ROTATE_ENV_VAR, "true")
    monkeypatch.setenv(UnifiedPlanningEngine._HASH_PIN_ENV_VAR, "a" * 64)
    monkeypatch.delenv(UnifiedPlanningEngine._HASH_PIN_STORE_KEY_ENV_VAR, raising=False)
    with pytest.raises(UnifiedPlanningSecurityError, match="requires"):
        engine._verify_package_hash_pin("a" * 64)


def test_verify_package_hash_pin_auto_rotate_persists_signed_store(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    engine = _engine_for_policy_tests()
    store_path = tmp_path / "pins.json"
    current_hash = "a" * 64
    next_hash = "b" * 64
    monkeypatch.setenv(UnifiedPlanningEngine._HASH_PIN_AUTO_ROTATE_ENV_VAR, "true")
    monkeypatch.setenv(
        UnifiedPlanningEngine._HASH_PIN_ENV_VAR,
        f"{current_hash},{next_hash}",
    )
    monkeypatch.setenv(UnifiedPlanningEngine._HASH_PIN_STORE_KEY_ENV_VAR, "test-secret")
    monkeypatch.setenv(UnifiedPlanningEngine._HASH_PIN_STORE_ENV_VAR, str(store_path))
    monkeypatch.setenv(UnifiedPlanningEngine._HASH_PIN_MAX_HISTORY_ENV_VAR, "3")

    assert engine._verify_package_hash_pin(current_hash) is True
    assert store_path.exists()

    # Verify store-backed pinning works even after env allowlist is removed.
    monkeypatch.setenv(UnifiedPlanningEngine._HASH_PIN_ENV_VAR, "")
    assert engine._verify_package_hash_pin(current_hash) is True


def test_verify_package_hash_pin_auto_rotate_rejects_tampered_store(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    engine = _engine_for_policy_tests()
    store_path = tmp_path / "pins.json"
    current_hash = "a" * 64
    monkeypatch.setenv(UnifiedPlanningEngine._HASH_PIN_AUTO_ROTATE_ENV_VAR, "true")
    monkeypatch.setenv(UnifiedPlanningEngine._HASH_PIN_ENV_VAR, current_hash)
    monkeypatch.setenv(UnifiedPlanningEngine._HASH_PIN_STORE_KEY_ENV_VAR, "test-secret")
    monkeypatch.setenv(UnifiedPlanningEngine._HASH_PIN_STORE_ENV_VAR, str(store_path))

    assert engine._verify_package_hash_pin(current_hash) is True

    payload = store_path.read_text(encoding="utf-8")
    store_path.write_text(payload.replace(current_hash, "b" * 64), encoding="utf-8")

    monkeypatch.setenv(UnifiedPlanningEngine._HASH_PIN_ENV_VAR, "")
    with pytest.raises(UnifiedPlanningSecurityError, match="signature verification failed"):
        engine._verify_package_hash_pin(current_hash)
