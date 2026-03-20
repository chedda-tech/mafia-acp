"""Handler for the fear_and_greed ACP job.

Simplest job — returns current F&G data from cache.
Service-only (no fund transfer), $0.10, 30s SLA.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from virtuals_acp.models import ACPJobPhase, ACPMemoStatus

if TYPE_CHECKING:
    from virtuals_acp.client import VirtualsACP
    from virtuals_acp.job import ACPJob
    from virtuals_acp.memo import ACPMemo

from src.data.cache import DataCache
from src.intelligence.signal_detector import map_market_regime

logger = logging.getLogger(__name__)

# Very lightweight memory lock to prevent duplicate websocket deliveries
_DELIVERED_JOBS: set[int] = set()
_DELIVERED_JOBS_LOCK = threading.Lock()


def handle_fear_and_greed(
    job: ACPJob,
    memo_to_sign: ACPMemo | None,
    cache: DataCache,
    acp_client: VirtualsACP,
) -> None:
    """Handle a fear_and_greed job through all phases.

    Dispatch on job.phase (current phase), matching the official SDK pattern.
    ACP backend does NOT send onNewTask for TRANSACTION — confirmed empirically.
    TRANSACTION delivery is handled by a background polling thread spawned after accept.
    """
    phase = job.phase
    actionable = memo_to_sign is not None and memo_to_sign.status == ACPMemoStatus.PENDING

    if phase == ACPJobPhase.REQUEST:
        if memo_to_sign is None:
            logger.warning("REQUEST phase but no memo_to_sign for job %d", job.id)
            return
        _handle_negotiation(job, memo_to_sign, cache, acp_client)
    elif phase == ACPJobPhase.NEGOTIATION:
        _handle_negotiation_phase(job, memo_to_sign)
    elif phase == ACPJobPhase.TRANSACTION:
        # Reached if onNewTask ever fires for TRANSACTION (belt-and-suspenders)
        _handle_transaction(job, memo_to_sign, cache)
    elif phase == ACPJobPhase.EVALUATION:
        if memo_to_sign is not None:
            memo_to_sign.sign(approved=True, reason="Deliverable accepted")
        else:
            logger.warning("EVALUATION phase but no memo_to_sign for job %d", job.id)
    else:
        logger.warning(
            "Unexpected phase %s for fear_and_greed job %d (actionable=%s)",
            phase,
            job.id,
            actionable,
        )


def _handle_negotiation_phase(job: ACPJob, memo_to_sign: ACPMemo | None) -> None:
    """Handle follow-up NEGOTIATION callbacks that may require our signature."""
    if memo_to_sign is None:
        logger.info(
            "NEGOTIATION phase for job %d but no memo_to_sign; relying on background poller to create requirement.",
            job.id,
        )
        return

    if memo_to_sign.status != ACPMemoStatus.PENDING:
        logger.info(
            "NEGOTIATION memo for job %d is not pending (status=%s); no action",
            job.id,
            memo_to_sign.status,
        )
        return

    logger.info(
        "Signing NEGOTIATION memo %s for job %d to advance to %s",
        memo_to_sign.id,
        job.id,
        memo_to_sign.next_phase,
    )
    memo_to_sign.sign(approved=True, reason="Negotiation acknowledged")


def _handle_negotiation(
    job: ACPJob,
    memo_to_sign: ACPMemo,
    cache: DataCache,
    acp_client: VirtualsACP,
) -> None:
    """Accept the job and explicitly create the requirement memo to push it to TRANSACTION.

    ACP backend does NOT send onNewTask for TRANSACTION — confirmed empirically.
    Must poll after accept to detect when Butler pays and then deliver.
    """
    logger.info("Accepting fear_and_greed job %d", job.id)
    job.accept(reason="Fear & Greed data ready for delivery")

    store = getattr(acp_client, "_idempotency_store", None)
    owner_id = getattr(acp_client, "_owner_id", "default")
    lock_ttl = int(getattr(acp_client, "_job_lock_ttl_seconds", 300))
    if store is not None:
        acquired = store.acquire_job_lock(
            job_id=int(job.id),
            owner_id=owner_id,
            ttl_seconds=lock_ttl,
        )
        if not acquired:
            logger.warning(
                "Poller lock already held for job %d; skipping duplicate poll thread",
                job.id,
            )
            return

    threading.Thread(
        target=_poll_and_deliver,
        args=(job.id, cache, acp_client, owner_id, lock_ttl),
        daemon=True,
    ).start()


def _poll_and_deliver(
    job_id: int,
    cache: DataCache,
    acp_client: VirtualsACP,
    owner_id: str,
    lock_ttl_seconds: int,
) -> None:
    """Background: poll job state until TRANSACTION phase, then deliver."""
    import time as _time

    store = getattr(acp_client, "_idempotency_store", None)
    max_attempts = 24  # 24 × 5s = 120s max wait (well within 5min SLA)
    try:
        for attempt in range(max_attempts):
            _time.sleep(5)
            try:
                if store is not None:
                    renewed = store.renew_job_lock(
                        job_id=int(job_id),
                        owner_id=owner_id,
                        ttl_seconds=lock_ttl_seconds,
                    )
                    if not renewed:
                        logger.warning(
                            "[poll] lost job lock for job %d; stopping poller",
                            job_id,
                        )
                        return

                fresh_job = acp_client.get_job_by_onchain_id(job_id)
                pending_memos = [
                    m
                    for m in getattr(fresh_job, "memos", [])
                    if getattr(m, "status", None) == ACPMemoStatus.PENDING
                ]
                pending_summary = [
                    {
                        "id": getattr(m, "id", None),
                        "type": str(getattr(m, "type", None)),
                        "next_phase": str(getattr(m, "next_phase", None)),
                        "sender": getattr(m, "sender", None),
                        "receiver": getattr(m, "receiver", None),
                    }
                    for m in pending_memos
                ]
                latest_memo = (
                    getattr(fresh_job, "memos", [])[-1] if getattr(fresh_job, "memos", []) else None
                )
                logger.info(
                    "[poll] job %d phase=%s (attempt %d/%d) pending_memos=%d pending=%s latest_memo={id:%s status:%s next:%s reason:%r}",
                    job_id,
                    fresh_job.phase,
                    attempt + 1,
                    max_attempts,
                    len(pending_memos),
                    pending_summary,
                    getattr(latest_memo, "id", None),
                    getattr(latest_memo, "status", None),
                    getattr(latest_memo, "next_phase", None),
                    getattr(latest_memo, "signed_reason", None),
                )
                if fresh_job.phase == ACPJobPhase.NEGOTIATION and not pending_memos:
                    logger.info(
                        "[poll] Job %d in NEGOTIATION with no pending memos; creating requirement",
                        job_id,
                    )
                    try:
                        fresh_job.create_requirement(
                            "Fear & Greed data ready. Proceed to transaction."
                        )
                    except Exception as req_e:
                        logger.error(
                            "[poll] Failed to create requirement for job %d: %s", job_id, req_e
                        )

                if fresh_job.phase == ACPJobPhase.TRANSACTION:
                    try:
                        _handle_transaction(fresh_job, None, cache)
                    except Exception as e:
                        logger.error(
                            "[poll] Failed to execute transaction for job %d: %s", job_id, e
                        )
                    return
                if fresh_job.phase in (
                    ACPJobPhase.COMPLETED,
                    ACPJobPhase.REJECTED,
                    ACPJobPhase.EXPIRED,
                ):
                    logger.warning(
                        "[poll] job %d terminal phase %s (reason=%r) — stopping",
                        job_id,
                        fresh_job.phase,
                        getattr(fresh_job, "rejection_reason", None),
                    )
                    return
            except Exception as e:
                logger.error("[poll] error fetching job %d: %s", job_id, e)
        logger.error("[poll] job %d never reached TRANSACTION in %ds", job_id, max_attempts * 5)
    finally:
        if store is not None:
            store.release_job_lock(job_id=int(job_id), owner_id=owner_id)


def _handle_transaction(job: ACPJob, memo_to_sign: ACPMemo | None, cache: DataCache) -> None:
    """Fetch data from cache and deliver."""
    with _DELIVERED_JOBS_LOCK:
        if job.id in _DELIVERED_JOBS:
            return
        _DELIVERED_JOBS.add(job.id)

    if cache.is_stale():
        logger.warning("Cache is stale for job %d — delivering with stale data warning", job.id)

    data = cache._data  # Direct access since we're in sync context
    regimes = map_market_regime(data)

    deliverable = json.dumps(
        {
            "fear_and_greed": data.fg_value,
            "classification": data.fg_classification,
            "change_1h": data.fg_change_1h,
            "change_24h": data.fg_change_24h,
            "change_7d": data.fg_change_7d,
            "change_30d": data.fg_change_30d,
            "regime": regimes["sentiment_regime"],
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "coinmarketcap",
        }
    )

    logger.info(
        "Delivering fear_and_greed job %d: F&G=%d (%s)",
        job.id,
        data.fg_value,
        data.fg_classification,
    )
    job.deliver(deliverable)
