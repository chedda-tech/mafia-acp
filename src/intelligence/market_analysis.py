"""Handler for the market_sentiment ACP job.

Full market intelligence report combining F&G, BTC dominance, asset metrics,
signal detection, and AI-generated narrative.
Service-only (no fund transfer), $0.25, 60s SLA.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from virtuals_acp.models import ACPJobPhase

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


def handle_market_sentiment(
    job: ACPJob,
    memo_to_sign: ACPMemo,
    cache: DataCache,
    acp_client: VirtualsACP,
) -> None:
    """Handle a market_sentiment job through all phases."""
    phase = memo_to_sign.next_phase

    if phase == ACPJobPhase.NEGOTIATION:
        _handle_negotiation(job)
    elif phase == ACPJobPhase.TRANSACTION:
        _handle_transaction(job, cache, acp_client)
    elif phase == ACPJobPhase.EVALUATION:
        memo_to_sign.sign(approved=True, reason="Deliverable accepted")
    else:
        logger.warning("Unexpected phase %s for market_sentiment job %d", phase, job.id)


def _handle_negotiation(job: ACPJob) -> None:
    """Accept the job and parse optional parameters."""
    logger.info("Accepting market_sentiment job %d", job.id)
    job.accept(reason="Market intelligence report ready for generation")


def _handle_transaction(job: ACPJob, cache: DataCache, acp_client: VirtualsACP) -> None:
    """Build the full market sentiment report and deliver."""
    # Parse requirements
    reqs = _parse_requirements(job)
    focus_assets = reqs.get("focus_assets", DEFAULT_FOCUS_ASSETS)
    include_analysis = reqs.get("include_analysis", True)

    if cache.is_stale():
        logger.warning("Cache is stale for market_sentiment job %d", job.id)

    data = cache._data  # Direct access in sync context

    # Build the report
    report = _build_report(data, focus_assets, include_analysis, acp_client)

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
    acp_client: VirtualsACP,
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
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in a thread (ACP callback runs in threads)
                # Create a new loop for this thread
                new_loop = asyncio.new_event_loop()
                try:
                    from src.agent.config import Settings
                    settings = Settings()
                    analysis = new_loop.run_until_complete(
                        generate_narrative(data, signals, settings.anthropic_api_key)
                    )
                finally:
                    new_loop.close()
            else:
                from src.agent.config import Settings
                settings = Settings()
                analysis = loop.run_until_complete(
                    generate_narrative(data, signals, settings.anthropic_api_key)
                )
        except RuntimeError:
            # No event loop — create one
            from src.agent.config import Settings
            settings = Settings()
            analysis = asyncio.run(
                generate_narrative(data, signals, settings.anthropic_api_key)
            )

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
