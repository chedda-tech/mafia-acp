"""Handler for the market_sentiment ACP job.

Full market intelligence report combining F&G, BTC dominance, asset metrics,
signal detection, and AI-generated narrative.
Service-only (no fund transfer), $0.25, 60s SLA.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from virtuals_acp.models import ACPJobPhase, ACPMemoStatus

from src.data.models import MarketDataCache, format_market_cap
from src.intelligence.ai_narrator import generate_narrative
from src.intelligence.signal_detector import detect_signals

if TYPE_CHECKING:
    from virtuals_acp.client import VirtualsACP
    from virtuals_acp.job import ACPJob
    from virtuals_acp.memo import ACPMemo

    from src.data.cache import DataCache

logger = logging.getLogger(__name__)

DEFAULT_FOCUS_ASSETS = ["BTC", "ETH", "SOL"]

# Very lightweight memory lock to prevent duplicate websocket deliveries
_DELIVERED_JOBS: set[int] = set()
_DELIVERED_JOBS_LOCK = threading.Lock()


def handle_market_sentiment(
    job: ACPJob,
    memo_to_sign: ACPMemo | None,
    cache: DataCache,
    acp_client: VirtualsACP,
) -> None:
    """Handle a market_sentiment job through all phases."""
    phase = job.phase

    if phase == ACPJobPhase.REQUEST:
        if memo_to_sign is None:
            return
        logger.info("Accepting market_sentiment job %d", job.id)
        job.accept(reason="Market intelligence report ready for generation")

        # Start a background poller just like fear_and_greed to reliably push the job forward
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
                return

        import threading

        threading.Thread(
            target=_poll_and_deliver,
            args=(job.id, cache, acp_client, owner_id, lock_ttl),
            daemon=True,
        ).start()
    elif phase == ACPJobPhase.NEGOTIATION:
        if memo_to_sign and memo_to_sign.status == ACPMemoStatus.PENDING:
            memo_to_sign.sign(approved=True, reason="Negotiation acknowledged")
    elif phase == ACPJobPhase.TRANSACTION:
        # Reached if onNewTask ever fires for TRANSACTION
        _handle_transaction(job, cache, acp_client)
    elif phase == ACPJobPhase.EVALUATION:
        if memo_to_sign:
            memo_to_sign.sign(approved=True, reason="Deliverable accepted")


def _poll_and_deliver(
    job_id: int,
    cache: DataCache,
    acp_client: VirtualsACP,
    owner_id: str,
    lock_ttl_seconds: int,
) -> None:
    """Background: poll job state until TRANSACTION phase, then deliver."""
    import time

    store = getattr(acp_client, "_idempotency_store", None)
    max_attempts = 24
    try:
        for attempt in range(max_attempts):
            time.sleep(5)
            try:
                if store is not None:
                    renewed = store.renew_job_lock(
                        job_id=int(job_id),
                        owner_id=owner_id,
                        ttl_seconds=lock_ttl_seconds,
                    )
                    if not renewed:
                        return

                fresh_job = acp_client.get_job_by_onchain_id(job_id)
                pending_memos = [
                    m
                    for m in getattr(fresh_job, "memos", [])
                    if getattr(m, "status", None) == ACPMemoStatus.PENDING
                ]

                if fresh_job.phase == ACPJobPhase.NEGOTIATION and not pending_memos:
                    logger.info(
                        "[poll] Job %d in NEGOTIATION with no pending memos; creating requirement",
                        job_id,
                    )
                    try:
                        fresh_job.create_requirement(
                            "Market sentiment report ready. Proceed to transaction."
                        )
                    except Exception as req_e:
                        logger.error(
                            "[poll] Failed to create requirement for job %d: %s", job_id, req_e
                        )

                if fresh_job.phase == ACPJobPhase.TRANSACTION:
                    try:
                        _handle_transaction(fresh_job, cache, acp_client)
                    except Exception as handle_e:
                        logger.error(
                            "[poll] error delivering logic for job %d: %s", job_id, handle_e
                        )
                    return
                if fresh_job.phase in (
                    ACPJobPhase.COMPLETED,
                    ACPJobPhase.REJECTED,
                    ACPJobPhase.EXPIRED,
                ):
                    return
            except Exception as e:
                logger.error("[poll] error fetching job %d: %s", job_id, e)
    finally:
        if store is not None:
            store.release_job_lock(job_id=int(job_id), owner_id=owner_id)


def _handle_transaction(job: ACPJob, cache: DataCache, acp_client: VirtualsACP) -> None:
    """Build the full market sentiment report and deliver."""
    with _DELIVERED_JOBS_LOCK:
        if job.id in _DELIVERED_JOBS:
            return
        _DELIVERED_JOBS.add(job.id)

    # Parse requirements
    reqs = _parse_requirements(job)
    focus_assets = reqs.get("focus_assets", DEFAULT_FOCUS_ASSETS)
    include_analysis = reqs.get("include_analysis", True)

    if cache.is_stale():
        logger.warning("Cache is stale for market_sentiment job %d", job.id)

    data = cache._data  # Direct access in sync context

    # Build the report
    report = _build_report(data, focus_assets, include_analysis)

    logger.info("Delivering market_sentiment job %d", job.id)
    job.deliver(json.dumps(report))


def _parse_requirements(job: ACPJob) -> dict:
    """Extract user requirements from job context."""
    context = job.context
    if not context:
        return {}
    if isinstance(context, str):
        try:
            return json.loads(context)
        except json.JSONDecodeError:
            return {}
    if isinstance(context, dict):
        # Requirements may be nested
        req = context.get("requirement", context)
        if isinstance(req, str):
            try:
                return json.loads(req)
            except json.JSONDecodeError:
                return {}
        return req if isinstance(req, dict) else {}
    return {}


def _build_report(
    data: MarketDataCache,
    focus_assets: list[str],
    include_analysis: bool,
) -> dict:
    """Assemble the complete market sentiment report."""
    now = datetime.now(UTC)

    report: dict = {
        "timestamp": now.isoformat(),
        "fear_and_greed": {
            "value": data.fg_value,
            "classification": data.fg_classification,
            "change_24h": data.fg_change_24h,
            "change_7d": data.fg_change_7d,
            "change_30d": data.fg_change_30d,
        },
        "btc_dominance": {
            "value": data.btc_dominance,
            "change_24h": data.btc_dominance_change_24h,
            "trend": _dominance_trend(data.btc_dominance_change_24h),
        },
        "total_market_cap": {
            "value_usd": format_market_cap(data.total_market_cap),
            "change_24h": data.total_market_cap_change_24h,
            "change_7d": data.total_market_cap_change_7d,
        },
        "assets": [
            asset_data
            for symbol in focus_assets
            if (asset_data := data.get_asset_data(symbol)) is not None
        ],
        "source": "mafia_terminal",
    }

    # Signal detection and AI analysis
    if include_analysis:
        signals = detect_signals(data)
        # Run async narrative in a sync context
        from src.agent.config import Settings

        settings = Settings()

        try:
            analysis = asyncio.run(
                generate_narrative(
                    data,
                    signals,
                    base_url=settings.llm_base_url,
                    api_key=settings.llm_api_key,
                    model=settings.llm_model,
                )
            )
        except Exception as e:
            logger.error("Failed to generate market narrative: %s", e)
            analysis = "Analysis temporarily unavailable."

        report["analysis"] = analysis
    else:
        report["analysis"] = None

    return report


def _dominance_trend(change_24h: float) -> str:
    """Classify BTC dominance trend."""
    if change_24h > 0.3:
        return "rising"
    elif change_24h < -0.3:
        return "falling"
    return "stable"
