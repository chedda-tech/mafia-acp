"""Test script: Send a fear_and_greed job to the MAFIA agent.

Run this in a second terminal while the agent is running:
    uv run python scripts/test_fear_and_greed.py

    # Or from project root if PYTHONPATH issues:
    PYTHONPATH=. uv run python scripts/test_fear_and_greed.py

The buyer agent uses the SAME credentials as MAFIA (self-test).
In a real scenario you'd use a separate buyer wallet.
"""

import json
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from virtuals_acp.client import VirtualsACP
from virtuals_acp.configs.configs import BASE_MAINNET_ACP_X402_CONFIG_V2
from virtuals_acp.contract_clients.contract_client_v2 import ACPContractClientV2
from virtuals_acp.models import ACPMemoStatus

from src.agent.config import Settings

settings = Settings()

received_deliverable = None


def on_new_task(job, memo_to_sign=None):
    """Buyer callback — handle responses from MAFIA."""
    global received_deliverable

    if memo_to_sign is None or memo_to_sign.status != ACPMemoStatus.PENDING:
        return

    phase = memo_to_sign.next_phase
    print(f"[BUYER] Job {job.id} | phase={phase}")

    # Auto-approve all memos
    memo_to_sign.sign(approved=True, reason="Accepted")

    # Check if MAFIA delivered
    for memo in job.memos:
        if memo.content and "fear_and_greed" in str(memo.content):
            try:
                data = json.loads(memo.content)
                if "fear_and_greed" in data:
                    received_deliverable = data
                    print("\n✓ Deliverable received:")
                    print(json.dumps(data, indent=2))
            except Exception:
                pass


print("Connecting buyer to ACP mainnet...")
contract_client = ACPContractClientV2(
    agent_wallet_address=settings.agent_wallet_address,
    wallet_private_key=settings.whitelisted_wallet_private_key,
    entity_id=settings.entity_id,
    config=BASE_MAINNET_ACP_X402_CONFIG_V2,
)

buyer = VirtualsACP(
    acp_contract_clients=contract_client,
    on_new_task=on_new_task,
)

print(f"Looking up MAFIA agent by wallet {settings.agent_wallet_address}...")
mafia = buyer.get_agent(settings.agent_wallet_address)

if mafia is None:
    print("MAFIA agent not found. Make sure it is registered on the ACP portal.")
    raise SystemExit(1)

print(f"\nAgent: {getattr(mafia, 'name', mafia)}")

offerings = getattr(mafia, "job_offerings", [])
print(f"Offerings: {[getattr(o, 'name', str(o)) for o in offerings]}")

fg_offering = next(
    (o for o in offerings if "fear" in getattr(o, "name", "").lower()),
    None,
)

if not fg_offering:
    print("fear_and_greed offering not found on MAFIA agent.")
    raise SystemExit(1)

print(f"\nInitiating fear_and_greed job via offering: {getattr(fg_offering, 'name', fg_offering)}")

job_id = fg_offering.initiate_job(
    service_requirement=json.dumps({}),
)
print(f"Job initiated: {job_id}")
print("Waiting for MAFIA to respond (up to 60s)...")

deadline = time.time() + 60
while time.time() < deadline:
    if received_deliverable:
        print("\n✓ Test PASSED")
        raise SystemExit(0)
    time.sleep(1)

print("\n✗ Timed out — no deliverable received within 60s")
raise SystemExit(1)
