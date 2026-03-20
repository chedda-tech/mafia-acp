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
import socket

from virtuals_acp.client import VirtualsACP
from virtuals_acp.configs.configs import (
    BASE_MAINNET_ACP_X402_CONFIG_V2,
    BASE_SEPOLIA_ACP_X402_CONFIG_V2,
)
from virtuals_acp.contract_clients.contract_client_v2 import ACPContractClientV2

from src.agent.config import Settings, setup_logging
from src.agent.router import JobRouter
from src.data.cache import DataCache
from src.data.idempotency import IdempotencyStore, PostgresIdempotencyStore
from src.data.terminal_feed import TerminalFeed
from src.intelligence.fear_and_greed import handle_fear_and_greed
from src.intelligence.market_analysis import handle_market_sentiment

logger = logging.getLogger(__name__)


def main_sync() -> None:
    """Synchronous entry point (for pyproject.toml scripts)."""
    asyncio.run(main())


def _install_socket_event_logger(acp_client: VirtualsACP) -> None:
    """DIAGNOSTIC: log ALL socket.io events (raw) and catch unknown event names."""

    # 1. Wrap handle_new_task to log raw data BEFORE the SDK parses it.
    #    This tells us if onNewTask fires for TRANSACTION but crashes during parsing.
    _orig_handle = acp_client.handle_new_task

    def _logged_handle(data: dict) -> None:
        logger.info(
            "[SOCKET-RAW] onNewTask: job_id=%s phase=%s memo_to_sign=%s memos_count=%d",
            data.get("id"),
            data.get("phase"),
            data.get("memoToSign"),
            len(data.get("memos", [])),
        )
        return _orig_handle(data)

    acp_client.handle_new_task = _logged_handle

    # 2. Catch-all for any socket events NOT already handled by the SDK
    #    (roomJoined, onEvaluate, onNewTask have specific handlers — this catches anything else)
    @acp_client.sio.on("*")
    def _catch_unknown(event: str, data: object) -> None:
        logger.info(
            "[SOCKET-UNKNOWN] event=%r data_keys=%s",
            event,
            list(data.keys()) if isinstance(data, dict) else type(data).__name__,
        )

    logger.info("[DIAG] socket event logger installed")


async def _watch_socket_health(acp_client: VirtualsACP, interval: int = 30) -> None:
    """Log socket.io connection state every `interval` seconds.

    Makes silent NAT-induced disconnections immediately visible in Railway logs.
    """
    while True:
        await asyncio.sleep(interval)
        connected = getattr(acp_client.sio, "connected", None)
        if not connected:
            logger.warning(
                "[SOCKET-HEALTH] socket.io DISCONNECTED (connected=%s) — waiting for auto-reconnect",
                connected,
            )
        else:
            logger.info("[SOCKET-HEALTH] socket.io connected OK")


def _install_prepare_result_logger() -> None:
    """TEMPORARY DIAGNOSTIC: log prepare_result before send_prepared_calls."""
    import json as _json

    from virtuals_acp.alchemy import AlchemyAccountKit

    _orig = AlchemyAccountKit.handle_user_operation

    def _logged(self, calls, capabilities=None):  # type: ignore[no-untyped-def]
        if capabilities is None:
            capabilities = {}
        additional_capabilities = {"maxFeePerGas": {"multiplier": 1.1}}
        capabilities.update(additional_capabilities)

        prepare_result = self.prepare_calls(calls, capabilities)
        logger.info(
            "[DIAG] prepare_result:\n%s",
            _json.dumps(prepare_result, default=str)[:4000],
        )

        result = self.send_prepared_calls(prepare_result)
        logger.info(
            "[DIAG] send_prepared_calls SUCCESS: %s", result.get("preparedCallIds", ["?"])[0]
        )

        try:
            status = self.wait_for_call_status(result["preparedCallIds"][0])
            logger.info("[DIAG] wait_for_call_status OK")
            return status
        except Exception as e:
            logger.warning(
                "[DIAG] wait_for_call_status failed: %s — UserOp submitted, continuing", e
            )
            return result  # UserOp was submitted; best-effort response

    AlchemyAccountKit.handle_user_operation = _logged  # type: ignore[method-assign]
    logger.info("[DIAG] prepare_result logger installed")


async def main() -> None:
    """Start the MAFIA ACP agent."""
    settings = Settings()
    setup_logging(settings.log_level)
    _install_prepare_result_logger()

    # Select ACP network config
    if settings.acp_network == "mainnet":
        acp_config = BASE_MAINNET_ACP_X402_CONFIG_V2
    else:
        acp_config = BASE_SEPOLIA_ACP_X402_CONFIG_V2

    logger.info("Starting MAFIA ACP Agent...")
    logger.info("Network: %s (chain %d)", settings.acp_network, acp_config.chain_id)
    logger.info("Entity ID: %s", settings.entity_id)
    logger.info("Agent wallet: %s", settings.agent_wallet_address)

    # --- Data Layer ---
    data_cache = DataCache(stale_threshold_seconds=settings.stale_data_threshold_seconds)
    if settings.database_url:
        logger.info("Idempotency store: PostgreSQL (Supabase)")
        idempotency_store = PostgresIdempotencyStore(settings.database_url)
    else:
        logger.info("Idempotency store: SQLite (%s)", settings.idempotency_db_path)
        idempotency_store = IdempotencyStore(db_path=settings.idempotency_db_path)
    terminal_feed = TerminalFeed(settings=settings, cache=data_cache)

    # --- Job Router ---
    router = JobRouter(data_cache=data_cache, idempotency_store=idempotency_store)

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
        config=acp_config,
    )

    # VirtualsACP connects to websocket immediately on init.
    # The on_new_task callback runs in separate threads (not async).
    acp_client = VirtualsACP(
        acp_contract_clients=contract_client,
        on_new_task=router.on_new_task,
    )
    owner_id = (
        f"{socket.gethostname()}:{settings.entity_id}:{settings.agent_wallet_address.lower()}"
    )
    setattr(acp_client, "_idempotency_store", idempotency_store)
    setattr(acp_client, "_owner_id", owner_id)
    setattr(acp_client, "_job_lock_ttl_seconds", settings.job_lock_ttl_seconds)
    router.set_acp_client(acp_client)
    _install_socket_event_logger(acp_client)

    # Log the socket.io transport in use (websocket vs polling) — critical for Railway diagnosis
    eio = getattr(acp_client.sio, "eio", None)
    transport_fn = getattr(eio, "transport", None)
    transport_name = transport_fn() if callable(transport_fn) else str(transport_fn or "unknown")
    logger.info("[SOCKET-TRANSPORT] %s", transport_name)

    logger.info("ACP client connected — agent is online")

    # --- Start Data Feed + Socket Health Watcher ---
    feed_task = asyncio.create_task(terminal_feed.start())
    health_task = asyncio.create_task(_watch_socket_health(acp_client))
    logger.info("Data feed started (refresh every %ds)", settings.data_refresh_interval_seconds)

    # --- Keep Alive ---
    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def handle_shutdown(sig: int, frame: object) -> None:
        logger.info("Shutdown signal received (%s)", sig)
        loop.call_soon_threadsafe(shutdown_event.set)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    logger.info("MAFIA ACP Agent is running. Press Ctrl+C to stop.")

    try:
        await shutdown_event.wait()
    finally:
        logger.info("Shutting down...")
        try:
            acp_client.sio.disconnect()
        except Exception:
            pass
        feed_task.cancel()
        health_task.cancel()
        await asyncio.gather(feed_task, health_task, return_exceptions=True)
        await terminal_feed.stop()
        logger.info("MAFIA ACP Agent stopped.")


if __name__ == "__main__":
    asyncio.run(main())
