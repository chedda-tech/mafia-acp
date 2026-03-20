"""Tests for IdempotencyStore — deduplication and job locking (SQLite backend).

The SQLite backend is used in local dev and is the reference implementation.
These tests validate the correctness that production relies on.
"""

import pytest

from src.data.idempotency import IdempotencyStore


@pytest.fixture
def store(tmp_path):
    return IdempotencyStore(str(tmp_path / "test_idempotency.db"))


class TestClaimMemo:
    def test_first_claim_returns_true(self, store):
        assert store.claim_memo(memo_id=1, job_id=10, phase="REQUEST") is True

    def test_duplicate_claim_returns_false(self, store):
        store.claim_memo(memo_id=1, job_id=10, phase="REQUEST")
        assert store.claim_memo(memo_id=1, job_id=10, phase="REQUEST") is False

    def test_duplicate_across_phases_still_blocked(self, store):
        """Memo ID is globally unique — same ID in a different phase is still a duplicate."""
        store.claim_memo(memo_id=5, job_id=10, phase="REQUEST")
        assert store.claim_memo(memo_id=5, job_id=10, phase="TRANSACTION") is False

    def test_different_memo_ids_are_independent(self, store):
        assert store.claim_memo(memo_id=1, job_id=10, phase="REQUEST") is True
        assert store.claim_memo(memo_id=2, job_id=10, phase="REQUEST") is True

    def test_different_jobs_same_memo_id_blocked(self, store):
        """Memo IDs are global — same ID for a different job still blocked."""
        store.claim_memo(memo_id=99, job_id=10, phase="REQUEST")
        assert store.claim_memo(memo_id=99, job_id=20, phase="REQUEST") is False


class TestJobLocks:
    def test_fresh_lock_acquired(self, store):
        assert store.acquire_job_lock(job_id=1, owner_id="worker-a", ttl_seconds=60) is True

    def test_active_lock_blocks_other_owner(self, store):
        store.acquire_job_lock(job_id=1, owner_id="worker-a", ttl_seconds=60)
        assert store.acquire_job_lock(job_id=1, owner_id="worker-b", ttl_seconds=60) is False

    def test_active_lock_blocks_same_owner(self, store):
        """Reacquire on active lock is also blocked — prevents double threads."""
        store.acquire_job_lock(job_id=1, owner_id="worker-a", ttl_seconds=60)
        assert store.acquire_job_lock(job_id=1, owner_id="worker-a", ttl_seconds=60) is False

    def test_expired_lock_can_be_taken_over(self, store):
        """ttl=0 means lock expires immediately; next acquire should succeed."""
        store.acquire_job_lock(job_id=1, owner_id="worker-a", ttl_seconds=0)
        assert store.acquire_job_lock(job_id=1, owner_id="worker-b", ttl_seconds=60) is True

    def test_different_job_ids_independent(self, store):
        assert store.acquire_job_lock(job_id=1, owner_id="worker-a", ttl_seconds=60) is True
        assert store.acquire_job_lock(job_id=2, owner_id="worker-a", ttl_seconds=60) is True

    def test_renew_by_owner_returns_true(self, store):
        store.acquire_job_lock(job_id=1, owner_id="worker-a", ttl_seconds=60)
        assert store.renew_job_lock(job_id=1, owner_id="worker-a", ttl_seconds=120) is True

    def test_renew_by_wrong_owner_returns_false(self, store):
        store.acquire_job_lock(job_id=1, owner_id="worker-a", ttl_seconds=60)
        assert store.renew_job_lock(job_id=1, owner_id="worker-b", ttl_seconds=120) is False

    def test_renew_nonexistent_lock_returns_false(self, store):
        assert store.renew_job_lock(job_id=999, owner_id="worker-a", ttl_seconds=60) is False

    def test_release_allows_reacquire_by_new_owner(self, store):
        store.acquire_job_lock(job_id=1, owner_id="worker-a", ttl_seconds=60)
        store.release_job_lock(job_id=1, owner_id="worker-a")
        assert store.acquire_job_lock(job_id=1, owner_id="worker-b", ttl_seconds=60) is True

    def test_release_by_wrong_owner_leaves_lock_intact(self, store):
        """Only the lock owner can release it."""
        store.acquire_job_lock(job_id=1, owner_id="worker-a", ttl_seconds=60)
        store.release_job_lock(job_id=1, owner_id="worker-b")  # wrong owner, no-op
        assert store.acquire_job_lock(job_id=1, owner_id="worker-c", ttl_seconds=60) is False

    def test_release_nonexistent_lock_is_safe(self, store):
        """Releasing a non-existent lock should not raise."""
        store.release_job_lock(job_id=999, owner_id="worker-a")  # should not raise
