"""Secure Unified Planning integration for structured plan generation."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import threading
import time
from contextlib import contextmanager
from importlib import import_module
from importlib.metadata import PackageNotFoundError, metadata, version
from pathlib import Path
from typing import Any, ClassVar


class UnifiedPlanningUnavailableError(RuntimeError):
    """Raised when unified-planning is unavailable or unusable."""


class UnifiedPlanningSecurityError(RuntimeError):
    """Raised when unified-planning fails privacy/security requirements."""


class UnifiedPlanningEngine:
    """Thin secure wrapper around ``unified_planning`` for operation planning."""

    _ALLOWED_LICENSE_TOKENS = (
        "apache software license",
        "apache license 2.0",
        "apache-2.0",
    )
    _DESTRUCTIVE_OP_CODES = {1, 2, 3}
    _MAX_STEPS = 5000
    _MAX_DEPENDENCIES = 20000
    _HASH_PIN_ENV_VAR = "AI_AGENT_UNIFIED_PLANNING_HASH_PIN"
    _HASH_PIN_AUTO_ROTATE_ENV_VAR = "AI_AGENT_UNIFIED_PLANNING_HASH_PIN_AUTO_ROTATE"
    _HASH_PIN_STORE_ENV_VAR = "AI_AGENT_UNIFIED_PLANNING_HASH_PIN_STORE"
    _HASH_PIN_STORE_KEY_ENV_VAR = "AI_AGENT_UNIFIED_PLANNING_HASH_PIN_STORE_HMAC_KEY"
    _HASH_PIN_MAX_HISTORY_ENV_VAR = "AI_AGENT_UNIFIED_PLANNING_HASH_PIN_MAX_HISTORY"
    _HASH_PIN_STORE_DEFAULT_RELATIVE = Path(
        "Library/Application Support/AIAgent/security/unified_planning_hash_store.json"
    )
    _HASH_PIN_STORE_SCHEMA_VERSION = 1
    _HASH_PIN_STORE_MAX_BYTES = 64 * 1024
    _HASH_PIN_MAX_HISTORY_DEFAULT = 6
    _POLICY_ATTESTATION_SPEC = {
        "boundary_payload_mode": "numeric_boolean_only",
        "string_payload_allowed": False,
        "binary_payload_allowed": False,
        "none_payload_allowed": False,
        "float_payload_allowed": False,
        "allowed_scalar_types": ("int", "bool"),
        "allowed_container_types": ("list", "tuple", "set", "frozenset", "dict"),
        "max_steps": 5000,
        "max_dependencies": 20000,
        "self_dependencies_allowed": False,
        "network_blocked_primitives": (
            "socket.socket",
            "socket.socketpair",
            "socket.create_connection",
            "socket.getaddrinfo",
            "socket.gethostbyname",
        ),
    }
    _POLICY_ATTESTATION_CHECKSUM = "6ebc8926c1339034be94b15db427689fe2f60df9325236661222f274d4f77214"
    _NETWORK_GUARD_STATE: ClassVar[threading.local] = threading.local()
    _NETWORK_GUARD_HOOK_LOCK: ClassVar[threading.Lock] = threading.Lock()
    _NETWORK_GUARD_HOOK_INSTALLED: ClassVar[bool] = False

    def __init__(self) -> None:
        self._validate_license()
        self.version = version("unified-planning")
        try:
            shortcuts = import_module("unified_planning.shortcuts")
        except Exception as exc:  # pragma: no cover - import guard
            raise UnifiedPlanningUnavailableError(
                f"unified-planning import failed: {exc}"
            ) from exc

        self.policy_checksum = self._compute_policy_checksum()
        self.policy_attestation_verified = False
        self._verify_policy_attestation()
        self.policy_attestation_verified = True

        self.package_hash = self._compute_unified_planning_package_hash(shortcuts_module=shortcuts)
        self.package_hash_auto_rotate_enabled = False
        self.package_hash_pinned = self._verify_package_hash_pin(self.package_hash)
        self.package_hash_verified = True

        self._Problem = getattr(shortcuts, "Problem")
        self._Fluent = getattr(shortcuts, "Fluent")
        self._InstantaneousAction = getattr(shortcuts, "InstantaneousAction")
        self._OneshotPlanner = getattr(shortcuts, "OneshotPlanner")
        self._Not = getattr(shortcuts, "Not")

    @classmethod
    def _compute_policy_checksum(cls) -> str:
        payload = json.dumps(
            cls._POLICY_ATTESTATION_SPEC,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _verify_policy_attestation(self) -> None:
        if self.policy_checksum != self._POLICY_ATTESTATION_CHECKSUM:
            raise UnifiedPlanningSecurityError(
                "Planner policy checksum attestation failed; policy constants may have been tampered"
            )

    @staticmethod
    def _normalize_module_file_path(raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser().resolve(strict=False)
        if candidate.suffix == ".pyc":
            source_candidate = candidate.with_suffix(".py")
            if source_candidate.exists() and source_candidate.is_file():
                return source_candidate
        return candidate

    def _compute_unified_planning_package_hash(self, *, shortcuts_module: Any) -> str:
        try:
            root_module = import_module("unified_planning")
        except Exception as exc:  # pragma: no cover - import guard
            raise UnifiedPlanningUnavailableError(
                f"unified-planning root import failed during hash attestation: {exc}"
            ) from exc

        paths: list[Path] = []
        for module in (root_module, shortcuts_module):
            module_file = getattr(module, "__file__", None)
            if isinstance(module_file, str) and module_file.strip():
                paths.append(self._normalize_module_file_path(module_file))

        unique_paths = sorted({path for path in paths}, key=lambda item: str(item))
        if not unique_paths:
            raise UnifiedPlanningSecurityError(
                "unified-planning package hash attestation failed: no module files found"
            )

        digest = hashlib.sha256()
        digest.update(str(self.version).encode("utf-8"))
        digest.update(b"\0")
        for path in unique_paths:
            if not path.exists() or not path.is_file():
                raise UnifiedPlanningSecurityError(
                    f"unified-planning package hash attestation failed: missing module file {path}"
                )
            digest.update(str(path).encode("utf-8"))
            digest.update(b"\0")
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(65536), b""):
                    digest.update(chunk)
            digest.update(b"\0")

        return digest.hexdigest()

    def _verify_package_hash_pin(self, package_hash: str) -> bool:
        raw_pin = os.getenv(self._HASH_PIN_ENV_VAR, "").strip()
        env_tokens = self._parse_hash_pin_tokens(raw_pin)
        auto_rotate = self._parse_bool_env(
            os.getenv(self._HASH_PIN_AUTO_ROTATE_ENV_VAR),
            default=False,
        )
        self.package_hash_auto_rotate_enabled = auto_rotate

        store_tokens: list[str] = []
        store_key: bytes | None = None
        if auto_rotate:
            store_key = self._read_hash_store_key_bytes()
            store_tokens = self._load_signed_hash_store(store_key)

        # Explicit environment pins are authoritative and must not be widened
        # by store history. Store-backed tokens are only used when no env pins
        # are configured.
        allowed = set(env_tokens) if env_tokens else set(store_tokens)
        if not allowed:
            return False

        normalized_hash = package_hash.strip().lower()
        if normalized_hash not in allowed:
            raise UnifiedPlanningSecurityError(
                "unified-planning package hash pin verification failed"
            )

        if auto_rotate and store_key is not None:
            max_history = self._read_hash_pin_max_history()
            rotated_tokens = self._build_rotated_hash_tokens(
                current_hash=normalized_hash,
                env_tokens=env_tokens,
                store_tokens=store_tokens,
                max_history=max_history,
            )
            self._write_signed_hash_store(store_key, rotated_tokens)

        return True

    @staticmethod
    def _parse_bool_env(raw: str | None, *, default: bool) -> bool:
        if raw is None:
            return default
        value = raw.strip().lower()
        if not value:
            return default
        if value in {"1", "true", "yes", "on"}:
            return True
        if value in {"0", "false", "no", "off"}:
            return False
        raise UnifiedPlanningSecurityError(
            "Invalid boolean value for hash pin auto-rotation setting"
        )

    def _read_hash_pin_max_history(self) -> int:
        raw = os.getenv(self._HASH_PIN_MAX_HISTORY_ENV_VAR, "").strip()
        if not raw:
            return self._HASH_PIN_MAX_HISTORY_DEFAULT
        try:
            parsed = int(raw)
        except ValueError as exc:
            raise UnifiedPlanningSecurityError(
                f"{self._HASH_PIN_MAX_HISTORY_ENV_VAR} must be an integer"
            ) from exc
        if parsed < 2 or parsed > 32:
            raise UnifiedPlanningSecurityError(
                f"{self._HASH_PIN_MAX_HISTORY_ENV_VAR} must be between 2 and 32"
            )
        return parsed

    def _resolve_hash_store_path(self) -> Path:
        raw = os.getenv(self._HASH_PIN_STORE_ENV_VAR, "").strip()
        if raw:
            candidate = Path(raw).expanduser().resolve(strict=False)
        else:
            candidate = (Path.home() / self._HASH_PIN_STORE_DEFAULT_RELATIVE).expanduser().resolve(
                strict=False
            )
        return candidate

    @staticmethod
    def _parse_hash_pin_tokens(raw_pin: str) -> list[str]:
        if not raw_pin:
            return []
        tokens = [item.strip().lower() for item in raw_pin.split(",") if item.strip()]
        if not tokens:
            raise UnifiedPlanningSecurityError(
                f"{UnifiedPlanningEngine._HASH_PIN_ENV_VAR} is set but contains no valid hash entries"
            )
        if any(len(token) != 64 or any(ch not in "0123456789abcdef" for ch in token) for token in tokens):
            raise UnifiedPlanningSecurityError(
                f"{UnifiedPlanningEngine._HASH_PIN_ENV_VAR} must contain comma-separated SHA-256 hex digests"
            )
        return tokens

    def _read_hash_store_key_bytes(self) -> bytes:
        raw = os.getenv(self._HASH_PIN_STORE_KEY_ENV_VAR, "").strip()
        if not raw:
            raise UnifiedPlanningSecurityError(
                f"{self._HASH_PIN_AUTO_ROTATE_ENV_VAR}=true requires {self._HASH_PIN_STORE_KEY_ENV_VAR}"
            )
        return raw.encode("utf-8")

    @staticmethod
    def _canonical_store_payload(payload: dict[str, Any]) -> bytes:
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def _sign_hash_store_payload(self, payload: dict[str, Any], key: bytes) -> str:
        return hmac.new(key, self._canonical_store_payload(payload), hashlib.sha256).hexdigest()

    def _verify_hash_store_signature(self, payload: dict[str, Any], signature: str, key: bytes) -> bool:
        expected = self._sign_hash_store_payload(payload, key)
        return hmac.compare_digest(expected, signature)

    def _load_signed_hash_store(self, key: bytes) -> list[str]:
        path = self._resolve_hash_store_path()
        if not path.exists():
            return []
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise UnifiedPlanningSecurityError(
                f"Unable to read hash pin store: {exc}"
            ) from exc
        if len(raw) > self._HASH_PIN_STORE_MAX_BYTES:
            raise UnifiedPlanningSecurityError("Hash pin store exceeds maximum allowed size")
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise UnifiedPlanningSecurityError(
                "Hash pin store is not valid JSON"
            ) from exc
        if not isinstance(decoded, dict):
            raise UnifiedPlanningSecurityError("Hash pin store JSON root must be an object")

        signature = decoded.get("signature")
        if not isinstance(signature, str) or not signature:
            raise UnifiedPlanningSecurityError("Hash pin store signature is missing")

        version_value = decoded.get("version")
        updated_at = decoded.get("updated_at")
        hashes = decoded.get("hashes")
        if version_value != self._HASH_PIN_STORE_SCHEMA_VERSION:
            raise UnifiedPlanningSecurityError("Hash pin store schema version is invalid")
        if not isinstance(updated_at, int) or updated_at < 0:
            raise UnifiedPlanningSecurityError("Hash pin store updated_at is invalid")
        if not isinstance(hashes, list):
            raise UnifiedPlanningSecurityError("Hash pin store hashes field must be a list")

        normalized_hashes: list[str] = []
        for item in hashes:
            if not isinstance(item, str):
                raise UnifiedPlanningSecurityError("Hash pin store contains non-string hash values")
            token = item.strip().lower()
            if len(token) != 64 or any(ch not in "0123456789abcdef" for ch in token):
                raise UnifiedPlanningSecurityError("Hash pin store contains invalid SHA-256 digest entries")
            if token not in normalized_hashes:
                normalized_hashes.append(token)

        body = {
            "version": version_value,
            "updated_at": updated_at,
            "hashes": normalized_hashes,
        }
        if not self._verify_hash_store_signature(body, signature, key):
            raise UnifiedPlanningSecurityError("Hash pin store signature verification failed")
        return normalized_hashes

    def _write_signed_hash_store(self, key: bytes, hashes: list[str]) -> None:
        path = self._resolve_hash_store_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        normalized_hashes: list[str] = []
        for token in hashes:
            cleaned = token.strip().lower()
            if cleaned and cleaned not in normalized_hashes:
                normalized_hashes.append(cleaned)

        body = {
            "version": self._HASH_PIN_STORE_SCHEMA_VERSION,
            "updated_at": int(time.time()),
            "hashes": normalized_hashes,
        }
        payload = dict(body)
        payload["signature"] = self._sign_hash_store_payload(body, key)

        tmp_path = path.with_suffix(path.suffix + ".tmp")
        data = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
        try:
            with tmp_path.open("w", encoding="utf-8") as handle:
                handle.write(data)
            os.chmod(tmp_path, 0o600)
            tmp_path.replace(path)
        except OSError as exc:
            raise UnifiedPlanningSecurityError(
                f"Unable to persist hash pin store: {exc}"
            ) from exc

    @staticmethod
    def _build_rotated_hash_tokens(
        *,
        current_hash: str,
        env_tokens: list[str],
        store_tokens: list[str],
        max_history: int,
    ) -> list[str]:
        ordered: list[str] = []

        def _add(token: str) -> None:
            value = token.strip().lower()
            if not value:
                return
            if value in ordered:
                return
            ordered.append(value)

        _add(current_hash)
        for token in env_tokens:
            _add(token)
        for token in store_tokens:
            _add(token)
        return ordered[:max_history]

    @staticmethod
    def _validate_license() -> None:
        try:
            pkg_meta = metadata("unified-planning")
        except PackageNotFoundError as exc:
            raise UnifiedPlanningUnavailableError(
                "unified-planning is required but not installed"
            ) from exc

        classifiers = pkg_meta.get_all("Classifier", [])
        blob = " ".join(
            [
                str(pkg_meta.get("License", "")),
                *[str(item) for item in classifiers],
            ]
        ).lower()
        if not any(token in blob for token in UnifiedPlanningEngine._ALLOWED_LICENSE_TOKENS):
            raise UnifiedPlanningSecurityError(
                "unified-planning license verification failed; expected Apache-2.0 compatible metadata"
            )

    @classmethod
    def _network_guard_block_active(cls) -> bool:
        return int(getattr(cls._NETWORK_GUARD_STATE, "depth", 0)) > 0

    @classmethod
    def _network_guard_audit_hook(cls, event: str, _args: tuple[Any, ...]) -> None:
        if not event.startswith("socket."):
            return
        if cls._network_guard_block_active():
            raise UnifiedPlanningSecurityError(
                "Network access is disabled during unified-planning execution"
            )

    @classmethod
    def _ensure_network_guard_audit_hook(cls) -> None:
        with cls._NETWORK_GUARD_HOOK_LOCK:
            if cls._NETWORK_GUARD_HOOK_INSTALLED:
                return
            sys.addaudithook(cls._network_guard_audit_hook)
            cls._NETWORK_GUARD_HOOK_INSTALLED = True

    @classmethod
    def _push_network_guard_scope(cls) -> None:
        current = int(getattr(cls._NETWORK_GUARD_STATE, "depth", 0))
        cls._NETWORK_GUARD_STATE.depth = current + 1

    @classmethod
    def _pop_network_guard_scope(cls) -> None:
        current = int(getattr(cls._NETWORK_GUARD_STATE, "depth", 0))
        if current <= 1:
            if hasattr(cls._NETWORK_GUARD_STATE, "depth"):
                delattr(cls._NETWORK_GUARD_STATE, "depth")
            return
        cls._NETWORK_GUARD_STATE.depth = current - 1

    @contextmanager
    def _network_guard(self):
        """Block networking primitives for the current thread while planner code executes."""
        self._ensure_network_guard_audit_hook()
        self._push_network_guard_scope()
        try:
            yield
        finally:
            self._pop_network_guard_scope()

    def _assert_no_text_payload(self, payload: Any) -> None:
        if isinstance(payload, str):
            raise UnifiedPlanningSecurityError(
                "String payload is not allowed across the unified-planning boundary"
            )
        if isinstance(payload, (bytes, bytearray, memoryview)):
            raise UnifiedPlanningSecurityError(
                "Binary payload is not allowed across the unified-planning boundary"
            )
        if isinstance(payload, (bool, int)):
            return
        if isinstance(payload, dict):
            for key, value in payload.items():
                self._assert_no_text_payload(key)
                self._assert_no_text_payload(value)
            return
        if isinstance(payload, (list, tuple, set, frozenset)):
            for value in payload:
                self._assert_no_text_payload(value)
            return
        raise UnifiedPlanningSecurityError(
            f"Unsupported payload type for unified-planning boundary: {type(payload).__name__}"
        )

    def _normalize_abstract_steps(
        self,
        steps: list[tuple[int, int, bool]],
    ) -> list[tuple[int, int, bool]]:
        normalized: list[tuple[int, int, bool]] = []
        for index, raw_step in enumerate(steps):
            if not isinstance(raw_step, (list, tuple)) or len(raw_step) != 3:
                raise UnifiedPlanningSecurityError(
                    f"Invalid abstract step payload at index {index}"
                )
            step_id_raw, op_code_raw, valid_raw = raw_step
            if not isinstance(step_id_raw, int) or isinstance(step_id_raw, bool) or step_id_raw < 0:
                raise UnifiedPlanningSecurityError(
                    f"Invalid step identifier at index {index}"
                )
            if not isinstance(op_code_raw, int) or isinstance(op_code_raw, bool):
                raise UnifiedPlanningSecurityError(
                    f"Invalid op code at index {index}"
                )
            if op_code_raw < 0 or op_code_raw > 99:
                raise UnifiedPlanningSecurityError(
                    f"Out-of-range op code at index {index}"
                )
            if not isinstance(valid_raw, bool):
                raise UnifiedPlanningSecurityError(
                    f"Invalid step validity flag at index {index}"
                )
            normalized.append((int(step_id_raw), int(op_code_raw), bool(valid_raw)))
        return normalized

    def analyze_complexity(
        self,
        *,
        steps: list[tuple[int, int, bool]],
        dependency_count: int,
    ) -> dict[str, Any]:
        normalized_steps = self._normalize_abstract_steps(steps)
        if not isinstance(dependency_count, int) or isinstance(dependency_count, bool):
            raise UnifiedPlanningSecurityError("dependency_count must be an integer")
        dep_count = dependency_count
        if dep_count < 0:
            raise UnifiedPlanningSecurityError("dependency_count must be non-negative")
        if len(normalized_steps) > self._MAX_STEPS:
            raise UnifiedPlanningSecurityError(
                f"planner step count exceeds limit ({self._MAX_STEPS})"
            )
        if dep_count > self._MAX_DEPENDENCIES:
            raise UnifiedPlanningSecurityError(
                f"planner dependency count exceeds limit ({self._MAX_DEPENDENCIES})"
            )
        self._assert_no_text_payload(normalized_steps)
        self._assert_no_text_payload(dep_count)

        destructive = sum(1 for _, op_code, _ in normalized_steps if op_code in self._DESTRUCTIVE_OP_CODES)
        invalid = sum(1 for _, _, is_valid in normalized_steps if not is_valid)
        score = len(normalized_steps) + (2 * destructive) + (3 * invalid) + min(4, dep_count)
        if score <= 3:
            level = "low"
            strategy = "linear"
        elif score <= 8:
            level = "medium"
            strategy = "dependency_ordered"
        elif score <= 14:
            level = "high"
            strategy = "risk_first_structured"
        else:
            level = "very_high"
            strategy = "phased_with_human_checkpoints"

        return {
            "score": score,
            "level": level,
            "strategy": strategy,
            "factors": {
                "op_count": len(normalized_steps),
                "destructive_op_count": destructive,
                "invalid_op_count": invalid,
                "dependency_count": dep_count,
            },
        }

    def plan_order(
        self,
        *,
        step_count: int,
        dependencies: list[tuple[int, int]],
    ) -> dict[str, Any]:
        if not isinstance(step_count, int) or isinstance(step_count, bool):
            raise UnifiedPlanningSecurityError("step_count must be an integer")
        if step_count < 0:
            raise UnifiedPlanningSecurityError("step_count must be non-negative")
        if step_count > self._MAX_STEPS:
            raise UnifiedPlanningSecurityError(
                f"planner step count exceeds limit ({self._MAX_STEPS})"
            )
        if step_count <= 0:
            return {
                "engine": "unified-planning",
                "engine_version": self.version,
                "engine_name": "",
                "status": "SKIPPED_EMPTY",
                "ordered_indices": [],
            }
        if not isinstance(dependencies, list):
            raise UnifiedPlanningSecurityError("dependencies must be a list")
        if len(dependencies) > self._MAX_DEPENDENCIES:
            raise UnifiedPlanningSecurityError(
                f"planner dependency count exceeds limit ({self._MAX_DEPENDENCIES})"
            )
        for index, edge in enumerate(dependencies):
            if not isinstance(edge, (list, tuple)) or len(edge) != 2:
                raise UnifiedPlanningSecurityError(f"Invalid dependency edge at index {index}")

        self._assert_no_text_payload(step_count)
        self._assert_no_text_payload(dependencies)

        deps: list[set[int]] = [set() for _ in range(step_count)]
        for before, after in dependencies:
            if not isinstance(before, int) or isinstance(before, bool):
                raise UnifiedPlanningSecurityError("Dependency source index must be an integer")
            if not isinstance(after, int) or isinstance(after, bool):
                raise UnifiedPlanningSecurityError("Dependency target index must be an integer")
            if before == after:
                raise UnifiedPlanningSecurityError("Self-dependencies are not allowed")
            if before < 0 or after < 0 or before >= step_count or after >= step_count:
                raise UnifiedPlanningSecurityError("Invalid planner dependency indices")
            deps[after].add(before)

        problem = self._Problem("file_ops_ordering")
        done_fluents = []
        for index in range(step_count):
            fluent = self._Fluent(f"step_{index}_done")
            problem.add_fluent(fluent, default_initial_value=False)
            done_fluents.append(fluent)

        for index in range(step_count):
            action = self._InstantaneousAction(f"step_{index}")
            action.add_precondition(self._Not(done_fluents[index]))
            for dependency_index in sorted(deps[index]):
                action.add_precondition(done_fluents[dependency_index])
            action.add_effect(done_fluents[index], True)
            problem.add_action(action)
            problem.add_goal(done_fluents[index])

        with self._network_guard():
            with self._OneshotPlanner(problem_kind=problem.kind) as planner:
                engine_name = str(getattr(planner, "name", "") or planner.__class__.__name__)
                result = planner.solve(problem)

        status_text = str(getattr(result, "status", "UNKNOWN")).strip() or "UNKNOWN"
        plan = getattr(result, "plan", None)
        if plan is None or not hasattr(plan, "actions"):
            raise UnifiedPlanningUnavailableError(
                f"unified-planning returned no executable plan (status={status_text})"
            )

        ordered_indices: list[int] = []
        for step in getattr(plan, "actions", []):
            action = getattr(step, "action", None)
            name = str(getattr(action, "name", "")).strip()
            if not name.startswith("step_"):
                continue
            try:
                ordered_indices.append(int(name.split("_", 1)[1]))
            except ValueError:
                continue

        if sorted(ordered_indices) != list(range(step_count)):
            raise UnifiedPlanningUnavailableError(
                "unified-planning produced an invalid operation ordering"
            )

        return {
            "engine": "unified-planning",
            "engine_version": self.version,
            "engine_name": engine_name,
            "status": status_text,
            "ordered_indices": ordered_indices,
        }
