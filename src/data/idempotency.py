"""Durable idempotency ledger and job lock store.

This store prevents duplicate callback processing when ACP/socket delivery is at-least-once.

Two backends:
- IdempotencyStore      — SQLite, for local dev (no DATABASE_URL)
- PostgresIdempotencyStore — PostgreSQL via psycopg2, for Railway/production (DATABASE_URL set)
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class IdempotencyStore:
    """SQLite-backed store for memo claims and per-job locks."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, check_same_thread=False)

    def _init_db(self) -> None:
        path = Path(self._db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_memos (
                    memo_id INTEGER PRIMARY KEY,
                    job_id INTEGER NOT NULL,
                    phase TEXT NOT NULL,
                    claimed_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS job_locks (
                    job_id INTEGER PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    acquired_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )

    def claim_memo(self, memo_id: int, job_id: int, phase: str) -> bool:
        """Claim a memo id for processing exactly once.

        Returns True only for the first claimant.
        """
        now = datetime.now(UTC).isoformat()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO processed_memos
                    (memo_id, job_id, phase, claimed_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (memo_id, job_id, phase, now, now),
            )
            inserted = cur.rowcount == 1
            if not inserted:
                conn.execute(
                    "UPDATE processed_memos SET last_seen_at = ? WHERE memo_id = ?",
                    (now, memo_id),
                )
            return inserted

    def acquire_job_lock(self, job_id: int, owner_id: str, ttl_seconds: int) -> bool:
        """Acquire an expiring per-job lock.

        Returns True only when a new lock is acquired.
        """
        now = datetime.now(UTC)
        expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()
        now_iso = now.isoformat()

        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM job_locks WHERE expires_at <= ?", (now_iso,))

            row = conn.execute(
                "SELECT owner_id FROM job_locks WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO job_locks (job_id, owner_id, acquired_at, expires_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (job_id, owner_id, now_iso, expires_at),
                )
                return True

            return False

    def renew_job_lock(self, job_id: int, owner_id: str, ttl_seconds: int) -> bool:
        """Renew lock expiry if currently held by owner."""
        now = datetime.now(UTC)
        expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE job_locks
                SET expires_at = ?
                WHERE job_id = ? AND owner_id = ?
                """,
                (expires_at, job_id, owner_id),
            )
            return cur.rowcount == 1

    def release_job_lock(self, job_id: int, owner_id: str) -> None:
        """Release lock only if owned by owner_id."""
        with self._lock, self._connect() as conn:
            conn.execute(
                "DELETE FROM job_locks WHERE job_id = ? AND owner_id = ?",
                (job_id, owner_id),
            )


class PostgresIdempotencyStore:
    """PostgreSQL-backed store for Railway/production deployments.

    Identical interface to IdempotencyStore — swap in via factory in main.py.
    Uses a dedicated `mafia_acp` schema to avoid collisions with other tables.
    """

    def __init__(self, database_url: str) -> None:
        import psycopg2
        import psycopg2.extras

        self._database_url = database_url
        self._lock = threading.Lock()
        self._psycopg2 = psycopg2
        self._init_db()

    def _connect(self):
        return self._psycopg2.connect(self._database_url)

    def _init_db(self) -> None:
        logger.info("Initializing PostgreSQL schema (mafia_acp)...")
        with self._lock:
            conn = self._connect()
            try:
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute("CREATE SCHEMA IF NOT EXISTS mafia_acp")
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS mafia_acp.processed_memos (
                            memo_id BIGINT PRIMARY KEY,
                            job_id BIGINT NOT NULL,
                            phase TEXT NOT NULL,
                            claimed_at TIMESTAMPTZ NOT NULL,
                            last_seen_at TIMESTAMPTZ NOT NULL
                        )
                        """
                    )
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS mafia_acp.job_locks (
                            job_id BIGINT PRIMARY KEY,
                            owner_id TEXT NOT NULL,
                            acquired_at TIMESTAMPTZ NOT NULL,
                            expires_at TIMESTAMPTZ NOT NULL
                        )
                        """
                    )
            finally:
                conn.close()
        logger.info("PostgreSQL schema ready (mafia_acp)")

    def claim_memo(self, memo_id: int, job_id: int, phase: str) -> bool:
        """Claim a memo id for processing exactly once. Returns True only for the first claimant."""
        now = datetime.now(UTC)
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO mafia_acp.processed_memos
                        (memo_id, job_id, phase, claimed_at, last_seen_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (memo_id) DO UPDATE SET last_seen_at = EXCLUDED.last_seen_at
                    RETURNING (xmax = 0)
                    """,
                    (memo_id, job_id, phase, now, now),
                )
                row = cur.fetchone()
                return bool(row and row[0])

    def acquire_job_lock(self, job_id: int, owner_id: str, ttl_seconds: int) -> bool:
        """Acquire an expiring per-job lock.

        Returns True when the lock is acquired — either as a fresh insert or by
        overwriting an expired lock. Returns False when a live lock already exists.
        """
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=ttl_seconds)
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                # Atomic upsert: insert if no row exists; overwrite if the existing
                # lock is expired. A live lock causes the WHERE to fail → no row → False.
                cur.execute(
                    """
                    INSERT INTO mafia_acp.job_locks (job_id, owner_id, acquired_at, expires_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (job_id) DO UPDATE
                        SET owner_id    = EXCLUDED.owner_id,
                            acquired_at = EXCLUDED.acquired_at,
                            expires_at  = EXCLUDED.expires_at
                        WHERE mafia_acp.job_locks.expires_at <= EXCLUDED.acquired_at
                    RETURNING true
                    """,
                    (job_id, owner_id, now, expires_at),
                )
                row = cur.fetchone()
                return bool(row)

    def renew_job_lock(self, job_id: int, owner_id: str, ttl_seconds: int) -> bool:
        """Renew lock expiry if currently held by owner."""
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE mafia_acp.job_locks
                    SET expires_at = %s
                    WHERE job_id = %s AND owner_id = %s
                    """,
                    (expires_at, job_id, owner_id),
                )
                return cur.rowcount == 1

    def release_job_lock(self, job_id: int, owner_id: str) -> None:
        """Release lock only if owned by owner_id."""
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM mafia_acp.job_locks WHERE job_id = %s AND owner_id = %s",
                    (job_id, owner_id),
                )
