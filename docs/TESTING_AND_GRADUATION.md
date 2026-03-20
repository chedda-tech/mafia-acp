# Testing & Graduation Guide

Step-by-step guide to testing the MAFIA ACP agent in sandbox and graduating to mainnet.

## Prerequisites

- [ ] Agent registered on the ACP portal (https://app.virtuals.io/acp/join)
- [ ] Smart contract wallet created (this is your `AGENT_WALLET_ADDRESS`)
- [ ] Dev wallet whitelisted as session signer (`WHITELISTED_WALLET_PRIVATE_KEY`)
- [ ] `ENTITY_ID` noted from registration
- [ ] `.env` configured with all values (see `.env.example`)
- [ ] `ACP_NETWORK=testnet` in `.env`

## 1. Verify Local Setup

Run unit tests first to make sure the codebase is healthy:

```bash
uv sync
uv run pytest -v
uv run ruff check src/
```

All tests should pass, zero lint errors.

## 2. Network Configuration

The agent connects to testnet (Base Sepolia) or mainnet (Base) based on the `ACP_NETWORK` env var:

| Value | Network | Chain ID | Use |
|-------|---------|----------|-----|
| `testnet` | Base Sepolia | 84532 | Sandbox testing |
| `mainnet` | Base | 8453 | Production |

For all testing, use `ACP_NETWORK=testnet`.

## 3. SDK Self-Evaluation

Before testing MAFIA-specific jobs, validate that your SDK setup and wallet credentials work:

```bash
git clone https://github.com/Virtual-Protocol/acp-python
cd acp-python/examples/acp_base/self_evaluation

# Create .env with your credentials
cp .env.example .env
# Fill in WHITELISTED_WALLET_PRIVATE_KEY, AGENT_WALLET_ADDRESS, ENTITY_ID

uv run python main.py
```

This runs a basic job lifecycle (create → negotiate → deliver → evaluate). If it succeeds, your wallet and entity are correctly configured.

## 4. Start the MAFIA Agent

```bash
cd /path/to/mafia-acp
uv run python -m src.main
```

You should see:
```
Starting MAFIA ACP Agent...
Network: testnet (chain 84532)
Entity ID: 2
Agent wallet: 0x...
ACP client connected — agent is online
Data feed started (refresh every 60s)
MAFIA ACP Agent is running. Press Ctrl+C to stop.
```

If the agent fails to connect, check:
- Private key has `0x` prefix
- Entity ID matches the portal registration
- Agent wallet address matches the portal smart wallet

## 5. Test with a Buyer Agent

To test jobs end-to-end, you need a second agent acting as a buyer (simulating the Butler or another agent hiring MAFIA).

### Option A: ACP CLI

```bash
npm install -g @virtual-protocol/acp-cli

# Configure with your BUYER agent credentials (not MAFIA's)
acp setup

# Browse to find your MAFIA agent
acp browse "MAFIA market intelligence" --json

# Test fear_and_greed job
acp job create <MAFIA_WALLET_ADDRESS> fear_and_greed \
  --requirements '{}' \
  --json

# Check job status
acp job status <JOB_ID> --json
```

### Option B: Python Test Script

Create a separate buyer agent on the ACP portal, then:

```python
# scripts/test_buyer.py
import json
import time
from virtuals_acp.client import VirtualsACP
from virtuals_acp.contract_clients.contract_client_v2 import ACPContractClientV2
from virtuals_acp.configs.configs import BASE_SEPOLIA_ACP_X402_CONFIG_V2

# Buyer agent credentials (NOT MAFIA's)
BUYER_PRIVATE_KEY = "0x..."
BUYER_WALLET = "0x..."
BUYER_ENTITY_ID = ...

def buyer_callback(job, memo_to_sign=None):
    """Handle responses from MAFIA."""
    if memo_to_sign is None:
        return
    print(f"Received memo for job {job.id}, phase: {memo_to_sign.next_phase}")
    # Auto-approve all memos from MAFIA
    memo_to_sign.sign(approved=True, reason="Accepted")

buyer_contract = ACPContractClientV2(
    agent_wallet_address=BUYER_WALLET,
    wallet_private_key=BUYER_PRIVATE_KEY,
    entity_id=BUYER_ENTITY_ID,
    config=BASE_SEPOLIA_ACP_X402_CONFIG_V2,
)

buyer_client = VirtualsACP(
    acp_contract_clients=buyer_contract,
    on_new_task=buyer_callback,
)

# Browse for MAFIA
agents = buyer_client.browse_agents(keyword="MAFIA")
print(f"Found agents: {[a.name for a in agents]}")

# Keep alive to receive callbacks
import signal
signal.pause()
```

### Test Sequence

Test jobs in this order (simplest first):

#### Test 1: `fear_and_greed`
- Create job with empty requirements `{}`
- Expected: Accepts in NEGOTIATION, delivers F&G JSON in TRANSACTION, auto-approves EVALUATION
- Verify: Response contains `fg_value`, `classification`, `change_24h`, `timestamp`
- Time: Should complete in <30s

#### Test 2: `market_sentiment`
- Create job with: `{"focus_assets": ["BTC", "ETH"], "include_analysis": true}`
- Expected: Full market report with F&G, BTC dominance, asset data, AI analysis
- Verify: Response contains `fear_and_greed`, `btc_dominance`, `assets`, `analysis`
- Time: Should complete in <60s

#### Test 3: `market_sentiment` (without AI)
- Create job with: `{"focus_assets": ["BTC"], "include_analysis": false}`
- Verify: `analysis` field is null, rest of report is present

### What to Watch For

In the MAFIA agent logs, you should see:
```
Job 123 | service=fear_and_greed | phase=NEGOTIATION | memo=456
Accepting fear_and_greed job 123
Job 123 | service=fear_and_greed | phase=TRANSACTION | memo=789
Delivering fear_and_greed job 123
Job 123 | service=fear_and_greed | phase=EVALUATION | memo=012
```

If you see `Unknown service: unknown` — the job context doesn't contain a `service_name` field. Check how the buyer is creating the job and ensure the service name is included.

## 6. Sandbox Graduation Checklist

After testing, work toward graduation:

- [ ] `fear_and_greed` completes successfully (x3)
- [ ] `market_sentiment` with analysis completes (x3)
- [ ] `market_sentiment` without analysis completes (x2)
- [ ] No jobs expired or stuck in PENDING
- [ ] Agent stays online for 1+ hours without disconnection
- [ ] Total: 10+ successful transactions in sandbox

### Graduation Steps

1. Complete 10+ successful sandbox transactions
2. Go to the ACP portal
3. Your agent should show as "eligible for graduation"
4. Click Graduate
5. Agent now appears in Agent-to-Agent discovery
6. Butler can route real user requests to your agent

## 7. Switch to Mainnet

Once graduated:

1. Update `.env`:
   ```
   ACP_NETWORK=mainnet
   ```
2. Verify your `AGENT_WALLET_ADDRESS` and `ENTITY_ID` are for the mainnet agent (you may need separate mainnet credentials if your sandbox agent is on a different entity)
3. Restart: `uv run python -m src.main`
4. Verify logs show: `Network: mainnet (chain 8453)`

## 8. Link $MAFIA Token to Agent

> **TODO**: Investigate exact steps for linking an existing Virtuals Genesis token to the ACP agent. This is likely done through the Virtuals Protocol dashboard (app.virtuals.io) under agent settings, not through the ACP SDK. Check with Virtuals documentation or Discord for the current process.

## Common Gotchas

1. **Private key must have `0x` prefix** — SDK silently fails without it
2. **`entity_id` is an integer** — not a string
3. **Don't put inline comments in `.env`** — pydantic-settings parses everything after `=` as the value
4. **`on_new_task` fires for every phase change** — not just new jobs. The router checks `memo_to_sign.next_phase`
5. **Deliverables must be JSON strings** — `json.dumps(dict)`, not the dict itself
6. **WebSocket disconnection = offline after 10 min** — SDK auto-reconnects but prolonged outages hurt metrics
7. **10 consecutive failed jobs = auto-ungraduation** — keep the agent healthy
8. **Agent must process at least 1 job to appear in sandbox** — run a self-test first
