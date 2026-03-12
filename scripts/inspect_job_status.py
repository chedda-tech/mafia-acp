"""Inspect an ACP job status and memo timeline using local project credentials.

Usage:
    uv run python scripts/inspect_job_status.py --job-id 1002898422
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from virtuals_acp.client import VirtualsACP
from virtuals_acp.configs.configs import (
    BASE_MAINNET_ACP_X402_CONFIG_V2,
    BASE_SEPOLIA_ACP_X402_CONFIG_V2,
)
from virtuals_acp.contract_clients.contract_client_v2 import ACPContractClientV2

# Ensure project root is on sys.path when running as a script.
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent.config import Settings


def _enum_name(value: Any) -> str:
    """Render enum-like values consistently for logs."""
    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name
    return str(value)


def _build_client(settings: Settings) -> VirtualsACP:
    if settings.acp_network == "mainnet":
        acp_config = BASE_MAINNET_ACP_X402_CONFIG_V2
    else:
        acp_config = BASE_SEPOLIA_ACP_X402_CONFIG_V2

    contract_client = ACPContractClientV2(
        agent_wallet_address=settings.agent_wallet_address,
        wallet_private_key=settings.whitelisted_wallet_private_key,
        entity_id=settings.entity_id,
        config=acp_config,
    )

    return VirtualsACP(
        acp_contract_clients=contract_client,
        on_new_task=lambda *args, **kwargs: None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect ACP job status and memos")
    parser.add_argument("--job-id", type=int, required=True, help="On-chain job id")
    args = parser.parse_args()

    settings = Settings()
    client = _build_client(settings)
    job = client.get_job_by_onchain_id(args.job_id)

    print("=== Job Summary ===")
    print(f"network: {settings.acp_network}")
    print(f"job_id: {getattr(job, 'id', None)}")
    print(f"name: {getattr(job, 'name', None)}")
    print(f"phase: {_enum_name(getattr(job, 'phase', None))}")
    print(f"rejection_reason: {getattr(job, 'rejection_reason', None)}")
    print(f"memo_count: {len(getattr(job, 'memos', []))}")

    print("\n=== Memos ===")
    for memo in getattr(job, "memos", []):
        memo_id = getattr(memo, "id", None)
        memo_type = _enum_name(getattr(memo, "memo_type", None))
        status = _enum_name(getattr(memo, "status", None))
        next_phase = _enum_name(getattr(memo, "next_phase", None))
        sender = getattr(memo, "sender", None)
        receiver = getattr(memo, "receiver", None)
        print(
            "- "
            f"id={memo_id} "
            f"type={memo_type} "
            f"status={status} "
            f"next_phase={next_phase} "
            f"sender={sender} "
            f"receiver={receiver}"
        )


if __name__ == "__main__":
    main()
