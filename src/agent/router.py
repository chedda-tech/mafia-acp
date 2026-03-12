"""Job routing — the on_new_task callback that ACP calls for every job event.

Routes incoming jobs by service name to the appropriate handler.
Each handler manages its own phase-specific logic.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

from virtuals_acp.models import ACPJobPhase, ACPMemoStatus

if TYPE_CHECKING:
    from virtuals_acp.client import VirtualsACP
    from virtuals_acp.job import ACPJob
    from virtuals_acp.memo import ACPMemo

    from src.data.cache import DataCache
    from src.data.idempotency import IdempotencyStore

logger = logging.getLogger(__name__)

# Process-wide actionable memo guard. This protects against accidental duplicate
# callback wiring where more than one router instance can receive the same memo.
_SEEN_ACTIONABLE_MEMOS: set[int] = set()
_SEEN_ACTIONABLE_MEMOS_LOCK = threading.Lock()

# Type alias for job handlers
JobHandler = Callable[["ACPJob", "ACPMemo | None", "DataCache", "VirtualsACP"], None]


class JobRouter:
    """Routes incoming ACP jobs to the correct handler by service name."""

    def __init__(
        self, data_cache: DataCache, idempotency_store: IdempotencyStore | None = None
    ) -> None:
        self._cache = data_cache
        self._acp_client: VirtualsACP | None = None
        self._handlers: dict[str, JobHandler] = {}
        self._idempotency = idempotency_store

    def set_acp_client(self, client: VirtualsACP) -> None:
        """Set the ACP client after initialization (avoids circular dependency)."""
        self._acp_client = client

    def register_handler(self, service_name: str, handler: JobHandler) -> None:
        """Register a handler for a service name."""
        self._handlers[service_name] = handler
        logger.info("Registered handler for service: %s", service_name)

    def on_new_task(self, job: ACPJob, memo_to_sign: ACPMemo | None = None) -> None:
        """Main callback — ACP calls this for every job phase change.

        CRITICAL: Never leave a PENDING memo unsigned. Always accept or reject.
        Dispatches on job.phase (current phase), matching the official SDK pattern.
        """
        assert self._acp_client is not None, "ACP client not set on router"

        job_phase = job.phase
        phase_name = job_phase.name if hasattr(job_phase, "name") else str(job_phase)
        memo_info = (
            f"memo={memo_to_sign.id} next_phase={memo_to_sign.next_phase} status={memo_to_sign.status}"
            if memo_to_sign is not None
            else "memo=None"
        )
        actionable = memo_to_sign is not None and memo_to_sign.status == ACPMemoStatus.PENDING

        # Extract service name using robust fallbacks.
        service_name, service_source = self._get_service_name(job)

        logger.info(
            "Job %d | service=%s (source=%s) | phase=%s | %s",
            job.id,
            service_name,
            service_source,
            phase_name,
            memo_info,
        )
        if memo_to_sign is not None:
            logger.info(
                "Job %d | memo_actionable=%s | memo_type=%s | sender=%s | receiver=%s",
                job.id,
                actionable,
                getattr(memo_to_sign, "type", None),
                getattr(memo_to_sign, "sender", None),
                getattr(memo_to_sign, "receiver", None),
            )

        if actionable and memo_to_sign is not None:
            memo_id = int(memo_to_sign.id)
            with _SEEN_ACTIONABLE_MEMOS_LOCK:
                if memo_id in _SEEN_ACTIONABLE_MEMOS:
                    logger.warning(
                        "Duplicate actionable memo detected (process-wide); skipping job %d memo %s",
                        job.id,
                        memo_to_sign.id,
                    )
                    return
                _SEEN_ACTIONABLE_MEMOS.add(memo_id)

            if self._idempotency is not None:
                claimed = self._idempotency.claim_memo(
                    memo_id=memo_id,
                    job_id=int(job.id),
                    phase=phase_name,
                )
                logger.info(
                    "Memo claim result job=%d memo=%s claimed=%s",
                    job.id,
                    memo_to_sign.id,
                    claimed,
                )
                if not claimed:
                    logger.warning(
                        "Duplicate actionable memo detected (durable); skipping job %d memo %s",
                        job.id,
                        memo_to_sign.id,
                    )
                    return

        # For REQUEST phase (accepting a job), we need a PENDING NEGOTIATION memo.
        # For all other phases (TRANSACTION, EVALUATION, etc.) proceed regardless —
        # X402 jobs may have memo_to_sign=None or APPROVED in TRANSACTION phase.
        if job_phase == ACPJobPhase.REQUEST:
            if memo_to_sign is None or memo_to_sign.status != ACPMemoStatus.PENDING:
                logger.warning(
                    "Job %d: REQUEST phase but NEGOTIATION memo not pending (%s) — skipping",
                    job.id,
                    memo_info,
                )
                return

        handler = self._handlers.get(service_name)
        if handler is None:
            logger.warning(
                "Unknown service for job %d: service=%s source=%s phase=%s actionable=%s",
                job.id,
                service_name,
                service_source,
                phase_name,
                actionable,
            )
            if actionable and job_phase == ACPJobPhase.REQUEST:
                try:
                    logger.warning("Rejecting job %d due to unknown service during REQUEST", job.id)
                    job.reject(reason=f"Unknown service: {service_name}")
                except Exception as e:
                    logger.error("Failed to reject job %d: %s", job.id, e)
            elif actionable:
                logger.warning(
                    "Not rejecting unknown service for job %d outside REQUEST phase (phase=%s)",
                    job.id,
                    phase_name,
                )
            return

        try:
            logger.info(
                "Dispatching job %d to handler '%s' (phase=%s actionable=%s)",
                job.id,
                service_name,
                phase_name,
                actionable,
            )
            handler(job, memo_to_sign, self._cache, self._acp_client)
        except Exception as e:
            logger.error(
                "Handler error for job %d (service=%s, phase=%s): %s",
                job.id,
                service_name,
                phase_name,
                e,
                exc_info=True,
            )
            # Reject only when a pending memo is actionable.
            if actionable:
                try:
                    logger.warning("Rejecting job %d due to handler exception", job.id)
                    job.reject(reason=f"Internal error: {str(e)[:200]}")
                except Exception as reject_err:
                    logger.error("Failed to reject job %d after error: %s", job.id, reject_err)

    def _get_service_name(self, job: ACPJob) -> tuple[str, str]:
        """Extract the service/offering name from the job.

        Preferred order:
        1. job.get_service_name() when available
        2. job.name parsed from negotiation payload
        3. context fallbacks for legacy/custom payloads
        """
        getter = getattr(job, "get_service_name", None)
        if callable(getter):
            try:
                name = getter()
                if isinstance(name, str) and name:
                    return name, "job.get_service_name"
            except Exception as e:
                logger.debug("job.get_service_name failed for job %s: %s", job.id, e)

        name = getattr(job, "name", None)
        if isinstance(name, str) and name:
            return name, "job.name"

        context = getattr(job, "context", None)
        if isinstance(context, dict):
            for key in ("service_name", "name"):
                candidate = context.get(key)
                if isinstance(candidate, str) and candidate:
                    return candidate, f"job.context.{key}"

            requirement = context.get("requirement")
            if isinstance(requirement, dict):
                for key in ("service_name", "name"):
                    candidate = requirement.get(key)
                    if isinstance(candidate, str) and candidate:
                        return candidate, f"job.context.requirement.{key}"

        return "unknown", "none"
