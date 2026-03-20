# MAFIA AI — Deployment & Instance Isolation Plan

**Status:** Under Implementation
**Target Environment:** Railway

---

## 1. Instance Isolation Strategy (Dev vs. Production)
Because Virtuals ACP uses an active WebSocket connection to listen for jobs, running local code and production code under the same `ENTITY_ID` will cause race conditions and corrupted job lifecycles. We must institute a hard split.

### Action Items:
1. **Create the Dev Agent:** 
   - Register a separate entity named **"MAFIA AI - Dev"** on the ACP Dashboard.
   - Note the secondary `ENTITY_ID` and `AGENT_WALLET_ADDRESS`.
2. **Local Environment Variables:** Switch your local `.env` file to use the Dev agent credentials. 
3. **Environment Toggling (Mainnet vs. Testnet):** 
   - Introduce an `ENVIRONMENT` flag in the codebase.
   - **Local/Dev:** Uses Testnet (`BASE_SEPOLIA_CONFIG_V2`) for mock execution logic.
   - **Production:** Uses Mainnet (`BASE_MAINNET_CONFIG_V2`).

---

## 2. Codebase Preparation

### Containerization
Railway utilizes Nixpacks by default, but because the project employs `uv` (a much faster top-tier python package manager), a custom `Dockerfile` is required to ensure dependencies map accurately.

**Dockerfile Implementation Scope:**
- Install Base Python 3.11+.
- Add `uv`.
- Copy `pyproject.toml` and `uv.lock`.
- Sync dependencies.
- Define `python -m src.main` as the runtime command.

### State Management & Database

Railway container filesystems are **ephemeral** — any file written to disk is lost on restart or redeploy. The agent persists state to **Supabase PostgreSQL** instead.

#### How storage works

The agent uses a single abstraction called the **Idempotency Store** (`src/data/idempotency.py`). It has two backends selected automatically at startup:

| Environment | Backend | Selection logic |
|-------------|---------|-----------------|
| Local dev | SQLite at `.state/idempotency.db` | `DATABASE_URL` not set |
| Railway / production | Supabase PostgreSQL | `DATABASE_URL` is set |

#### Supabase schema: `mafia_acp`

All tables live in a dedicated `mafia_acp` schema inside your existing Supabase database. **Tables are created automatically on first agent startup** — no manual migration needed.

##### `mafia_acp.processed_memos`

Tracks every ACP memo that has been processed. ACP socket delivery is at-least-once — the same memo can arrive twice. This table ensures each memo is only acted on once.

| Column | Type | Description |
|--------|------|-------------|
| `memo_id` | BIGINT PK | ACP memo ID |
| `job_id` | BIGINT | ACP job this memo belongs to |
| `phase` | TEXT | Job phase when memo was processed (REQUEST, NEGOTIATION, etc.) |
| `claimed_at` | TIMESTAMPTZ | When first processed |
| `last_seen_at` | TIMESTAMPTZ | Updated on duplicate deliveries |

##### `mafia_acp.job_locks`

Short-lived (5 min TTL) per-job locks. Prevents two threads from concurrently processing callbacks for the same job — can happen when a zombie socket and a new socket both receive the same event.

| Column | Type | Description |
|--------|------|-------------|
| `job_id` | BIGINT PK | ACP job ID |
| `owner_id` | TEXT | Hostname + entity_id + wallet — identifies which process holds the lock |
| `acquired_at` | TIMESTAMPTZ | When lock was acquired |
| `expires_at` | TIMESTAMPTZ | Auto-expires after `JOB_LOCK_TTL_SECONDS` (default 300s) |

#### Phase 2 tables (not yet created)

When `smart_buy` / `take_profit` are implemented, the following tables will be added to the same `mafia_acp` schema:
- `monitoring_jobs` — tracks active conditional execution jobs and their state
- `execution_history` — audit trail of completed/expired executions

---

## 3. Railway Deployment Playbook

### Step 1: Initialize Railway Services
1. Login to Railway, select "New Project" → "Deploy from GitHub Repo".
2. Select the `mafia-acp` source.
3. Railway will start its first build immediately using the `Dockerfile` and will fail (this is expected due to missing credentials).

### Step 2: Inject Environment Variables
Go to the Railway Service settings → **Variables** and populate:
```env
# ACP Credentials (production agent)
WHITELISTED_WALLET_PRIVATE_KEY=0x...   # Live wallet private key (0x prefix required)
AGENT_WALLET_ADDRESS=0x...             # Smart contract wallet from ACP portal
ENTITY_ID=19740                        # Integer entity ID from ACP registration
ACP_NETWORK=mainnet

# Database (Supabase — transaction pooler URL)
DATABASE_URL=postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres

# LLM
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=...
LLM_MODEL=deepseek/deepseek-chat

# APIs
MAFIA_API_BASE_URL=https://mafia-api-production.up.railway.app
COINMARKETCAP_API_KEY=...
ANTHROPIC_API_KEY=...
```

> **Note:** Use the **transaction pooler** URL from Supabase (port 6543), not the direct connection or session pooler.

### Step 3: Deployment Verification
1. Trigger a manual Rebuild/Redeploy.
2. Monitor Railway logs to ensure the ACP client establishes the WebSocket connection successfully.
3. Access Virtuals Butler, select the live MAFIA AI Agent (`19740`), and initiate a baseline job (`fear_and_greed`). 
4. Check the Railway container logs for job receipt and verify the Butler interface successfully returns the data.
