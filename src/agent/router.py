"""Job routing — the on_new_task callback that ACP calls for every job event.

Routes incoming jobs by service name to the appropriate handler.
Each handler manages its own phase-specific logic.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from virtuals_acp.models import ACPMemoStatus

if TYPE_CHECKING:
    from virtuals_acp.client import VirtualsACP
    from virtuals_acp.job import ACPJob
    from virtuals_acp.memo import ACPMemo

    from src.data.cache import DataCache

logger = logging.getLogger(__name__)

# Type alias for job handlers
JobHandler = Callable[["ACPJob", "ACPMemo", "DataCache", "VirtualsACP"], None]


class JobRouter:
    """Routes incoming ACP jobs to the correct handler by service name."""

    def __init__(self, data_cache: DataCache) -> None:
        self._cache = data_cache
        self._acp_client: VirtualsACP | None = None
        self._handlers: dict[str, JobHandler] = {}

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
        """
        if memo_to_sign is None:
            return
        if memo_to_sign.status != ACPMemoStatus.PENDING:
            return

        assert self._acp_client is not None, "ACP client not set on router"

        # Extract service name from job context
        service_name = self._get_service_name(job)
        phase = memo_to_sign.next_phase

        logger.info(
            "Job %d | service=%s | phase=%s | memo=%d",
            job.id,
            service_name,
            phase.name if hasattr(phase, "name") else phase,
            memo_to_sign.id,
        )

        handler = self._handlers.get(service_name)
        if handler is None:
            logger.warning("Unknown service: %s (job %d) — rejecting", service_name, job.id)
            try:
                job.reject(reason=f"Unknown service: {service_name}")
            except Exception as e:
                logger.error("Failed to reject job %d: %s", job.id, e)
            return

        try:
            handler(job, memo_to_sign, self._cache, self._acp_client)
        except Exception as e:
            logger.error(
                "Handler error for job %d (service=%s, phase=%s): %s",
                job.id,
                service_name,
                phase.name if hasattr(phase, "name") else phase,
                e,
                exc_info=True,
            )
            # Try to reject so the memo doesn't stay pending
            try:
                job.reject(reason=f"Internal error: {str(e)[:200]}")
            except Exception as reject_err:
                logger.error("Failed to reject job %d after error: %s", job.id, reject_err)

    def _get_service_name(self, job: ACPJob) -> str:
        """Extract the service/offering name from job context."""
        context = job.context
        if context and isinstance(context, dict):
            # The context typically contains the service requirement info
            # The service name may be in various places depending on how the job was created
            service_name = context.get("service_name", "")
            if service_name:
                return service_name

            # Try to extract from the first memo's content (requirement memo)
            requirement = context.get("requirement", "")
            if requirement:
                try:
                    req_data = (
                        json.loads(requirement) if isinstance(requirement, str) else requirement
                    )
                    return req_data.get("service_name", "")
                except (json.JSONDecodeError, AttributeError):
                    pass

        # Fallback: check memos for service context
        for memo in job.memos:
            if memo.content:
                try:
                    content = json.loads(memo.content)
                    if isinstance(content, dict) and "service_name" in content:
                        return content["service_name"]
                except (json.JSONDecodeError, AttributeError):
                    pass

        return "unknown"
