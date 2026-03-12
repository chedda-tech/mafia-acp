"""Durable idempotency ledger and job lock store.

This store prevents duplicate callback processing when ACP/socket delivery is at-least-once.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path


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
