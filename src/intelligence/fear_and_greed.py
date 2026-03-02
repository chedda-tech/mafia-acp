"""Handler for the fear_and_greed ACP job.

Simplest job — returns current F&G data from cache.
Service-only (no fund transfer), $0.10, 30s SLA.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from virtuals_acp.models import ACPJobPhase

if TYPE_CHECKING:
    from virtuals_acp.client import VirtualsACP
    from virtuals_acp.job import ACPJob
    from virtuals_acp.memo import ACPMemo

    from src.data.cache import DataCache

logger = logging.getLogger(__name__)


def handle_fear_and_greed(
    job: ACPJob,
    memo_to_sign: ACPMemo,
    cache: DataCache,
    acp_client: VirtualsACP,
) -> None:
    """Handle a fear_and_greed job through all phases."""
    phase = memo_to_sign.next_phase

    if phase == ACPJobPhase.NEGOTIATION:
        _handle_negotiation(job, memo_to_sign)
    elif phase == ACPJobPhase.TRANSACTION:
        _handle_transaction(job, memo_to_sign, cache)
    elif phase == ACPJobPhase.EVALUATION:
        # Buyer evaluates our deliverable — auto-approve
        memo_to_sign.sign(approved=True, reason="Deliverable accepted")
    else:
        logger.warning("Unexpected phase %s for fear_and_greed job %d", phase, job.id)


def _handle_negotiation(job: ACPJob, memo_to_sign: ACPMemo) -> None:
    """Accept the job — no input required for F&G."""
    logger.info("Accepting fear_and_greed job %d", job.id)
    job.accept(reason="Fear & Greed data ready for delivery")


def _handle_transaction(job: ACPJob, memo_to_sign: ACPMemo, cache: DataCache) -> None:
    """Fetch data from cache and deliver."""
    if cache.is_stale():
        logger.warning("Cache is stale for job %d — delivering with stale data warning", job.id)

    data = cache._data  # Direct access since we're in sync context

    deliverable = json.dumps({
        "fear_and_greed": data.fg_value,
        "classification": data.fg_classification,
        "change_1h": data.fg_change_1h,
        "change_24h": data.fg_change_24h,
        "change_7d": data.fg_change_7d,
        "change_30d": data.fg_change_30d,
        "timestamp": datetime.now(UTC).isoformat(),
        "source": "mafia_terminal",
    })

    logger.info(
        "Delivering fear_and_greed job %d: F&G=%d (%s)",
        job.id,
        data.fg_value,
        data.fg_classification,
    )
    job.deliver(deliverable)
