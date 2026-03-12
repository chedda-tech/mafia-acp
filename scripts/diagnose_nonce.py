"""Diagnostic script: inspect the nonce prepared by Alchemy and compare
it to what the EntryPoint expects on-chain.

Run while the agent is NOT running (uses same credentials):
    uv run python scripts/diagnose_nonce.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from web3 import Web3
from virtuals_acp.alchemy import AlchemyAccountKit, AlchemyRPCClient
from virtuals_acp.configs.configs import BASE_MAINNET_ACP_X402_CONFIG_V2
from virtuals_acp.contract_clients.contract_client_v2 import ACPContractClientV2

from src.agent.config import Settings

settings = Settings()

# ── Monkey-patch RPC client to log all requests/responses ──────────────────
_orig_request = AlchemyRPCClient.request

def _logged_request(self, method, params):
    print(f"\n[RPC] → {method}")
    if method in ("wallet_prepareCalls", "wallet_sendPreparedCalls"):
        print(f"      params: {json.dumps(params, indent=2)[:2000]}")
    try:
        result = _orig_request(self, method, params)
        if method == "wallet_prepareCalls":
            print(f"      result (prepare): {json.dumps(result, indent=2)[:2000]}")
        return result
    except Exception as e:
        print(f"      ERROR: {e}")
        raise

AlchemyRPCClient.request = _logged_request

# ── Connect ─────────────────────────────────────────────────────────────────
print("Initializing contract client...")
contract_client = ACPContractClientV2(
    agent_wallet_address=settings.agent_wallet_address,
    wallet_private_key=settings.whitelisted_wallet_private_key,
    entity_id=settings.entity_id,
    config=BASE_MAINNET_ACP_X402_CONFIG_V2,
)

alchemy_kit: AlchemyAccountKit = contract_client.alchemy_kit
print(f"permissions_context: {alchemy_kit.permissions_context}")

# ── Generate the nonce key the SDK would use ────────────────────────────────
nonce_key_hex = alchemy_kit.get_random_nonce()
nonce_key_int = int(nonce_key_hex, 16)
print(f"\nRandom nonce key (SDK): {nonce_key_hex}")
print(f"  as integer:           {nonce_key_int}")

# ── Query EntryPoint.getNonce on-chain ──────────────────────────────────────
ENTRY_POINT_V07 = "0x0000000071727De22E5E9d8BAf0edAc6f37da032"
ENTRY_POINT_ABI = [
    {
        "inputs": [
            {"name": "sender", "type": "address"},
            {"name": "key", "type": "uint192"},
        ],
        "name": "getNonce",
        "outputs": [{"name": "nonce", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
]

w3 = contract_client.w3
entry_point = w3.eth.contract(
    address=Web3.to_checksum_address(ENTRY_POINT_V07),
    abi=ENTRY_POINT_ABI,
)

# Check nonce for the random key
try:
    nonce_for_random_key = entry_point.functions.getNonce(
        settings.agent_wallet_address, nonce_key_int
    ).call()
    expected_seq = nonce_for_random_key & 0xFFFFFFFFFFFFFFFF  # lower 64 bits
    print(f"\nEntryPoint.getNonce(account, randomKey):")
    print(f"  full nonce:    {nonce_for_random_key}")
    print(f"  sequence:      {expected_seq}  (should be 0 for a fresh key)")
except Exception as e:
    print(f"\nFailed to call EntryPoint.getNonce: {e}")

# Check nonce for key=0 (sequential fallback)
try:
    nonce_key0 = entry_point.functions.getNonce(
        settings.agent_wallet_address, 0
    ).call()
    print(f"\nEntryPoint.getNonce(account, key=0):")
    print(f"  full nonce:    {nonce_key0}")
    print(f"  sequence:      {nonce_key0 & 0xFFFFFFFFFFFFFFFF}")
except Exception as e:
    print(f"\nFailed to call EntryPoint.getNonce(key=0): {e}")

# Check nonce for entity_id as key
try:
    nonce_entity = entry_point.functions.getNonce(
        settings.agent_wallet_address, settings.entity_id
    ).call()
    print(f"\nEntryPoint.getNonce(account, key=entity_id={settings.entity_id}):")
    print(f"  full nonce:    {nonce_entity}")
    print(f"  sequence:      {nonce_entity & 0xFFFFFFFFFFFFFFFF}")
except Exception as e:
    print(f"\nFailed to call EntryPoint.getNonce(entity_id): {e}")

# ── Attempt a prepare_calls with a no-op to see what nonce Alchemy uses ─────
print("\n─────────────────────────────────────────────────")
print("Attempting wallet_prepareCalls with a minimal no-op...")
print("(This will show us the nonce Alchemy actually puts in the UserOperation)")

# Use the real memo ID from the last Butler test.
# Even if the memo/job is already closed, prepare_calls will still build and return
# the prepared UserOperation with a real nonce before simulating execution.
REAL_MEMO_ID = 1009728292
op = contract_client.sign_memo(memo_id=REAL_MEMO_ID, is_approved=True, reason="diagnostic")

try:
    prepare_result = alchemy_kit.prepare_calls([op])
    print("\n✓ prepare_calls succeeded")
    # Extract the nonce from the UserOperation in the prepare result
    user_op = prepare_result.get("userOp") or prepare_result.get("userOperation") or {}
    nonce_in_userop = user_op.get("nonce")
    if nonce_in_userop is not None:
        nonce_int = int(nonce_in_userop, 16) if isinstance(nonce_in_userop, str) else nonce_in_userop
        key = nonce_int >> 64
        seq = nonce_int & 0xFFFFFFFFFFFFFFFF
        print(f"  nonce in UserOp: {nonce_in_userop}")
        print(f"  → key:      {hex(key)}")
        print(f"  → sequence: {seq}")
    else:
        print(f"  prepare_result keys: {list(prepare_result.keys())}")
        print(f"  full prepare_result: {json.dumps(prepare_result, default=str)[:3000]}")
except Exception as e:
    print(f"\n✗ prepare_calls failed: {e}")
    print("  (if 'Job does not exist', try a more recent memo_id from a fresh Butler test)")
