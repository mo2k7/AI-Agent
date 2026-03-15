"""One-time strict migration for legacy memory/session artifacts.

This module upgrades legacy persisted state before strict runtime starts:
1) upgrades legacy semantic-memory HMAC rows to v2 payloads
2) removes legacy ``ipc-*`` ghost sessions with zero messages
3) writes a migration marker and backup snapshot

Runtime code should not perform legacy migration/cleanup after this runs.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from .crypto import compute_hmac, verify_hmac
from .keychain import KeychainError, get_or_create_master_key


MIGRATION_ID = "strict_runtime_v2"
MIGRATION_VERSION = 1
MIGRATION_PREFIX = "v2:"


class MemoryMigrationError(RuntimeError):
    """Raised when strict preflight migration fails."""


@dataclass(frozen=True)
class MigrationResult:
    """Migration summary payload."""

    migration_id: str
    version: int
    upgraded_hmac_rows: int
    removed_ghost_sessions: int
    backup_path: str
    marker_path: str
    already_migrated: bool


def _marker_path(memory_root: Path) -> Path:
    return memory_root / ".migrations" / f"{MIGRATION_ID}.json"


def _backup_root(memory_root: Path) -> Path:
    return memory_root / "migration_backups"


def _semantic_hmac_payload_v2(
    *,
    memory_id: str,
    kind: str,
    fact_key: str,
    content_enc: str,
    confidence: float,
    source_message_id: str,
    trust_flags_json: str,
    policy_flags_json: str,
    created_at: float,
    updated_at: float,
    is_deleted: int,
) -> str:
    payload = {
        "memory_id": str(memory_id),
        "kind": str(kind),
        "fact_key": str(fact_key),
        "content_enc": str(content_enc),
        "confidence": float(confidence),
        "source_message_id": str(source_message_id),
        "trust_flags_json": str(trust_flags_json),
        "policy_flags_json": str(policy_flags_json),
        "created_at": float(created_at),
        "updated_at": float(updated_at),
        "is_deleted": int(is_deleted),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _copy_if_exists(path: Path, target: Path) -> None:
    if not path.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)


def _snapshot_memory_state(memory_root: Path, destination_root: Path) -> None:
    destination_root.mkdir(parents=True, exist_ok=True)
    _copy_if_exists(memory_root / "index.db", destination_root / "index.db")
    _copy_if_exists(memory_root / "index.db-wal", destination_root / "index.db-wal")
    _copy_if_exists(memory_root / "index.db-shm", destination_root / "index.db-shm")

    sessions_dir = memory_root / "sessions"
    if not sessions_dir.exists():
        return
    for session_db in sorted(sessions_dir.glob("*.db")):
        _copy_if_exists(session_db, destination_root / "sessions" / session_db.name)
        _copy_if_exists(
            Path(f"{session_db}-wal"),
            destination_root / "sessions" / f"{session_db.name}-wal",
        )
        _copy_if_exists(
            Path(f"{session_db}-shm"),
            destination_root / "sessions" / f"{session_db.name}-shm",
        )


def _read_sqlite_count(connection: sqlite3.Connection, query: str, params: tuple[object, ...]) -> int:
    row = connection.execute(query, params).fetchone()
    if row is None:
        return 0
    value = row[0]
    return int(value) if value is not None else 0


def _remove_ghost_ipc_sessions(memory_root: Path) -> int:
    index_db = memory_root / "index.db"
    sessions_dir = memory_root / "sessions"
    if not index_db.exists():
        return 0

    removed = 0
    with closing(sqlite3.connect(index_db)) as index_conn, index_conn:
        rows = index_conn.execute(
            "SELECT session_id FROM sessions WHERE session_id LIKE 'ipc-%'"
        ).fetchall()
        for row in rows:
            session_id = str(row[0]).strip()
            if not session_id:
                continue

            session_db = sessions_dir / f"{session_id}.db"
            should_remove = False
            if not session_db.exists():
                should_remove = True
            else:
                try:
                    with closing(sqlite3.connect(session_db)) as session_conn:
                        message_count = _read_sqlite_count(
                            session_conn,
                            "SELECT COUNT(*) FROM messages",
                            (),
                        )
                        should_remove = message_count == 0
                except sqlite3.DatabaseError:
                    should_remove = True

            if not should_remove:
                continue

            index_conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            index_conn.execute("DELETE FROM semantic_index WHERE session_id = ?", (session_id,))
            removed += 1

            for candidate in (
                session_db,
                Path(f"{session_db}-wal"),
                Path(f"{session_db}-shm"),
            ):
                candidate.unlink(missing_ok=True)
    return removed


def _upgrade_legacy_semantic_hmac_rows(memory_root: Path, master_key: bytes) -> int:
    sessions_dir = memory_root / "sessions"
    if not sessions_dir.exists():
        return 0

    upgraded_rows = 0
    for session_db in sorted(sessions_dir.glob("*.db")):
        with closing(sqlite3.connect(session_db)) as connection, connection:
            connection.row_factory = sqlite3.Row
            table_row = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='semantic_memories'"
            ).fetchone()
            if table_row is None:
                continue

            rows = connection.execute(
                """
                SELECT memory_id, kind, fact_key, content_enc, confidence, source_message_id,
                       trust_flags_json, policy_flags_json, created_at, updated_at, is_deleted, hmac
                FROM semantic_memories
                WHERE hmac NOT LIKE ?
                """,
                (f"{MIGRATION_PREFIX}%",),
            ).fetchall()
            if not rows:
                continue

            updates: list[tuple[str, str]] = []
            for row in rows:
                memory_id = str(row["memory_id"])
                legacy_payload = f"{memory_id}:{row['content_enc']}:{row['fact_key']}:{row['kind']}"
                if not verify_hmac(master_key, legacy_payload, row["hmac"]):
                    raise MemoryMigrationError(
                        f"Legacy semantic HMAC verification failed for memory_id={memory_id}"
                    )
                upgraded_payload = _semantic_hmac_payload_v2(
                    memory_id=memory_id,
                    kind=str(row["kind"]),
                    fact_key=str(row["fact_key"]),
                    content_enc=str(row["content_enc"]),
                    confidence=float(row["confidence"]),
                    source_message_id=str(row["source_message_id"]),
                    trust_flags_json=str(row["trust_flags_json"]),
                    policy_flags_json=str(row["policy_flags_json"]),
                    created_at=float(row["created_at"]),
                    updated_at=float(row["updated_at"]),
                    is_deleted=int(row["is_deleted"]),
                )
                upgraded_hmac = f"{MIGRATION_PREFIX}{compute_hmac(master_key, upgraded_payload)}"
                updates.append((upgraded_hmac, memory_id))

            connection.executemany(
                "UPDATE semantic_memories SET hmac = ? WHERE memory_id = ?",
                updates,
            )
            upgraded_rows += len(updates)
    return upgraded_rows


def run_preflight_migration(memory_root: Path) -> MigrationResult:
    """Old v2 preflight migration is now a no-op since v3 is a unified DB clean break."""
    return MigrationResult(
        migration_id=MIGRATION_ID,
        version=MIGRATION_VERSION,
        upgraded_hmac_rows=0,
        removed_ghost_sessions=0,
        backup_path="",
        marker_path="",
        already_migrated=True,
    )


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run one-time strict memory migration")
    parser.add_argument(
        "--memory-root",
        required=True,
        help="Path to memory root directory (contains index.db and sessions/)",
    )
    args = parser.parse_args()

    result = run_preflight_migration(Path(args.memory_root))
    print(json.dumps(result.__dict__, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
