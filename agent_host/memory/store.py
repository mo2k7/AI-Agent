"""Encrypted SQLite persistence for session and semantic memory."""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import stat
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, TypeVar, TYPE_CHECKING, cast

from .crypto import CryptoBox, compute_hmac, verify_hmac
from .retriever import encode_text_semantic
if TYPE_CHECKING:
    from .embeddings import EmbeddingService
from .types import MemoryKind, MemoryMode, MemoryRecord, SessionMessage, SessionRecord

logger = logging.getLogger(__name__)


def _safe_int(raw: str, default: int) -> int:
    """Parse *raw* as an integer, returning *default* on failure."""
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


def _safe_float(raw: str, default: float) -> float:
    """Parse *raw* as a float, returning *default* on failure."""
    try:
        return float(raw)
    except (ValueError, TypeError):
        return default


class MemoryStoreError(RuntimeError):
    """Raised for storage-layer failures."""


T = TypeVar("T")


class _DBMetricsCollector:
    """Thread-safe SQLite contention + latency metrics collector."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets_ms = (1, 5, 10, 25, 50, 100, 250, 500, 1000)
        self._histogram: dict[str, int] = {self._bucket_name(limit): 0 for limit in self._buckets_ms}
        self._histogram["gt_1000ms"] = 0
        self._total_queries = 0
        self._total_locked = 0
        self._total_busy = 0
        self._total_retries = 0
        self._total_failures = 0

    @staticmethod
    def _bucket_name(limit: int) -> str:
        return f"le_{limit}ms"

    def record(
        self,
        *,
        latency_ms: float,
        retries: int,
        locked: bool,
        busy: bool,
        failed: bool,
    ) -> None:
        with self._lock:
            self._total_queries += 1
            self._total_retries += max(0, retries)
            if locked:
                self._total_locked += 1
            if busy:
                self._total_busy += 1
            if failed:
                self._total_failures += 1

            bucket_key = "gt_1000ms"
            for limit in self._buckets_ms:
                if latency_ms <= limit:
                    bucket_key = self._bucket_name(limit)
                    break
            self._histogram[bucket_key] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "queries_total": self._total_queries,
                "retries_total": self._total_retries,
                "locked_events": self._total_locked,
                "busy_events": self._total_busy,
                "failures_total": self._total_failures,
                "latency_histogram": dict(self._histogram),
            }


_DB_METRICS = _DBMetricsCollector()


def get_db_metrics_snapshot() -> dict[str, Any]:
    return _DB_METRICS.snapshot()


class _InstrumentedConnection(sqlite3.Connection):
    """sqlite3 connection with busy/locked retries and latency tracking."""

    _retry_attempts = max(0, _safe_int(os.environ.get("AI_AGENT_SQLITE_BUSY_RETRIES", "5"), 5))
    _retry_delay_seconds = max(
        0.0,
        _safe_float(os.environ.get("AI_AGENT_SQLITE_BUSY_RETRY_DELAY_MS", "20"), 20.0) / 1000.0,
    )

    @staticmethod
    def _is_lock_error(exc: sqlite3.OperationalError) -> tuple[bool, bool]:
        detail = str(exc).lower()
        return ("locked" in detail, "busy" in detail)

    def execute(self, sql: str, parameters: Any = (), /) -> sqlite3.Cursor:
        super_execute = super().execute
        return self._run_with_retry("execute", sql, lambda: super_execute(sql, parameters))

    def executemany(self, sql: str, seq_of_parameters: Any, /) -> sqlite3.Cursor:
        super_executemany = super().executemany
        return self._run_with_retry(
            "executemany",
            sql,
            lambda: super_executemany(sql, seq_of_parameters),
        )

    def executescript(self, sql_script: str, /) -> sqlite3.Cursor:
        super_executescript = super().executescript
        return self._run_with_retry("executescript", sql_script, lambda: super_executescript(sql_script))

    def _run_with_retry(self, operation: str, sql: str, call: Callable[[], sqlite3.Cursor]) -> sqlite3.Cursor:
        started = time.perf_counter()
        retries = 0
        saw_locked = False
        saw_busy = False
        failed = False
        while True:
            try:
                cursor = call()
                latency_ms = (time.perf_counter() - started) * 1000.0
                _DB_METRICS.record(
                    latency_ms=latency_ms,
                    retries=retries,
                    locked=saw_locked,
                    busy=saw_busy,
                    failed=failed,
                )
                return cursor
            except sqlite3.OperationalError as exc:
                is_locked, is_busy = self._is_lock_error(exc)
                if not is_locked and not is_busy:
                    failed = True
                    latency_ms = (time.perf_counter() - started) * 1000.0
                    _DB_METRICS.record(
                        latency_ms=latency_ms,
                        retries=retries,
                        locked=saw_locked,
                        busy=saw_busy,
                        failed=failed,
                    )
                    raise
                saw_locked = saw_locked or is_locked
                saw_busy = saw_busy or is_busy
                if retries >= self._retry_attempts:
                    failed = True
                    latency_ms = (time.perf_counter() - started) * 1000.0
                    _DB_METRICS.record(
                        latency_ms=latency_ms,
                        retries=retries,
                        locked=saw_locked,
                        busy=saw_busy,
                        failed=failed,
                    )
                    logger.warning(
                        "sqlite_retry_exhausted",
                        extra={
                            "component": "db.sqlite",
                            "method": operation,
                            "duration_ms": round(latency_ms, 3),
                            "error_type": type(exc).__name__,
                            "error_message": str(exc),
                            "sql_preview": sql[:180],
                            "retry_count": retries,
                        },
                    )
                    raise
                retries += 1
                logger.warning(
                    "sqlite_locked_or_busy_retry",
                    extra={
                        "component": "db.sqlite",
                        "method": operation,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                        "sql_preview": sql[:180],
                        "retry_count": retries,
                    },
                )
                delay = self._retry_delay_seconds * retries
                time.sleep(delay)


def _sqlite_connect(path: Path) -> sqlite3.Connection:
    timeout_seconds = _safe_float(os.environ.get("AI_AGENT_SQLITE_TIMEOUT_SECONDS", "5"), 5.0)
    return sqlite3.connect(path, timeout=timeout_seconds, factory=_InstrumentedConnection)


class MemoryStore:
    """Per-session encrypted store plus global cross-session index."""

    _INDEX_SCHEMA_SQL = """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            memory_mode TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            last_activity REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            wrapped_dek TEXT NOT NULL,
            wrap_nonce TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_sessions_last_activity
        ON sessions(last_activity DESC);

        CREATE TABLE IF NOT EXISTS semantic_index (
            memory_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            fact_key TEXT NOT NULL,
            vector_json TEXT NOT NULL,
            token_set_json TEXT NOT NULL,
            confidence REAL NOT NULL,
            updated_at REAL NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_semantic_session_updated
        ON semantic_index(session_id, updated_at DESC);

        CREATE INDEX IF NOT EXISTS idx_semantic_fact_key
        ON semantic_index(fact_key);
    """

    _SESSION_SCHEMA_SQL = """
        CREATE TABLE IF NOT EXISTS messages (
            message_id TEXT PRIMARY KEY,
            turn_index INTEGER NOT NULL,
            role TEXT NOT NULL,
            content_enc TEXT NOT NULL,
            created_at REAL NOT NULL,
            token_estimate INTEGER NOT NULL DEFAULT 0,
            meta_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_messages_turn
        ON messages(turn_index);

        CREATE TABLE IF NOT EXISTS summaries (
            summary_id TEXT PRIMARY KEY,
            turn_start INTEGER NOT NULL,
            turn_end INTEGER NOT NULL,
            summary_enc TEXT NOT NULL,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS semantic_memories (
            memory_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            fact_key TEXT NOT NULL,
            content_enc TEXT NOT NULL,
            confidence REAL NOT NULL,
            source_message_id TEXT NOT NULL,
            trust_flags_json TEXT NOT NULL,
            policy_flags_json TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            is_deleted INTEGER NOT NULL DEFAULT 0,
            hmac TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_semantic_fact_key
        ON semantic_memories(fact_key, is_deleted, updated_at DESC);

        CREATE TABLE IF NOT EXISTS session_info (
            session_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            memory_mode TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            last_activity REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            wrapped_dek TEXT NOT NULL,
            wrap_nonce TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notes (
            note_id TEXT PRIMARY KEY,
            content_enc TEXT NOT NULL,
            is_pinned INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            is_deleted INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT 'user'
        );

        CREATE INDEX IF NOT EXISTS idx_notes_updated
        ON notes(is_deleted, is_pinned DESC, updated_at DESC);

        CREATE TABLE IF NOT EXISTS note_images (
            image_id TEXT PRIMARY KEY,
            note_id TEXT NOT NULL,
            image_enc TEXT NOT NULL,
            mime_type TEXT NOT NULL DEFAULT 'image/png',
            width INTEGER NOT NULL DEFAULT 0,
            height INTEGER NOT NULL DEFAULT 0,
            alt_text TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            is_deleted INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (note_id) REFERENCES notes(note_id)
        );

        CREATE INDEX IF NOT EXISTS idx_note_images_note_id
        ON note_images(note_id, is_deleted);

        CREATE TABLE IF NOT EXISTS note_versions (
            version_id TEXT PRIMARY KEY,
            note_id TEXT NOT NULL,
            content_enc TEXT NOT NULL,
            created_at REAL NOT NULL,
            FOREIGN KEY (note_id) REFERENCES notes(note_id)
        );

        CREATE INDEX IF NOT EXISTS idx_note_versions_note_id
        ON note_versions(note_id, created_at DESC);
    """

    _INDEX_REQUIRED_COLUMNS: dict[str, dict[str, str]] = {
        "sessions": {
            "session_id": "TEXT",
            "title": "TEXT NOT NULL DEFAULT ''",
            "memory_mode": "TEXT NOT NULL DEFAULT 'on'",
            "created_at": "REAL NOT NULL DEFAULT 0",
            "updated_at": "REAL NOT NULL DEFAULT 0",
            "last_activity": "REAL NOT NULL DEFAULT 0",
            "status": "TEXT NOT NULL DEFAULT 'active'",
            "wrapped_dek": "TEXT NOT NULL DEFAULT ''",
            "wrap_nonce": "TEXT NOT NULL DEFAULT ''",
        },
        "semantic_index": {
            "memory_id": "TEXT",
            "session_id": "TEXT NOT NULL DEFAULT ''",
            "kind": "TEXT NOT NULL DEFAULT 'profile_fact'",
            "fact_key": "TEXT NOT NULL DEFAULT ''",
            "vector_json": "TEXT NOT NULL DEFAULT '[]'",
            "token_set_json": "TEXT NOT NULL DEFAULT '[]'",
            "confidence": "REAL NOT NULL DEFAULT 0",
            "updated_at": "REAL NOT NULL DEFAULT 0",
        },
    }

    _SESSION_REQUIRED_COLUMNS: dict[str, dict[str, str]] = {
        "messages": {
            "message_id": "TEXT",
            "turn_index": "INTEGER NOT NULL DEFAULT 0",
            "role": "TEXT NOT NULL DEFAULT 'user'",
            "content_enc": "TEXT NOT NULL DEFAULT ''",
            "created_at": "REAL NOT NULL DEFAULT 0",
            "token_estimate": "INTEGER NOT NULL DEFAULT 0",
            "meta_json": "TEXT NOT NULL DEFAULT '{}'",
        },
        "summaries": {
            "summary_id": "TEXT",
            "turn_start": "INTEGER NOT NULL DEFAULT 0",
            "turn_end": "INTEGER NOT NULL DEFAULT 0",
            "summary_enc": "TEXT NOT NULL DEFAULT ''",
            "created_at": "REAL NOT NULL DEFAULT 0",
        },
        "semantic_memories": {
            "memory_id": "TEXT",
            "kind": "TEXT NOT NULL DEFAULT 'profile_fact'",
            "fact_key": "TEXT NOT NULL DEFAULT ''",
            "content_enc": "TEXT NOT NULL DEFAULT ''",
            "confidence": "REAL NOT NULL DEFAULT 0",
            "source_message_id": "TEXT NOT NULL DEFAULT ''",
            "trust_flags_json": "TEXT NOT NULL DEFAULT '[]'",
            "policy_flags_json": "TEXT NOT NULL DEFAULT '[]'",
            "created_at": "REAL NOT NULL DEFAULT 0",
            "updated_at": "REAL NOT NULL DEFAULT 0",
            "is_deleted": "INTEGER NOT NULL DEFAULT 0",
            "hmac": "TEXT NOT NULL DEFAULT ''",
        },
        "session_info": {
            "session_id": "TEXT",
            "title": "TEXT NOT NULL DEFAULT ''",
            "memory_mode": "TEXT NOT NULL DEFAULT 'on'",
            "created_at": "REAL NOT NULL DEFAULT 0",
            "updated_at": "REAL NOT NULL DEFAULT 0",
            "last_activity": "REAL NOT NULL DEFAULT 0",
            "status": "TEXT NOT NULL DEFAULT 'active'",
            "wrapped_dek": "TEXT NOT NULL DEFAULT ''",
            "wrap_nonce": "TEXT NOT NULL DEFAULT ''",
        },
        "notes": {
            "note_id": "TEXT",
            "content_enc": "TEXT NOT NULL DEFAULT ''",
            "is_pinned": "INTEGER NOT NULL DEFAULT 0",
            "created_at": "REAL NOT NULL DEFAULT 0",
            "updated_at": "REAL NOT NULL DEFAULT 0",
            "is_deleted": "INTEGER NOT NULL DEFAULT 0",
            "source": "TEXT NOT NULL DEFAULT 'user'",
        },
    }
    _SEMANTIC_HMAC_VERSION = "v2"
    _SEMANTIC_HMAC_PREFIX = f"{_SEMANTIC_HMAC_VERSION}:"

    _SESSION_INFO_SELECT_COLUMNS = (
        "session_id, title, memory_mode, created_at, updated_at, "
        "last_activity, status, wrapped_dek, wrap_nonce"
    )

    def __init__(self, root_dir: Path, *, master_key: bytes):
        self.root_dir = root_dir
        self.sessions_dir = root_dir / "sessions"
        self.index_db_path = root_dir / "index.db"
        self._master_box = CryptoBox(master_key)
        self._master_key = master_key
        self._dek_cache: dict[str, bytes] = {}
        self._dek_cache_lock = threading.Lock()

        self._ensure_directories()
        self._init_index_db()

    # ------------------------------------------------------------------
    # setup
    # ------------------------------------------------------------------
    def _ensure_directories(self) -> None:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._enforce_permissions(self.root_dir, is_dir=True)
        self._enforce_permissions(self.sessions_dir, is_dir=True)

    def _canonical_session_id(self, session_id: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", session_id.strip()).strip("-.")
        if not cleaned:
            raise MemoryStoreError("Session id cannot be empty")
        return cleaned[:96]

    def _enforce_permissions(self, path: Path, *, is_dir: bool) -> None:
        mode = 0o700 if is_dir else 0o600
        try:
            path.chmod(mode)
        except PermissionError as exc:
            raise MemoryStoreError(f"Unable to enforce permissions on {path}") from exc

        actual_mode = stat.S_IMODE(path.stat().st_mode)
        if actual_mode & 0o077:
            raise MemoryStoreError(f"Insecure permissions on {path}: {oct(actual_mode)}")

    @staticmethod
    def _is_recoverable_index_error(exc: BaseException) -> bool:
        if not isinstance(exc, sqlite3.DatabaseError):
            return False
        lower = str(exc).lower()
        return any(
            marker in lower
            for marker in (
                "no such table",
                "malformed",
                "not a database",
                "disk image is malformed",
                "database schema is malformed",
                "file is not a database",
                "no such column",
                "has no column named",
            )
        )

    @staticmethod
    def _is_recoverable_session_error(exc: BaseException) -> bool:
        if not isinstance(exc, sqlite3.DatabaseError):
            return False
        lower = str(exc).lower()
        return any(
            marker in lower
            for marker in (
                "no such table",
                "malformed",
                "not a database",
                "disk image is malformed",
                "database schema is malformed",
                "file is not a database",
                "integrity check failed",
                "no such column",
                "has no column named",
            )
        )

    def _quarantine_db_family(self, db_path: Path) -> None:
        stamp = int(time.time() * 1000)
        for suffix in ("", "-wal", "-shm"):
            path = db_path if suffix == "" else Path(f"{db_path}{suffix}")
            if not path.exists():
                continue
            target = path.with_name(f"{path.name}.corrupt-{stamp}")
            counter = 0
            while target.exists():
                counter += 1
                target = path.with_name(f"{path.name}.corrupt-{stamp}-{counter}")
            path.replace(target)

    def _create_session_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(self._SESSION_SCHEMA_SQL)
        self._ensure_required_columns(conn, self._SESSION_REQUIRED_COLUMNS)

    def _table_columns(self, conn: sqlite3.Connection, table_name: str) -> set[str]:
        rows = conn.execute(f"PRAGMA table_info([{table_name}])").fetchall()
        return {str(row["name"] if isinstance(row, sqlite3.Row) else row[1]) for row in rows}

    def _ensure_required_columns(
        self,
        conn: sqlite3.Connection,
        required_by_table: dict[str, dict[str, str]],
    ) -> None:
        for table_name, required_columns in required_by_table.items():
            existing_columns = self._table_columns(conn, table_name)
            for column_name, column_sql in required_columns.items():
                if column_name in existing_columns:
                    continue
                conn.execute(f"ALTER TABLE [{table_name}] ADD COLUMN [{column_name}] {column_sql}")

    def _with_repair(
        self,
        *,
        operation: Callable[[], T],
        is_recoverable: Callable[[BaseException], bool],
        repair: Callable[[], None],
    ) -> T:
        try:
            return operation()
        except Exception as exc:
            if not is_recoverable(exc):
                raise
            repair()
            return operation()

    def _rebuild_index_db(self) -> None:
        self._quarantine_db_family(self.index_db_path)
        conn = _sqlite_connect(self.index_db_path)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            self._ensure_index_schema(conn)
        finally:
            conn.close()
        if self.index_db_path.exists():
            self._enforce_permissions(self.index_db_path, is_dir=False)

    def _connect_index(self, *, ensure_schema: bool = True) -> sqlite3.Connection:
        def _open() -> sqlite3.Connection:
            conn = _sqlite_connect(self.index_db_path)
            try:
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA foreign_keys=ON;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                if ensure_schema:
                    self._ensure_index_schema(conn)
                    if self.index_db_path.exists():
                        self._enforce_permissions(self.index_db_path, is_dir=False)
                return conn
            except Exception:
                conn.close()
                raise

        if not ensure_schema:
            return _open()

        return self._with_repair(
            operation=_open,
            is_recoverable=self._is_recoverable_index_error,
            repair=self._rebuild_index_db,
        )

    @contextmanager
    def _index_connection(self, *, ensure_schema: bool = True):
        conn = self._connect_index(ensure_schema=ensure_schema)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _ensure_index_schema(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        existing = {str(row["name"]) for row in rows}
        required = {"sessions", "semantic_index"}
        if not required.issubset(existing):
            conn.executescript(self._INDEX_SCHEMA_SQL)
        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_sessions_last_activity
            ON sessions(last_activity DESC);
            CREATE INDEX IF NOT EXISTS idx_semantic_session_updated
            ON semantic_index(session_id, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_semantic_fact_key
            ON semantic_index(fact_key);
            """
        )
        self._ensure_required_columns(conn, self._INDEX_REQUIRED_COLUMNS)
        conn.commit()

        verify_rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        verify_existing = {str(row["name"]) for row in verify_rows}
        has_required_tables = required.issubset(verify_existing)
        has_required_columns = all(
            set(columns.keys()).issubset(self._table_columns(conn, table_name))
            for table_name, columns in self._INDEX_REQUIRED_COLUMNS.items()
        )
        if not has_required_tables or not has_required_columns:
            raise MemoryStoreError(
                "Failed to initialize memory index database schema"
            )

    def _init_index_db(self) -> None:
        self._with_repair(
            operation=lambda: self._connect_index(ensure_schema=True).close(),
            is_recoverable=self._is_recoverable_index_error,
            repair=self._rebuild_index_db,
        )

        if not self.index_db_path.exists():
            raise MemoryStoreError("Failed to initialize memory index database")
        self._enforce_permissions(self.index_db_path, is_dir=False)

    def _safe_memory_mode(self, raw_mode: object, *, session_id: str | None = None) -> MemoryMode:
        """Parse persisted memory mode and self-heal invalid values."""
        if isinstance(raw_mode, str):
            normalized = raw_mode.strip().lower()
            for mode in MemoryMode:
                if mode.value == normalized:
                    return mode

        fallback = MemoryMode.ON
        if session_id:
            try:
                with self._index_connection() as conn:
                    conn.execute(
                        """
                        UPDATE sessions
                        SET memory_mode = ?, updated_at = ?, last_activity = ?
                        WHERE session_id = ?
                        """,
                        (fallback.value, time.time(), time.time(), session_id),
                    )
                self._upsert_session_info_from_index(session_id)
            except sqlite3.Error as exc:
                raise MemoryStoreError(
                    f"Failed to repair invalid memory_mode for session {session_id}"
                ) from exc
        return fallback

    @staticmethod
    def _safe_json_object(payload: object, *, default: dict[str, Any] | None = None) -> dict[str, Any]:
        """Best-effort JSON object parse for stored metadata."""
        fallback = default or {}
        if not isinstance(payload, str):
            return fallback
        try:
            decoded = json.loads(payload)
        except Exception:
            return fallback
        return decoded if isinstance(decoded, dict) else fallback

    @staticmethod
    def _safe_json_array(payload: object) -> list[str]:
        """Best-effort JSON array parse for trust/policy flag fields."""
        if not isinstance(payload, str):
            return []
        try:
            decoded = json.loads(payload)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("Malformed JSON array in store: %s", exc)
            return []
        if not isinstance(decoded, list):
            return []
        return [str(item) for item in decoded]

    def _row_to_session_record(self, row: sqlite3.Row) -> SessionRecord:
        return SessionRecord(
            session_id=row["session_id"],
            title=row["title"],
            memory_mode=self._safe_memory_mode(
                row["memory_mode"],
                session_id=row["session_id"],
            ),
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
            last_activity=float(row["last_activity"]),
            status=row["status"],
        )

    def _fetch_session_row(self, session_id: str) -> sqlite3.Row | None:
        with self._index_connection() as conn:
            return conn.execute(
                """
                SELECT session_id, title, memory_mode, created_at, updated_at, last_activity, status
                FROM sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()

    def _upsert_index_session(
        self,
        *,
        session_id: str,
        title: str,
        memory_mode: str,
        created_at: float,
        updated_at: float,
        last_activity: float,
        status: str,
        wrapped_dek: str,
        wrap_nonce: str,
    ) -> None:
        session_id = self._canonical_session_id(session_id)
        with self._index_connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    session_id, title, memory_mode, created_at, updated_at, last_activity,
                    status, wrapped_dek, wrap_nonce
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    title=excluded.title,
                    memory_mode=excluded.memory_mode,
                    created_at=excluded.created_at,
                    updated_at=excluded.updated_at,
                    last_activity=excluded.last_activity,
                    status=excluded.status,
                    wrapped_dek=excluded.wrapped_dek,
                    wrap_nonce=excluded.wrap_nonce
                """,
                (
                    session_id,
                    title,
                    memory_mode,
                    created_at,
                    updated_at,
                    last_activity,
                    status,
                    wrapped_dek,
                    wrap_nonce,
                ),
            )

    def _upsert_session_info(
        self,
        *,
        session_id: str,
        title: str,
        memory_mode: str,
        created_at: float,
        updated_at: float,
        last_activity: float,
        status: str,
        wrapped_dek: str,
        wrap_nonce: str,
    ) -> None:
        session_id = self._canonical_session_id(session_id)
        with self._session_connection(session_id) as conn:
            self._write_session_info(
                conn,
                session_id=session_id,
                title=title,
                memory_mode=memory_mode,
                created_at=created_at,
                updated_at=updated_at,
                last_activity=last_activity,
                status=status,
                wrapped_dek=wrapped_dek,
                wrap_nonce=wrap_nonce,
            )

    def _write_session_info(
        self,
        conn: sqlite3.Connection,
        *,
        session_id: str,
        title: str,
        memory_mode: str,
        created_at: float,
        updated_at: float,
        last_activity: float,
        status: str,
        wrapped_dek: str,
        wrap_nonce: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO session_info (
                session_id, title, memory_mode, created_at, updated_at,
                last_activity, status, wrapped_dek, wrap_nonce
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                title=excluded.title,
                memory_mode=excluded.memory_mode,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at,
                last_activity=excluded.last_activity,
                status=excluded.status,
                wrapped_dek=excluded.wrapped_dek,
                wrap_nonce=excluded.wrap_nonce
            """,
            (
                session_id,
                title,
                memory_mode,
                created_at,
                updated_at,
                last_activity,
                status,
                wrapped_dek,
                wrap_nonce,
            ),
        )

    def _ensure_session_info_row(
        self,
        conn: sqlite3.Connection,
        *,
        session_id: str,
    ) -> None:
        session_id = self._canonical_session_id(session_id)
        existing = conn.execute(
            "SELECT 1 FROM session_info WHERE session_id = ? LIMIT 1",
            (session_id,),
        ).fetchone()
        if existing is not None:
            return

        with self._index_connection() as index_conn:
            row = index_conn.execute(
                f"SELECT {self._SESSION_INFO_SELECT_COLUMNS} FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return

        self._write_session_info(
            conn,
            session_id=row["session_id"],
            title=row["title"],
            memory_mode=row["memory_mode"],
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
            last_activity=float(row["last_activity"]),
            status=row["status"],
            wrapped_dek=row["wrapped_dek"],
            wrap_nonce=row["wrap_nonce"],
        )

    def _upsert_session_info_from_index(self, session_id: str) -> None:
        session_id = self._canonical_session_id(session_id)
        with self._index_connection() as conn:
            row = conn.execute(
                f"SELECT {self._SESSION_INFO_SELECT_COLUMNS} FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return
        self._upsert_session_info(
            session_id=row["session_id"],
            title=row["title"],
            memory_mode=row["memory_mode"],
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
            last_activity=float(row["last_activity"]),
            status=row["status"],
            wrapped_dek=row["wrapped_dek"],
            wrap_nonce=row["wrap_nonce"],
        )

    def _load_session_info(self, session_id: str) -> dict[str, object] | None:
        session_id = self._canonical_session_id(session_id)
        path = self._session_db_path(session_id)
        if not path.exists():
            return None

        with self._session_connection(session_id) as conn:
            row = conn.execute(
                f"SELECT {self._SESSION_INFO_SELECT_COLUMNS} FROM session_info WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None

        return {
            "session_id": session_id,
            "title": str(row["title"]).strip() or f"Session {session_id[:8]}",
            "memory_mode": self._safe_memory_mode(row["memory_mode"]).value,
            "created_at": float(row["created_at"]),
            "updated_at": float(row["updated_at"]),
            "last_activity": float(row["last_activity"]),
            "status": str(row["status"]).strip() or "active",
            "wrapped_dek": row["wrapped_dek"],
            "wrap_nonce": row["wrap_nonce"],
        }

    # ------------------------------------------------------------------
    # session lifecycle
    # ------------------------------------------------------------------
    def create_session(self, *, title: str, memory_mode: MemoryMode) -> SessionRecord:
        session_id = str(uuid.uuid4())
        now = time.time()
        data_key = os.urandom(32)
        wrapped_dek, wrap_nonce = self._master_box.wrap_key(data_key)
        self._upsert_index_session(
            session_id=session_id,
            title=title,
            memory_mode=memory_mode.value,
            created_at=now,
            updated_at=now,
            last_activity=now,
            status="active",
            wrapped_dek=wrapped_dek,
            wrap_nonce=wrap_nonce,
        )
        self._ensure_session_db(session_id)
        self._upsert_session_info(
            session_id=session_id,
            title=title,
            memory_mode=memory_mode.value,
            created_at=now,
            updated_at=now,
            last_activity=now,
            status="active",
            wrapped_dek=wrapped_dek,
            wrap_nonce=wrap_nonce,
        )
        return SessionRecord(
            session_id=session_id,
            title=title,
            memory_mode=memory_mode,
            created_at=now,
            updated_at=now,
            last_activity=now,
            status="active",
        )

    def next_session_sequence(self) -> int:
        """Return the next 1-based session number for default naming."""
        with self._index_connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS session_count
                FROM sessions
                WHERE status != 'deleted'
                """
            ).fetchone()
        count = int(row["session_count"]) if row is not None else 0
        return count + 1

    def ensure_session(self, session_id: str, *, memory_mode: MemoryMode) -> SessionRecord:
        session_id = self._canonical_session_id(session_id)
        existing = self.get_session(session_id)
        if existing:
            if existing.memory_mode != memory_mode:
                self.set_session_mode(session_id, memory_mode)
                refreshed = self.get_session(session_id)
                if refreshed:
                    return refreshed
            return existing
        raise MemoryStoreError(f"Unknown session: {session_id}")

    def get_session(self, session_id: str) -> SessionRecord | None:
        session_id = self._canonical_session_id(session_id)
        row = self._fetch_session_row(session_id)
        if row is None:
            return None

        return self._row_to_session_record(row)

    def list_sessions(self, *, limit: int = 50) -> list[SessionRecord]:
        try:
            bounded_limit = max(1, min(int(limit), 5000))
        except (TypeError, ValueError):
            bounded_limit = 50
        with self._index_connection() as conn:
            rows = conn.execute(
                """
                SELECT session_id, title, memory_mode, created_at, updated_at, last_activity, status
                FROM sessions
                WHERE status != 'deleted'
                ORDER BY last_activity DESC
                LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()

        records = [self._row_to_session_record(row) for row in rows]
        return records

    def set_session_mode(self, session_id: str, mode: MemoryMode) -> None:
        session_id = self._canonical_session_id(session_id)
        now = time.time()
        with self._index_connection() as conn:
            result = conn.execute(
                """
                UPDATE sessions
                SET memory_mode = ?, updated_at = ?, last_activity = ?
                WHERE session_id = ?
                """,
                (mode.value, now, now, session_id),
            )
            affected = result.rowcount
        if affected <= 0:
            raise MemoryStoreError(f"Unknown session: {session_id}")
        self._upsert_session_info_from_index(session_id)

    def rename_session(self, session_id: str, *, title: str) -> SessionRecord:
        session_id = self._canonical_session_id(session_id)
        normalized = title.strip()
        if not normalized:
            raise MemoryStoreError("Session title cannot be empty")

        now = time.time()
        with self._index_connection() as conn:
            result = conn.execute(
                """
                UPDATE sessions
                SET title = ?, updated_at = ?, last_activity = ?
                WHERE session_id = ?
                """,
                (normalized, now, now, session_id),
            )
            affected = result.rowcount
        if affected <= 0:
            raise MemoryStoreError(f"Unknown session: {session_id}")

        updated = self.get_session(session_id)
        if updated is None:
            raise MemoryStoreError(f"Unknown session: {session_id}")
        self._upsert_session_info_from_index(session_id)
        return updated

    def delete_session(self, session_id: str) -> None:
        session_id = self._canonical_session_id(session_id)
        with self._dek_cache_lock:
            self._dek_cache.pop(session_id, None)
        with self._index_connection() as conn:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM semantic_index WHERE session_id = ?", (session_id,))

        session_db = self._session_db_path(session_id)
        session_paths = [
            session_db,
            Path(f"{session_db}-wal"),
            Path(f"{session_db}-shm"),
        ]
        for path in session_paths:
            if path.exists():
                path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # session db helpers
    # ------------------------------------------------------------------
    def _session_db_path(self, session_id: str) -> Path:
        session_id = self._canonical_session_id(session_id)
        return self.sessions_dir / f"{session_id}.db"

    def _ensure_session_db(self, session_id: str) -> Path:
        path = self._session_db_path(session_id)
        def _ensure_once() -> None:
            conn = _sqlite_connect(path)
            try:
                self._create_session_schema(conn)
                integrity = conn.execute("PRAGMA integrity_check;").fetchone()
                if integrity and integrity[0] != "ok":
                    raise sqlite3.DatabaseError(
                        f"Integrity check failed: {integrity[0]}"
                    )
            finally:
                conn.close()

        self._with_repair(
            operation=_ensure_once,
            is_recoverable=self._is_recoverable_session_error,
            repair=lambda: self._quarantine_db_family(path),
        )

        self._enforce_permissions(path, is_dir=False)
        return path

    def _connect_session(self, session_id: str) -> sqlite3.Connection:
        path = self._ensure_session_db(session_id)

        def _open() -> sqlite3.Connection:
            conn = _sqlite_connect(path)
            try:
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA foreign_keys=ON;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.execute("PRAGMA secure_delete=ON;")
                self._ensure_session_info_row(conn, session_id=session_id)
                return conn
            except Exception:
                conn.close()
                raise

        def _repair() -> None:
            self._quarantine_db_family(path)
            self._ensure_session_db(session_id)

        return self._with_repair(
            operation=_open,
            is_recoverable=self._is_recoverable_session_error,
            repair=_repair,
        )

    @contextmanager
    def _session_connection(self, session_id: str):
        conn = self._connect_session(session_id)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _get_session_dek(self, session_id: str) -> bytes:
        session_id = self._canonical_session_id(session_id)
        with self._dek_cache_lock:
            cached = self._dek_cache.get(session_id)
        if cached is not None:
            return cached

        with self._index_connection() as conn:
            row = conn.execute(
                "SELECT wrapped_dek, wrap_nonce FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            raise MemoryStoreError(f"Unknown session: {session_id}")

        dek = self._master_box.unwrap_key(row["wrapped_dek"], row["wrap_nonce"])
        with self._dek_cache_lock:
            self._dek_cache[session_id] = dek
        return dek

    def _session_box(self, session_id: str) -> CryptoBox:
        return CryptoBox(self._get_session_dek(session_id))

    # ------------------------------------------------------------------
    # messages and summaries
    # ------------------------------------------------------------------
    def append_message(
        self,
        session_id: str,
        *,
        role: str,
        content: str,
        meta: dict[str, Any] | None = None,
    ) -> SessionMessage:
        now = time.time()
        message_id = str(uuid.uuid4())
        metadata = meta or {}

        with self._session_connection(session_id) as conn:
            row = conn.execute("SELECT COALESCE(MAX(turn_index), -1) AS max_turn FROM messages").fetchone()
            turn_index = int(row["max_turn"]) + 1

            encrypted = self._session_box(session_id).encrypt_text(content, aad=message_id.encode("utf-8"))
            conn.execute(
                """
                INSERT INTO messages (
                    message_id, turn_index, role, content_enc, created_at, token_estimate, meta_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    turn_index,
                    role,
                    encrypted,
                    now,
                    max(1, len(content) // 4),
                    json.dumps(metadata, separators=(",", ":")),
                ),
            )

        self._touch_session(session_id)
        return SessionMessage(
            message_id=message_id,
            role=role,
            content=content,
            created_at=now,
            turn_index=turn_index,
            meta=metadata,
        )

    def list_recent_messages(self, session_id: str, *, limit: int = 10) -> list[SessionMessage]:
        try:
            bounded_limit = max(1, min(int(limit), 5000))
        except (TypeError, ValueError):
            bounded_limit = 10
        with self._session_connection(session_id) as conn:
            rows = conn.execute(
                """
                SELECT message_id, turn_index, role, content_enc, created_at, meta_json
                FROM messages
                ORDER BY turn_index DESC
                LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()

        box = self._session_box(session_id)
        parsed: list[SessionMessage] = []
        for row in rows:
            try:
                message_id = row["message_id"]
                content = box.decrypt_text(row["content_enc"], aad=message_id.encode("utf-8"))
                parsed.append(
                    SessionMessage(
                        message_id=message_id,
                        role=row["role"],
                        content=content,
                        created_at=float(row["created_at"]),
                        turn_index=int(row["turn_index"]),
                        meta=self._safe_json_object(row["meta_json"]),
                    )
                )
            except Exception as exc:
                raise MemoryStoreError(
                    f"Failed to decode recent message {row['message_id']} for session {session_id}"
                ) from exc

        parsed.sort(key=lambda item: item.turn_index)
        return parsed

    def list_messages(self, session_id: str, *, limit: int = 500) -> list[SessionMessage]:
        try:
            bounded_limit = max(1, min(int(limit), 5000))
        except (TypeError, ValueError):
            bounded_limit = 500
        with self._session_connection(session_id) as conn:
            rows = conn.execute(
                """
                SELECT message_id, turn_index, role, content_enc, created_at, meta_json
                FROM messages
                ORDER BY turn_index DESC
                LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()

        box = self._session_box(session_id)
        parsed: list[SessionMessage] = []
        for row in rows:
            try:
                message_id = row["message_id"]
                content = box.decrypt_text(row["content_enc"], aad=message_id.encode("utf-8"))
                parsed.append(
                    SessionMessage(
                        message_id=message_id,
                        role=row["role"],
                        content=content,
                        created_at=float(row["created_at"]),
                        turn_index=int(row["turn_index"]),
                        meta=self._safe_json_object(row["meta_json"]),
                    )
                )
            except Exception as exc:
                raise MemoryStoreError(
                    f"Failed to decode message {row['message_id']} for session {session_id}"
                ) from exc
        parsed.sort(key=lambda item: item.turn_index)
        return parsed

    def upsert_summary(self, session_id: str, *, turn_start: int, turn_end: int, summary: str) -> None:
        now = time.time()
        summary_id = f"summary-{turn_end}"
        box = self._session_box(session_id)
        encrypted = box.encrypt_text(summary, aad=summary_id.encode("utf-8"))

        with self._session_connection(session_id) as conn:
            conn.execute(
                """
                INSERT INTO summaries (summary_id, turn_start, turn_end, summary_enc, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(summary_id) DO UPDATE SET
                    turn_start=excluded.turn_start,
                    turn_end=excluded.turn_end,
                    summary_enc=excluded.summary_enc,
                    created_at=excluded.created_at
                """,
                (summary_id, turn_start, turn_end, encrypted, now),
            )

        self._touch_session(session_id)

    def latest_summary(self, session_id: str) -> str:
        with self._session_connection(session_id) as conn:
            row = conn.execute(
                """
                SELECT summary_id, summary_enc
                FROM summaries
                ORDER BY turn_end DESC, created_at DESC
                LIMIT 1
                """
            ).fetchone()

        if row is None:
            return ""

        box = self._session_box(session_id)
        try:
            return box.decrypt_text(row["summary_enc"], aad=row["summary_id"].encode("utf-8"))
        except Exception as exc:
            raise MemoryStoreError(
                f"Failed to decrypt summary for session {session_id}"
            ) from exc

    def _semantic_hmac_payload(
        self,
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

    def _semantic_hmac_v2(
        self,
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
        payload = self._semantic_hmac_payload(
            memory_id=memory_id,
            kind=kind,
            fact_key=fact_key,
            content_enc=content_enc,
            confidence=confidence,
            source_message_id=source_message_id,
            trust_flags_json=trust_flags_json,
            policy_flags_json=policy_flags_json,
            created_at=created_at,
            updated_at=updated_at,
            is_deleted=is_deleted,
        )
        digest = compute_hmac(self._master_key, payload)
        return f"{self._SEMANTIC_HMAC_PREFIX}{digest}"

    def _verify_semantic_hmac_v2(
        self,
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
        stored_hmac: str,
    ) -> bool:
        if not stored_hmac.startswith(self._SEMANTIC_HMAC_PREFIX):
            return False
        payload = self._semantic_hmac_payload(
            memory_id=memory_id,
            kind=kind,
            fact_key=fact_key,
            content_enc=content_enc,
            confidence=confidence,
            source_message_id=source_message_id,
            trust_flags_json=trust_flags_json,
            policy_flags_json=policy_flags_json,
            created_at=created_at,
            updated_at=updated_at,
            is_deleted=is_deleted,
        )
        return verify_hmac(
            self._master_key,
            payload,
            stored_hmac[len(self._SEMANTIC_HMAC_PREFIX):],
        )

    # ------------------------------------------------------------------
    # semantic memory
    # ------------------------------------------------------------------
    def upsert_semantic_memory(
        self,
        session_id: str,
        *,
        kind: MemoryKind,
        fact_key: str,
        content: str,
        confidence: float,
        source_message_id: str,
        trust_flags: tuple[str, ...],
        policy_flags: tuple[str, ...],
        embedding_service: object | None = None,
    ) -> MemoryRecord:
        now = time.time()
        box = self._session_box(session_id)

        with self._session_connection(session_id) as conn:
            existing = conn.execute(
                """
                SELECT memory_id, confidence, content_enc, created_at
                FROM semantic_memories
                WHERE fact_key = ? AND kind = ? AND is_deleted = 0
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (fact_key, kind.value),
            ).fetchone()

            if existing is not None:
                memory_id = existing["memory_id"]
                old_confidence = float(existing["confidence"])
                if confidence < old_confidence and abs(confidence - old_confidence) > 0.2:
                    confidence = old_confidence
                created_at = float(existing["created_at"])
            else:
                memory_id = str(uuid.uuid4())
                created_at = now

            encrypted = box.encrypt_text(content, aad=memory_id.encode("utf-8"))
            trust_flags_json = json.dumps(list(trust_flags), separators=(",", ":"))
            policy_flags_json = json.dumps(list(policy_flags), separators=(",", ":"))
            digest = self._semantic_hmac_v2(
                memory_id=memory_id,
                kind=kind.value,
                fact_key=fact_key,
                content_enc=encrypted,
                confidence=confidence,
                source_message_id=source_message_id,
                trust_flags_json=trust_flags_json,
                policy_flags_json=policy_flags_json,
                created_at=created_at,
                updated_at=now,
                is_deleted=0,
            )

            conn.execute(
                """
                INSERT INTO semantic_memories (
                    memory_id, kind, fact_key, content_enc, confidence,
                    source_message_id, trust_flags_json, policy_flags_json,
                    created_at, updated_at, is_deleted, hmac
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                ON CONFLICT(memory_id) DO UPDATE SET
                    kind=excluded.kind,
                    fact_key=excluded.fact_key,
                    content_enc=excluded.content_enc,
                    confidence=excluded.confidence,
                    source_message_id=excluded.source_message_id,
                    trust_flags_json=excluded.trust_flags_json,
                    policy_flags_json=excluded.policy_flags_json,
                    updated_at=excluded.updated_at,
                    hmac=excluded.hmac,
                    is_deleted=0
                """,
                (
                    memory_id,
                    kind.value,
                    fact_key,
                    encrypted,
                    confidence,
                    source_message_id,
                    trust_flags_json,
                    policy_flags_json,
                    created_at,
                    now,
                    digest,
                ),
            )

        service = cast("EmbeddingService | None", embedding_service)
        if service is None:
            raise MemoryStoreError(
                "Embedding service is required for semantic memory indexing."
            )
        encoded = encode_text_semantic(content, service, task_type="RETRIEVAL_DOCUMENT")
        with self._index_connection() as conn:
            conn.execute(
                """
                INSERT INTO semantic_index (
                    memory_id, session_id, kind, fact_key,
                    vector_json, token_set_json, confidence, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(memory_id) DO UPDATE SET
                    session_id=excluded.session_id,
                    kind=excluded.kind,
                    fact_key=excluded.fact_key,
                    vector_json=excluded.vector_json,
                    token_set_json=excluded.token_set_json,
                    confidence=excluded.confidence,
                    updated_at=excluded.updated_at
                """,
                (
                    memory_id,
                    session_id,
                    kind.value,
                    fact_key,
                    json.dumps(encoded.vector, separators=(",", ":")),
                    json.dumps(list(dict.fromkeys(encoded.tokens)), separators=(",", ":")),
                    confidence,
                    now,
                ),
            )

        self._touch_session(session_id)

        return MemoryRecord(
            memory_id=memory_id,
            session_id=session_id,
            kind=kind,
            fact_key=fact_key,
            content=content,
            confidence=confidence,
            source_message_id=source_message_id,
            trust_flags=trust_flags,
            policy_flags=policy_flags,
            created_at=created_at,
            updated_at=now,
        )

    def load_records_by_ids(self, memory_ids: list[str]) -> list[MemoryRecord]:
        grouped: dict[str, list[str]] = {}
        with self._index_connection() as conn:
            if not memory_ids:
                return []

            placeholders = ",".join("?" for _ in memory_ids)
            rows = conn.execute(
                f"SELECT memory_id, session_id FROM semantic_index WHERE memory_id IN ({placeholders})",
                tuple(memory_ids),
            ).fetchall()

        for row in rows:
            grouped.setdefault(row["session_id"], []).append(row["memory_id"])

        records: list[MemoryRecord] = []
        for session_id, ids in grouped.items():
            with self._session_connection(session_id) as conn:
                placeholders = ",".join("?" for _ in ids)
                rows = conn.execute(
                    f"""
                    SELECT memory_id, kind, fact_key, content_enc, confidence,
                           source_message_id, trust_flags_json, policy_flags_json,
                           created_at, updated_at, hmac
                    FROM semantic_memories
                    WHERE is_deleted = 0 AND memory_id IN ({placeholders})
                    """,
                    tuple(ids),
                ).fetchall()

            box = self._session_box(session_id)
            for row in rows:
                try:
                    memory_id = row["memory_id"]
                    encrypted = row["content_enc"]
                    if not self._verify_semantic_hmac_v2(
                        memory_id=memory_id,
                        kind=row["kind"],
                        fact_key=row["fact_key"],
                        content_enc=encrypted,
                        confidence=float(row["confidence"]),
                        source_message_id=row["source_message_id"],
                        trust_flags_json=row["trust_flags_json"],
                        policy_flags_json=row["policy_flags_json"],
                        created_at=float(row["created_at"]),
                        updated_at=float(row["updated_at"]),
                        is_deleted=0,
                        stored_hmac=str(row["hmac"]),
                    ):
                        raise MemoryStoreError(
                            f"HMAC verification failed for memory record {memory_id}"
                        )

                    content = box.decrypt_text(encrypted, aad=memory_id.encode("utf-8"))
                    records.append(
                        MemoryRecord(
                            memory_id=memory_id,
                            session_id=session_id,
                            kind=MemoryKind(row["kind"]),
                            fact_key=row["fact_key"],
                            content=content,
                            confidence=float(row["confidence"]),
                            source_message_id=row["source_message_id"],
                            trust_flags=tuple(self._safe_json_array(row["trust_flags_json"])),
                            policy_flags=tuple(self._safe_json_array(row["policy_flags_json"])),
                            created_at=float(row["created_at"]),
                            updated_at=float(row["updated_at"]),
                        )
                    )
                except Exception as exc:
                    raise MemoryStoreError(
                        f"Failed to load memory record {row['memory_id']} for session {session_id}"
                    ) from exc

        id_order = {memory_id: index for index, memory_id in enumerate(memory_ids)}
        records.sort(key=lambda item: id_order.get(item.memory_id, 10**9))
        return records

    def semantic_index_candidates(self, *, limit: int = 500) -> list[dict[str, Any]]:
        with self._index_connection() as conn:
            rows = conn.execute(
                """
                SELECT memory_id, session_id, kind, fact_key, vector_json, token_set_json, confidence
                FROM semantic_index
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [dict(row) for row in rows]

    def list_session_memories(self, session_id: str, *, limit: int = 200) -> list[MemoryRecord]:
        with self._session_connection(session_id) as conn:
            rows = conn.execute(
                """
                SELECT memory_id, kind, fact_key, content_enc, confidence,
                       source_message_id, trust_flags_json, policy_flags_json,
                       created_at, updated_at, hmac
                FROM semantic_memories
                WHERE is_deleted = 0
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        box = self._session_box(session_id)
        records: list[MemoryRecord] = []
        for row in rows:
            try:
                memory_id = row["memory_id"]
                encrypted = row["content_enc"]
                if not self._verify_semantic_hmac_v2(
                    memory_id=memory_id,
                    kind=row["kind"],
                    fact_key=row["fact_key"],
                    content_enc=encrypted,
                    confidence=float(row["confidence"]),
                    source_message_id=row["source_message_id"],
                    trust_flags_json=row["trust_flags_json"],
                    policy_flags_json=row["policy_flags_json"],
                    created_at=float(row["created_at"]),
                    updated_at=float(row["updated_at"]),
                    is_deleted=0,
                    stored_hmac=str(row["hmac"]),
                ):
                    raise MemoryStoreError(
                        f"HMAC verification failed for memory record {memory_id}"
                    )
                content = box.decrypt_text(encrypted, aad=memory_id.encode("utf-8"))
                records.append(
                    MemoryRecord(
                        memory_id=memory_id,
                        session_id=session_id,
                        kind=MemoryKind(row["kind"]),
                        fact_key=row["fact_key"],
                        content=content,
                        confidence=float(row["confidence"]),
                        source_message_id=row["source_message_id"],
                        trust_flags=tuple(self._safe_json_array(row["trust_flags_json"])),
                        policy_flags=tuple(self._safe_json_array(row["policy_flags_json"])),
                        created_at=float(row["created_at"]),
                        updated_at=float(row["updated_at"]),
                    )
                )
            except Exception as exc:
                raise MemoryStoreError(
                    f"Failed to decode memory record {row['memory_id']} for session {session_id}"
                ) from exc
        return records

    def delete_memory(self, session_id: str, memory_id: str) -> bool:
        with self._session_connection(session_id) as conn:
            result = conn.execute(
                """
                UPDATE semantic_memories
                SET is_deleted = 1, updated_at = ?
                WHERE memory_id = ?
                """,
                (time.time(), memory_id),
            )
            changed = result.rowcount > 0

        if changed:
            with self._index_connection() as conn:
                conn.execute("DELETE FROM semantic_index WHERE memory_id = ?", (memory_id,))
            self._touch_session(session_id)
        return changed

    def _touch_session(self, session_id: str) -> None:
        session_id = self._canonical_session_id(session_id)
        now = time.time()
        with self._index_connection() as conn:
            result = conn.execute(
                """
                UPDATE sessions
                SET updated_at = ?, last_activity = ?
                WHERE session_id = ?
                """,
                (now, now, session_id),
            )
        if result.rowcount <= 0:
            raise MemoryStoreError(f"Unknown session: {session_id}")
        with self._session_connection(session_id) as conn:
            info_result = conn.execute(
                """
                UPDATE session_info
                SET updated_at = ?, last_activity = ?
                WHERE session_id = ?
                """,
                (now, now, session_id),
            )
            info_affected = info_result.rowcount
        if info_affected <= 0:
            self._upsert_session_info_from_index(session_id)

    # ------------------------------------------------------------------
    # notes CRUD
    # ------------------------------------------------------------------

    def create_note(
        self,
        session_id: str,
        *,
        content: str,
        source: str = "user",
    ) -> dict[str, object]:
        """Create a new note in a session. Returns the note dict."""
        now = time.time()
        note_id = str(uuid.uuid4())
        box = self._session_box(session_id)
        encrypted = box.encrypt_text(content, aad=note_id.encode("utf-8"))

        with self._session_connection(session_id) as conn:
            conn.execute(
                """
                INSERT INTO notes (note_id, content_enc, is_pinned, created_at, updated_at, is_deleted, source)
                VALUES (?, ?, 0, ?, ?, 0, ?)
                """,
                (note_id, encrypted, now, now, source),
            )
        self._touch_session(session_id)
        return {
            "note_id": note_id,
            "content": content,
            "is_pinned": False,
            "created_at": now,
            "updated_at": now,
            "source": source,
        }

    def list_notes(self, session_id: str, *, limit: int = 200) -> list[dict[str, object]]:
        """List non-deleted notes for a session, pinned first, then by updated_at DESC."""
        try:
            bounded_limit = max(1, min(int(limit), 1000))
        except (TypeError, ValueError):
            bounded_limit = 200

        with self._session_connection(session_id) as conn:
            rows = conn.execute(
                """
                SELECT note_id, content_enc, is_pinned, created_at, updated_at, source
                FROM notes
                WHERE is_deleted = 0
                ORDER BY is_pinned DESC, updated_at DESC
                LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()

        box = self._session_box(session_id)
        notes: list[dict[str, object]] = []
        for row in rows:
            note_id = row["note_id"]
            try:
                content = box.decrypt_text(
                    row["content_enc"], aad=note_id.encode("utf-8")
                )
            except Exception:
                logger.warning("Failed to decrypt note %s in session %s", note_id, session_id)
                continue
            notes.append(
                {
                    "note_id": note_id,
                    "content": content,
                    "is_pinned": bool(row["is_pinned"]),
                    "created_at": float(row["created_at"]),
                    "updated_at": float(row["updated_at"]),
                    "source": row["source"],
                }
            )
        return notes

    def get_note(self, session_id: str, note_id: str) -> dict[str, object] | None:
        """Get a single note by ID. Returns None if not found or deleted."""
        with self._session_connection(session_id) as conn:
            row = conn.execute(
                "SELECT note_id, content_enc, is_pinned, created_at, updated_at, source "
                "FROM notes WHERE note_id = ? AND is_deleted = 0",
                (note_id,),
            ).fetchone()
        if row is None:
            return None
        box = self._session_box(session_id)
        try:
            content = box.decrypt_text(
                row["content_enc"], aad=note_id.encode("utf-8")
            )
        except Exception:
            logger.warning("Failed to decrypt note %s in session %s", note_id, session_id)
            return None
        return {
            "note_id": note_id,
            "content": content,
            "is_pinned": bool(row["is_pinned"]),
            "created_at": float(row["created_at"]),
            "updated_at": float(row["updated_at"]),
            "source": row["source"],
        }

    def update_note(
        self,
        session_id: str,
        note_id: str,
        *,
        content: str | None = None,
        is_pinned: bool | None = None,
        touch_timestamp: float | None = None,
    ) -> dict[str, object] | None:
        """Update a note's content and/or pinned state. Returns updated note or None."""
        now = touch_timestamp if touch_timestamp is not None else time.time()
        box = self._session_box(session_id)

        with self._session_connection(session_id) as conn:
            existing = conn.execute(
                "SELECT note_id, content_enc, is_pinned, created_at, source "
                "FROM notes WHERE note_id = ? AND is_deleted = 0",
                (note_id,),
            ).fetchone()
            if existing is None:
                return None

            new_content_enc = existing["content_enc"]
            try:
                final_content = box.decrypt_text(
                    existing["content_enc"], aad=note_id.encode("utf-8")
                )
            except Exception:
                logger.warning(
                    "Failed to decrypt note %s in session %s during update",
                    note_id,
                    session_id,
                )
                if content is None:
                    # Can't read existing content AND caller didn't provide new content.
                    return None
                # Caller provided new content — we can proceed despite decrypt failure.
                final_content = ""
            if content is not None:
                # Snapshot old content as a version before overwriting
                version_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO note_versions (version_id, note_id, content_enc, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (version_id, note_id, existing["content_enc"], now),
                )
                final_content = content
                new_content_enc = box.encrypt_text(content, aad=note_id.encode("utf-8"))

            final_pinned = bool(existing["is_pinned"])
            if is_pinned is not None:
                final_pinned = is_pinned

            conn.execute(
                """
                UPDATE notes SET content_enc = ?, is_pinned = ?, updated_at = ?
                WHERE note_id = ? AND is_deleted = 0
                """,
                (new_content_enc, int(final_pinned), now, note_id),
            )

        self._touch_session(session_id)
        return {
            "note_id": note_id,
            "content": final_content,
            "is_pinned": final_pinned,
            "created_at": float(existing["created_at"]),
            "updated_at": now,
            "source": existing["source"],
        }

    def delete_note(self, session_id: str, note_id: str) -> bool:
        """Soft-delete a note. Returns True if the note existed and was deleted."""
        now = time.time()
        with self._session_connection(session_id) as conn:
            result = conn.execute(
                "UPDATE notes SET is_deleted = 1, updated_at = ? "
                "WHERE note_id = ? AND is_deleted = 0",
                (now, note_id),
            )
            changed = result.rowcount > 0
            if changed:
                conn.execute(
                    "UPDATE note_images SET is_deleted = 1 "
                    "WHERE note_id = ? AND is_deleted = 0",
                    (note_id,),
                )
        if changed:
            self._touch_session(session_id)
        return changed

    # ------------------------------------------------------------------
    # Note Images
    # ------------------------------------------------------------------

    def create_note_image(
        self,
        session_id: str,
        note_id: str,
        *,
        image_bytes: bytes,
        mime_type: str = "image/png",
        width: int = 0,
        height: int = 0,
        alt_text: str = "",
    ) -> dict[str, object]:
        """Store an encrypted image associated with a note. Returns metadata dict."""
        now = time.time()
        image_id = str(uuid.uuid4())
        box = self._session_box(session_id)
        image_enc = box.encrypt_bytes(image_bytes, aad=image_id.encode("utf-8"))

        with self._session_connection(session_id) as conn:
            note_row = conn.execute(
                "SELECT 1 FROM notes WHERE note_id = ? AND is_deleted = 0",
                (note_id,),
            ).fetchone()
            if note_row is None:
                raise MemoryStoreError(
                    f"Note not found or deleted: {note_id}"
                )
            conn.execute(
                """
                INSERT INTO note_images
                    (image_id, note_id, image_enc, mime_type, width, height, alt_text, created_at, is_deleted)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (image_id, note_id, image_enc, mime_type, width, height, alt_text, now),
            )
        return {
            "image_id": image_id,
            "note_id": note_id,
            "mime_type": mime_type,
            "width": width,
            "height": height,
            "alt_text": alt_text,
            "created_at": now,
        }

    def get_note_image(self, session_id: str, image_id: str) -> dict[str, object] | None:
        """Retrieve a single image including decrypted bytes. Returns None if not found."""
        with self._session_connection(session_id) as conn:
            row = conn.execute(
                "SELECT ni.image_id, ni.note_id, ni.image_enc, ni.mime_type, ni.width, "
                "ni.height, ni.alt_text, ni.created_at "
                "FROM note_images ni "
                "INNER JOIN notes n ON n.note_id = ni.note_id "
                "WHERE ni.image_id = ? AND ni.is_deleted = 0 AND n.is_deleted = 0",
                (image_id,),
            ).fetchone()
        if row is None:
            return None

        box = self._session_box(session_id)
        try:
            image_bytes = box.decrypt_bytes(row["image_enc"], aad=row["image_id"].encode("utf-8"))
        except Exception:
            logger.warning("Failed to decrypt image %s in session %s", image_id, session_id)
            return None

        return {
            "image_id": row["image_id"],
            "note_id": row["note_id"],
            "image_data": image_bytes,
            "mime_type": row["mime_type"],
            "width": int(row["width"]),
            "height": int(row["height"]),
            "alt_text": row["alt_text"],
            "created_at": float(row["created_at"]),
        }

    def list_note_images(self, session_id: str, note_id: str) -> list[dict[str, object]]:
        """List metadata for all images attached to a note (no bytes returned)."""
        with self._session_connection(session_id) as conn:
            rows = conn.execute(
                "SELECT ni.image_id, ni.note_id, ni.mime_type, ni.width, ni.height, "
                "ni.alt_text, ni.created_at "
                "FROM note_images ni "
                "INNER JOIN notes n ON n.note_id = ni.note_id "
                "WHERE ni.note_id = ? AND ni.is_deleted = 0 AND n.is_deleted = 0 "
                "ORDER BY ni.created_at ASC",
                (note_id,),
            ).fetchall()
        return [
            {
                "image_id": row["image_id"],
                "note_id": row["note_id"],
                "mime_type": row["mime_type"],
                "width": int(row["width"]),
                "height": int(row["height"]),
                "alt_text": row["alt_text"],
                "created_at": float(row["created_at"]),
            }
            for row in rows
        ]

    def delete_note_images_for_note(self, session_id: str, note_id: str) -> int:
        """Soft-delete all images for a note. Returns count of deleted images."""
        with self._session_connection(session_id) as conn:
            result = conn.execute(
                "UPDATE note_images SET is_deleted = 1 "
                "WHERE note_id = ? AND is_deleted = 0",
                (note_id,),
            )
        return result.rowcount

    # ── note versions ──

    def list_note_versions(
        self, session_id: str, note_id: str, *, limit: int = 50
    ) -> list[dict[str, object]]:
        """List version history for a note (most recent first). Content is decrypted."""
        try:
            bounded_limit = max(1, min(int(limit), 500))
        except (TypeError, ValueError):
            bounded_limit = 50
        box = self._session_box(session_id)
        with self._session_connection(session_id) as conn:
            rows = conn.execute(
                "SELECT version_id, note_id, content_enc, created_at "
                "FROM note_versions WHERE note_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (note_id, bounded_limit),
            ).fetchall()

        versions: list[dict[str, object]] = []
        for row in rows:
            try:
                content = box.decrypt_text(
                    row["content_enc"], aad=row["note_id"].encode("utf-8")
                )
            except Exception:
                content = "(unable to decrypt)"
            versions.append({
                "version_id": row["version_id"],
                "note_id": row["note_id"],
                "content": content,
                "created_at": float(row["created_at"]),
            })
        return versions
