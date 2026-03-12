"""Diagnostic: test whether the agent wallet can submit ANY UserOperation.

Attempts a harmless USDC approve(acp_contract, 0) — approving 0 tokens changes
nothing meaningful but exercises the full prepare_calls → send_prepared_calls path.

Run while the agent is NOT running:
    uv run python scripts/diagnose_send.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from web3 import Web3
from virtuals_acp.alchemy import AlchemyAccountKit, AlchemyRPCClient
from virtuals_acp.configs.configs import BASE_MAINNET_ACP_X402_CONFIG_V2
from virtuals_acp.contract_clients.contract_client_v2 import ACPContractClientV2
from virtuals_acp.models import OperationPayload

from src.agent.config import Settings

settings = Settings()

# ── Monkey-patch RPC to log requests and responses ──────────────────────────
_orig_request = AlchemyRPCClient.request

def _logged_request(self, method, params):
    if method in ("wallet_prepareCalls", "wallet_sendPreparedCalls", "wallet_getCallsStatus"):
        print(f"\n[RPC →] {method}")
        if method != "wallet_getCallsStatus":
            print(json.dumps(params, default=str, indent=2)[:3000])
    try:
        result = _orig_request(self, method, params)
        if method in ("wallet_prepareCalls", "wallet_sendPreparedCalls"):
            print(f"[RPC ←] {method} SUCCESS")
            print(json.dumps(result, default=str, indent=2)[:3000])
        return result
    except Exception as e:
        print(f"[RPC ✗] {method} ERROR: {e}")
        raise

AlchemyRPCClient.request = _logged_request

# ── Connect ──────────────────────────────────────────────────────────────────
print("Connecting to ACP mainnet...")
contract_client = ACPContractClientV2(
    agent_wallet_address=settings.agent_wallet_address,
    wallet_private_key=settings.whitelisted_wallet_private_key,
    entity_id=settings.entity_id,
    config=BASE_MAINNET_ACP_X402_CONFIG_V2,
)

# ── Build a harmless USDC approve(acp_contract, 0) operation ────────────────
# USDC on Base mainnet
USDC_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
# ACP V2 contract (the spender we're approving — approving 0 is a no-op)
ACP_CONTRACT  = BASE_MAINNET_ACP_X402_CONFIG_V2.contract_address

w3 = contract_client.w3
usdc = w3.eth.contract(
    address=Web3.to_checksum_address(USDC_ADDRESS),
    abi=[{
        "name": "approve",
        "type": "function",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount",  "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
    }],
)

calldata = usdc.encode_abi("approve", args=[
    Web3.to_checksum_address(ACP_CONTRACT),
    0,  # approve 0 tokens — completely harmless
])

op = OperationPayload(to=USDC_ADDRESS, data=calldata)

print(f"\nOperation: USDC.approve({ACP_CONTRACT[:10]}..., 0)")
print(f"  to:   {op.to}")
print(f"  data: {op.data[:66]}...")

# ── Submit via handle_operation (same path as job.accept()) ─────────────────
print("\nAttempting handle_operation → send_prepared_calls...")
try:
    result = contract_client.handle_operation([op])
    print("\n✓ SUCCESS — UserOperation was submitted and confirmed!")
    print(json.dumps(result, default=str, indent=2)[:2000])
except Exception as e:
    print(f"\n✗ FAILED: {e}")
