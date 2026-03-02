"""MAFIA ACP Agent — Main entry point.

Initializes all components and starts the agent:
1. Load config from environment
2. Set up market data feeds (Terminal API + F&G)
3. Initialize ACP client with on_new_task callback
4. Start data feed refresh loop
5. Keep alive until terminated
"""

from __future__ import annotations

import asyncio
import logging
import signal

from virtuals_acp.client import VirtualsACP
from virtuals_acp.configs.configs import BASE_MAINNET_ACP_X402_CONFIG_V2
from virtuals_acp.contract_clients.contract_client_v2 import ACPContractClientV2

from src.agent.config import Settings, setup_logging
from src.agent.router import JobRouter
from src.data.cache import DataCache
from src.data.fear_and_greed import FearAndGreedFeed
from src.data.terminal_feed import TerminalFeed
from src.intelligence.fear_and_greed import handle_fear_and_greed
from src.intelligence.market_analysis import handle_market_sentiment

logger = logging.getLogger(__name__)


def main_sync() -> None:
    """Synchronous entry point (for pyproject.toml scripts)."""
    asyncio.run(main())


async def main() -> None:
    """Start the MAFIA ACP agent."""
    settings = Settings()
    setup_logging(settings.log_level)

    logger.info("Starting MAFIA ACP Agent...")
    logger.info("Entity ID: %s", settings.entity_id)
    logger.info("Agent wallet: %s", settings.agent_wallet_address)

    # --- Data Layer ---
    data_cache = DataCache(stale_threshold_seconds=settings.stale_data_threshold_seconds)
    fg_feed = FearAndGreedFeed(cmc_api_key=settings.coinmarketcap_api_key)
    terminal_feed = TerminalFeed(settings=settings, cache=data_cache, fg_feed=fg_feed)

    # --- Job Router ---
    router = JobRouter(data_cache=data_cache)

    # Register Phase 1 handlers (intelligence jobs)
    router.register_handler("fear_and_greed", handle_fear_and_greed)
    router.register_handler("market_sentiment", handle_market_sentiment)

    # Phase 2 handlers will be registered here:
    # router.register_handler("smart_buy", handle_smart_buy)
    # router.register_handler("take_profit", handle_take_profit)

    # --- ACP Client ---
    logger.info("Initializing ACP client...")
    contract_client = ACPContractClientV2(
        agent_wallet_address=settings.agent_wallet_address,
        wallet_private_key=settings.whitelisted_wallet_private_key,
        entity_id=settings.entity_id,
        config=BASE_MAINNET_ACP_X402_CONFIG_V2,
    )

    # VirtualsACP connects to websocket immediately on init.
    # The on_new_task callback runs in separate threads (not async).
    acp_client = VirtualsACP(
        acp_contract_clients=contract_client,
        on_new_task=router.on_new_task,
    )
    router.set_acp_client(acp_client)

    logger.info("ACP client connected — agent is online")

    # --- Start Data Feed ---
    feed_task = asyncio.create_task(terminal_feed.start())
    logger.info("Data feed started (refresh every %ds)", settings.data_refresh_interval_seconds)

    # --- Keep Alive ---
    shutdown_event = asyncio.Event()

    def handle_shutdown(sig: int, frame: object) -> None:
        logger.info("Shutdown signal received (%s)", sig)
        shutdown_event.set()

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    logger.info("MAFIA ACP Agent is running. Press Ctrl+C to stop.")

    try:
        await shutdown_event.wait()
    finally:
        logger.info("Shutting down...")
        feed_task.cancel()
        await terminal_feed.stop()
        logger.info("MAFIA ACP Agent stopped.")


if __name__ == "__main__":
    asyncio.run(main())
