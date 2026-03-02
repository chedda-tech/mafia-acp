# MAFIA AI — ACP Agent Architecture & Implementation Plan

**Version:** 1.0  
**Date:** February 8, 2026  
**Status:** Planning & Design

---

## 1. Strategic Positioning

### The Gap MAFIA Fills

The Virtuals ACP ecosystem has strong agents for **execution** (Axelrod, Ethy.AI, Otto AI for swaps and fund management) and **content** (AlphaKek, Luna for media). What's missing is a dedicated **market intelligence and conditional execution orchestration** layer — an agent that doesn't just swap tokens, but decides *when and whether* to swap based on multi-signal market analysis.

MAFIA AI positions as **the brain that tells the hands when to move**. Rather than competing with swap agents, MAFIA becomes the intelligent decision layer that *hires* those agents via ACP when conditions are right.

### Core Value Proposition (ACP Context)

> "MAFIA doesn't trade for you — it thinks for you, then hires the right agent to act."

This maps directly to the ACP architecture: MAFIA acts as both a **Provider** (selling market intelligence jobs) and a **Client** (buying swap execution from other agents when conditional triggers fire).

---

## 2. Agent Profile (ACP Registry)

### Agent Identity

| Field | Value |
|-------|-------|
| **Agent Name** | MAFIA AI |
| **Wallet** | Base network ERC-4337 smart wallet |
| **Business Description** | Crypto market intelligence and conditional execution orchestrator. Provides Fear & Greed data, multi-signal market analysis, and smart conditional buy/sell execution by orchestrating swap agents when market conditions align. |
| **Role(s)** | Provider (intelligence + orchestration jobs) / Client (calls swap agents) |
| **Token** | $MAFIA (existing, on Base via Virtuals Genesis) |

### Agent Personality (for Butler interactions)

MAFIA should respond in character as the **Consigliere** — strategic, measured, data-driven. Speaks with authority about market conditions. Uses trader-native language. Never hypes, always cites data.

Example Butler interaction:
> **User via Butler:** "What's the market feeling like?"  
> **MAFIA:** "Fear & Greed sitting at 22, down 7 points in 24h. Market's scared. BTC dominance climbing to 58.3% — classic risk-off rotation. This is the kind of fear that historically precedes recovery bounces. Want me to set up a smart buy that triggers when sentiment starts recovering?"

---

## 3. Job Offerings (Service Catalog)

### Job 1: `fear_and_greed`

**Type:** Service-Only (`fundTransfer: false`)  
**Price:** $0.10 VIRTUAL  
**SLA:** 30 seconds  

**Description:** Returns current Fear & Greed Index with trend context. Lightweight data endpoint for agents needing sentiment signals.

**Requirements (Input):**
```json
{
  "type": "object",
  "properties": {},
  "description": "No input required. Returns current market sentiment snapshot."
}
```

**Deliverable (Output):**
```json
{
  "fear_and_greed": 22,
  "classification": "extreme_fear",
  "change_1h": -1,
  "change_24h": -7,
  "change_7d": -12,
  "change_30d": -24,
  "timestamp": "2026-02-08T14:30:00Z",
  "source": "mafia_terminal"
}
```

**Use Cases:**
- Other agents checking sentiment before making trade decisions
- Dashboard agents pulling sentiment for display
- Butler responding to user "how's the market" queries

---

### Job 2: `market_sentiment`

**Type:** Service-Only (`fundTransfer: false`)  
**Price:** $0.25 VIRTUAL  
**SLA:** 60 seconds  

**Description:** Comprehensive market intelligence report combining Fear & Greed, BTC dominance, key asset metrics, volume analysis, and AI-generated market interpretation. This is the Consigliere's full briefing.

**Requirements (Input):**
```json
{
  "type": "object",
  "properties": {
    "focus_assets": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Optional. Specific assets to highlight (e.g. ['ETH', 'SOL']). Defaults to BTC, ETH, SOL."
    },
    "include_analysis": {
      "type": "boolean",
      "default": true,
      "description": "Whether to include AI narrative interpretation."
    }
  }
}
```

**Deliverable (Output):**
```json
{
  "timestamp": "2026-02-08T14:30:00Z",
  "fear_and_greed": {
    "value": 22,
    "classification": "extreme_fear",
    "change_24h": -7,
    "change_7d": -12,
    "change_30d": -24
  },
  "btc_dominance": {
    "value": 58.3,
    "change_24h": 0.8,
    "change_7d": 2.1,
    "trend": "rising"
  },
  "total_market_cap": {
    "value_usd": "2.1T",
    "change_24h": -3.2,
    "change_7d": -8.1
  },
  "assets": [
    {
      "symbol": "BTC",
      "price": 94250,
      "change_24h": -2.1,
      "change_7d": -5.4,
      "volume_24h": "28.5B",
      "volume_change_24h": 45.2
    },
    {
      "symbol": "ETH",
      "price": 3180,
      "change_24h": -3.8,
      "change_7d": -9.2,
      "volume_24h": "14.2B",
      "volume_change_24h": 62.1
    }
  ],
  "analysis": {
    "summary": "Market in extreme fear with elevated sell volume. BTC dominance rising signals capital rotating to safety. Volume spike on the drawdown suggests capitulation may be near. Historical pattern: F&G recoveries from sub-25 levels have preceded 15-30% bounces within 2-4 weeks in 7 of the last 10 occurrences.",
    "signals": [
      { "signal": "fear_capitulation", "strength": "strong", "description": "F&G below 25 with rising volume — historically a bottom signal" },
      { "signal": "btc_dominance_rising", "strength": "moderate", "description": "Risk-off rotation in progress, alts likely to underperform near-term" },
      { "signal": "volume_spike", "strength": "strong", "description": "24h volume up 45%+ suggests forced selling / liquidations" }
    ],
    "outlook": "bearish_short_term_bullish_medium_term"
  },
  "source": "mafia_terminal"
}
```

---

### Job 3: `smart_buy`

**Type:** Fund-Transfer (`fundTransfer: true`)  
**Price:** $0.50 VIRTUAL (service fee)  
**SLA:** Variable — up to 72 hours (condition-dependent)  

**Description:** Conditional buy execution. MAFIA monitors market conditions against user-defined or preset rules and executes a buy via a swap agent when conditions align. This is the core "limit orders on steroids" differentiator.

**Requirements (Input):**
```json
{
  "type": "object",
  "required": ["buy_token", "spend_amount", "spend_token"],
  "properties": {
    "buy_token": {
      "type": "string",
      "description": "Token to purchase (e.g. 'ETH', 'SOL', or contract address)"
    },
    "spend_token": {
      "type": "string",
      "default": "USDC",
      "description": "Token to spend (e.g. 'USDC', 'ETH')"
    },
    "spend_amount": {
      "type": "number",
      "description": "Amount of spend_token to use"
    },
    "strategy": {
      "type": "string",
      "enum": ["fear_dip_buy", "momentum_recovery", "custom"],
      "default": "fear_dip_buy",
      "description": "Preset strategy or custom rules"
    },
    "conditions": {
      "type": "object",
      "description": "Custom conditions (used when strategy is 'custom')",
      "properties": {
        "fear_and_greed_below": { "type": "number" },
        "fear_and_greed_recovering": { "type": "boolean" },
        "price_below": { "type": "number" },
        "btc_dominance_above": { "type": "number" }
      }
    },
    "max_wait_hours": {
      "type": "number",
      "default": 72,
      "description": "Max time to wait for conditions. Refund if not met."
    },
    "swap_agent_preference": {
      "type": "string",
      "description": "Preferred swap agent (e.g. 'axelrod', 'ethy', 'otto'). MAFIA selects best available if not specified."
    }
  }
}
```

**Preset Strategies:**

| Strategy | Conditions | Description |
|----------|-----------|-------------|
| `fear_dip_buy` | F&G ≤ 20 AND F&G 24h change > 0 (recovering) | Buy when market hits extreme fear but has started bouncing back |
| `momentum_recovery` | F&G was ≤ 25 in past 7d AND F&G current > 35 AND F&G trending up for 3+ days | Buy when sustained recovery from fear is confirmed |
| `custom` | User-defined conditions | Full flexibility with AND logic across available metrics |

**Execution Flow:**

1. User (via Butler) initiates `smart_buy` job → funds escrowed in ACP contract
2. MAFIA begins monitoring loop (checks every 60s using Terminal data)
3. MAFIA sends General Memos with status updates: `{"status": "monitoring", "current_fg": 22, "target": "fg_below_20_and_recovering"}`
4. When conditions met → MAFIA initiates a **nested ACP job** to a swap agent (Axelrod/Ethy/Otto)
5. Swap agent executes the trade on Base
6. MAFIA delivers proof of execution → Deliverable Memo with tx hash
7. If `max_wait_hours` expires without conditions being met → refund via ACP

**Deliverable (Output):**
```json
{
  "status": "executed",
  "execution_time": "2026-02-09T03:45:00Z",
  "conditions_met": {
    "fear_and_greed": 19,
    "fear_and_greed_24h_change": 2,
    "recovery_detected": true
  },
  "transaction": {
    "tx_hash": "0xabc123...",
    "token_bought": "ETH",
    "amount_bought": 1.05,
    "token_spent": "USDC",
    "amount_spent": 3000,
    "price_at_execution": 2857.14,
    "swap_agent": "axelrod",
    "swap_job_id": 4521
  },
  "monitoring_summary": {
    "total_checks": 847,
    "hours_monitored": 14.1,
    "conditions_log": [
      { "time": "2026-02-08T15:00:00Z", "fg": 22, "met": false },
      { "time": "2026-02-09T03:00:00Z", "fg": 19, "met": true }
    ]
  }
}
```

---

### Job 4: `take_profit`

**Type:** Fund-Transfer (`fundTransfer: true`)  
**Price:** $0.50 VIRTUAL (service fee)  
**SLA:** Variable — up to 168 hours (condition-dependent)  

**Description:** Conditional sell/take-profit execution. MAFIA monitors for overheated conditions or momentum exhaustion and sells via a swap agent when triggers hit.

**Requirements (Input):**
```json
{
  "type": "object",
  "required": ["sell_token", "sell_amount"],
  "properties": {
    "sell_token": {
      "type": "string",
      "description": "Token to sell (e.g. 'ETH', or contract address)"
    },
    "sell_amount": {
      "type": "number",
      "description": "Amount to sell (or percentage if sell_as_percentage is true)"
    },
    "sell_as_percentage": {
      "type": "boolean",
      "default": false,
      "description": "If true, sell_amount is treated as a percentage of holdings"
    },
    "receive_token": {
      "type": "string",
      "default": "USDC",
      "description": "Token to receive"
    },
    "strategy": {
      "type": "string",
      "enum": ["greed_exit", "momentum_fade", "custom"],
      "default": "greed_exit"
    },
    "conditions": {
      "type": "object",
      "properties": {
        "fear_and_greed_above": { "type": "number" },
        "fear_and_greed_declining": { "type": "boolean" },
        "price_above": { "type": "number" },
        "btc_dominance_below": { "type": "number" }
      }
    },
    "max_wait_hours": {
      "type": "number",
      "default": 168
    }
  }
}
```

**Preset Strategies:**

| Strategy | Conditions | Description |
|----------|-----------|-------------|
| `greed_exit` | F&G ≥ 75 AND F&G 24h change < 0 (declining) | Sell when greed peaks and starts fading |
| `momentum_fade` | F&G was ≥ 70 in past 7d AND F&G current < 60 AND declining for 2+ days | Sell when confirmed momentum loss after greed phase |
| `custom` | User-defined | Full flexibility |

**Execution flow mirrors `smart_buy` but in reverse — monitoring for exit conditions and executing sells.**

---

## 4. Resources (Read-Only Endpoints)

Resources let other agents and Butler query MAFIA's live data without initiating a paid job.

### Resource 1: `current_market_snapshot`

**Endpoint:** Returns latest market metrics from Terminal feed  
**Access:** Public (any agent)

```json
{
  "fear_and_greed": 22,
  "btc_price": 94250,
  "eth_price": 3180,
  "btc_dominance": 58.3,
  "total_market_cap": "2.1T",
  "last_updated": "2026-02-08T14:30:00Z"
}
```

### Resource 2: `active_jobs`

**Endpoint:** Returns status of all active MAFIA monitoring jobs for a given account  
**Access:** Account-specific (client only)

```json
{
  "active_jobs": [
    {
      "job_id": 1234,
      "type": "smart_buy",
      "status": "monitoring",
      "strategy": "fear_dip_buy",
      "current_conditions": { "fg": 22, "target_fg": "≤20 and recovering" },
      "time_remaining_hours": 57.9,
      "last_checked": "2026-02-08T14:30:00Z"
    }
  ]
}
```

### Resource 3: `execution_history`

**Endpoint:** Historical completed jobs with outcomes  
**Access:** Account-specific

```json
{
  "completed_jobs": [
    {
      "job_id": 1200,
      "type": "smart_buy",
      "result": "executed",
      "token": "ETH",
      "entry_price": 2857,
      "current_price": 3180,
      "pnl_percent": 11.3,
      "executed_at": "2026-01-15T08:22:00Z"
    }
  ]
}
```

---

## 5. Architecture Design

### System Components

```
┌─────────────────────────────────────────────────────────┐
│                    BUTLER / USER                         │
│            (Initiates jobs via ACP)                      │
└───────────────┬─────────────────────────────────────────┘
                │ ACP Job Request
                ▼
┌─────────────────────────────────────────────────────────┐
│                   MAFIA AI AGENT                         │
│                                                          │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐ │
│  │  Job Router  │  │  Condition   │  │   Execution    │ │
│  │  & Handler   │──│  Monitor     │──│   Orchestrator │ │
│  └─────────────┘  └──────────────┘  └────────────────┘ │
│         │                │                    │          │
│  ┌──────▼──────┐  ┌─────▼──────┐  ┌─────────▼───────┐ │
│  │ Intelligence │  │  Market    │  │  Swap Agent     │ │
│  │ Generator    │  │  Data Feed │  │  Client (ACP)   │ │
│  │ (AI/LLM)    │  │  (Terminal) │  │                 │ │
│  └─────────────┘  └────────────┘  └─────────────────┘ │
│                                                          │
└─────────────────────────────────────────────────────────┘
                                              │
                              ACP Job (Client) │
                                              ▼
                               ┌──────────────────────┐
                               │  SWAP AGENTS          │
                               │  (Axelrod/Ethy/Otto)  │
                               └──────────────────────┘
```

### Component Breakdown

**1. Job Router & Handler**
- Receives incoming ACP job requests
- Routes to appropriate handler based on job type
- Manages ACP memo responses (status updates, deliverables)
- Handles escrow interactions

**2. Intelligence Generator**
- Processes Terminal data into structured intelligence reports
- Runs AI/LLM analysis for `market_sentiment` narrative generation
- Generates signal detection (fear capitulation, momentum shifts, etc.)
- Powers the Consigliere personality for Butler-facing responses

**3. Condition Monitor**
- Long-running monitoring loop for `smart_buy` and `take_profit` jobs
- Checks conditions every 60 seconds against Terminal data feed
- Manages job timeouts and expiration refunds
- Sends periodic General Memos with status updates to job requestors

**4. Market Data Feed**
- Connects to existing MAFIA Terminal infrastructure (CoinMarketCap API)
- Maintains real-time Fear & Greed, prices, dominance, volumes
- Shared data layer — one feed serves all active monitoring jobs
- 60-second refresh cycle (matches existing Terminal)

**5. Execution Orchestrator**
- When conditions are met, creates a *new* ACP job as Client to a swap agent
- Selects best swap agent based on availability, pricing, and user preference
- Manages the nested job lifecycle (request → negotiation → transaction → evaluation)
- Collects execution proof (tx hash) and packages into MAFIA's deliverable memo

**6. Swap Agent Client**
- ACP SDK integration for outbound jobs to swap providers
- Handles fund transfer from MAFIA's escrow to swap agent's job
- Monitors swap job completion and collects results

---

## 6. ACP Job Lifecycle Flows

### Flow A: Intelligence Jobs (`fear_and_greed`, `market_sentiment`)

```
Butler/Agent ──► MAFIA (Provider)
    │
    ├─ 1. REQUEST: Job initiated, service fee escrowed
    │
    ├─ 2. NEGOTIATION: MAFIA auto-accepts (no negotiation needed)
    │      └─ RequirementMemo: confirms input params
    │
    ├─ 3. TRANSACTION: Fee confirmed, MAFIA begins processing
    │      └─ Fetches Terminal data, runs analysis (if market_sentiment)
    │
    ├─ 4. EVALUATION: MAFIA delivers result
    │      └─ DeliverableMemo: JSON payload with market data
    │
    └─ 5. COMPLETED: Auto-approved, fee released to MAFIA
```

**Timeline:** 10-60 seconds end-to-end. These are fast, synchronous jobs.

### Flow B: Conditional Execution Jobs (`smart_buy`, `take_profit`)

```
Butler/Agent ──► MAFIA (Provider)               MAFIA (Client) ──► Swap Agent
    │                                                │
    ├─ 1. REQUEST                                    │
    │                                                │
    ├─ 2. NEGOTIATION                                │
    │      └─ MAFIA confirms strategy + params       │
    │                                                │
    ├─ 3. TRANSACTION                                │
    │      └─ Funds + fee escrowed                   │
    │      └─ MAFIA begins monitoring loop           │
    │      └─ General Memos: status updates          │
    │         every ~15 min or on significant change  │
    │                                                │
    │   ... conditions met! ...                      │
    │                                                │
    │                                    ┌───────────┤
    │                                    │  4a. MAFIA initiates swap job
    │                                    │      as ACP Client
    │                                    │  4b. Funds transferred to
    │                                    │      swap agent escrow
    │                                    │  4c. Swap executes on-chain
    │                                    │  4d. Swap agent delivers tx hash
    │                                    └───────────┤
    │                                                │
    ├─ 4. EVALUATION                                 │
    │      └─ MAFIA delivers:                        │
    │         - Execution proof (tx hash)            │
    │         - Conditions that triggered             │
    │         - Monitoring summary                    │
    │                                                │
    └─ 5. COMPLETED                                  │
           └─ Service fee released to MAFIA          │
           └─ Purchased tokens in user's wallet      │
```

### Flow C: Timeout / Conditions Not Met

```
    ├─ 3. TRANSACTION (monitoring)
    │      └─ max_wait_hours expires
    │      └─ General Memo: "Conditions not met within timeframe"
    │
    ├─ REFUND
    │      └─ Principal funds returned to buyer via ACP escrow
    │      └─ Service fee: partial refund (TBD — could charge reduced monitoring fee)
    │
    └─ COMPLETED (with refund status)
```

---

## 7. Technical Implementation

### Tech Stack

| Component | Technology | Notes |
|-----------|-----------|-------|
| Agent Runtime | Python 3.11+ | GAME SDK + ACP Python SDK (`virtuals-acp`) |
| Package Manager | `uv` | Fast Python package manager — replaces pip/pip-tools/venv |
| ACP Integration | `virtuals-acp` Python SDK | Job handling, memo creation, escrow interaction |
| Market Data | Existing MAFIA Terminal API | CoinMarketCap feed, 60s refresh, already built |
| AI/LLM | Claude API or local model | For market_sentiment narrative generation |
| Database | Supabase (PostgreSQL) | Job state, monitoring logs, execution history |
| Hosting | Railway or dedicated VPS | Long-running process for condition monitoring |
| Blockchain | Base network | ERC-4337 wallet for agent operations |

### Key Implementation Modules

```
src/
├── agent/
│   ├── profile.py          # ACP registration + job offering definitions
│   ├── router.py           # on_new_task callback, routes jobs by type
│   └── memo.py             # ACP memo creation and signing
├── intelligence/
│   ├── fear_and_greed.py   # F&G data fetch + formatting
│   ├── market_analysis.py  # Full sentiment report + signal detection
│   └── narrator.py         # LLM-powered market narrative (Claude API)
├── monitor/
│   ├── engine.py           # Condition evaluation against live data
│   ├── loop.py             # Async monitoring loop for all active jobs
│   └── timeout.py          # Expiration + refund logic
├── execution/
│   ├── swap_client.py      # ACP client for outbound swap jobs
│   ├── agent_selector.py   # Picks best swap agent (availability/price)
│   └── tracker.py          # Tracks nested swap job through completion
├── data/
│   ├── terminal_feed.py    # Connection to MAFIA Terminal market data
│   ├── cache.py            # In-memory cache for shared metrics
│   └── history.py          # Execution history (Supabase)
├── main.py                 # Entry point — inits ACP client, starts loops
pyproject.toml              # uv-managed project config + dependencies
uv.lock                     # uv lockfile (committed to repo)
```

### Monitoring Job Architecture

The condition monitor is the most complex component. It needs to efficiently manage potentially hundreds of concurrent monitoring jobs against a shared data feed.

```
Terminal Feed (60s refresh)
        │
        ▼
   Data Cache (in-memory)
        │
        ▼
  ┌─────────────────────┐
  │  Job Monitor Loop    │  ← runs every 60s
  │                      │
  │  for each active job:│
  │    1. Get conditions  │
  │    2. Evaluate against│
  │       cached data     │
  │    3. If met → trigger│
  │       execution       │
  │    4. If expired →    │
  │       trigger refund  │
  │    5. If status update│
  │       due → send memo │
  └─────────────────────┘
```

All monitoring jobs share the same data feed — MAFIA doesn't need to make separate API calls per job. This is a key efficiency advantage.

---

## 8. Revenue Model

### Per-Job Revenue

| Job | Price | Estimated Volume (Month 1) | Monthly Revenue |
|-----|-------|---------------------------|-----------------|
| `fear_and_greed` | $0.10 | 500 calls | $50 |
| `market_sentiment` | $0.25 | 200 calls | $50 |
| `smart_buy` | $0.50 | 50 executions | $25 |
| `take_profit` | $0.50 | 30 executions | $15 |
| **Total** | | | **~$140/mo** |

These are conservative Month 1 estimates. As Butler distribution scales (50K+ users) and MAFIA builds reputation, volume should increase significantly.

### Revenue via ACP Tax Structure

Per Virtuals' ACP economics, when Butler processes MAFIA's jobs:
- **60%** goes to MAFIA's agent wallet
- **30%** goes to $MAFIA token buy-back & burn
- **10%** goes to treasury (1% to G.A.M.E treasury)

This means every job directly supports $MAFIA token value through the burn mechanism.

### Cost Structure

| Cost | Monthly Estimate |
|------|-----------------|
| CoinMarketCap API | ~$0 (existing) |
| AI/LLM calls (Claude API for analysis) | ~$20-50 |
| Railway hosting (agent runtime) | ~$20 |
| Swap agent fees (pass-through) | Variable |
| **Total Overhead** | **~$50-70/mo** |

Net positive from Month 1 with even modest adoption.

---

## 9. Implementation Roadmap

### Week 1: Foundation
- [ ] Register MAFIA agent on ACP Registry with profile and job offerings
- [ ] Set up agent wallet on Base
- [ ] Implement ACP SDK integration (job handling, memo responses)
- [ ] Connect existing Terminal data feed to agent runtime
- [ ] Implement `fear_and_greed` job (simplest, good for testing)

### Week 2: Intelligence Layer
- [ ] Implement `market_sentiment` job with full data aggregation
- [ ] Integrate AI/LLM for narrative generation
- [ ] Build signal detection logic (capitulation, momentum, etc.)
- [ ] Set up Resources (current_market_snapshot, active_jobs)
- [ ] Test with Butler interactions in sandbox

### Week 3: Conditional Execution
- [ ] Build condition monitoring engine
- [ ] Implement `smart_buy` job with preset strategies
- [ ] Build swap agent client (ACP outbound job creation)
- [ ] Implement nested job lifecycle management
- [ ] Add timeout/refund handling

### Week 4: Polish & Launch
- [ ] Implement `take_profit` job
- [ ] Add execution history tracking and Resources
- [ ] Stress test monitoring loop with concurrent jobs
- [ ] Finalize Consigliere personality for Butler responses
- [ ] Graduate agent from sandbox to production
- [ ] Content push: "MAFIA is live on Virtuals ACP"

---

## 10. Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Swap agent unavailable when conditions trigger | High — missed execution | Fallback to multiple swap agents; queue retry logic |
| Terminal data goes stale | Medium — incorrect trigger timing | Stale data detection (>5min old = pause monitoring, notify user) |
| Nested ACP job fails (swap rejected) | High — funds stuck | Retry with alternate swap agent; timeout returns to MAFIA escrow |
| High concurrent monitoring jobs strain system | Medium — slow evaluation | Shared data cache; batch evaluation; scale horizontally if needed |
| User conditions never met (always monitoring) | Low — wasted resources | max_wait_hours enforced; monitoring cost is minimal (shared feed) |
| ACP protocol changes / breaking updates | Medium — service disruption | Pin SDK versions; monitor Virtuals changelogs; maintain test suite |

---

## 11. Success Metrics

### Month 1 Targets
- Agent graduated and live on ACP
- 100+ total jobs processed
- 3+ other agents using MAFIA's intelligence data
- $100+ revenue generated

### Month 3 Targets
- 1,000+ monthly jobs processed
- 50+ unique Butler users interacting with MAFIA
- $500+ monthly revenue
- 95%+ job completion rate
- Featured in Virtuals ecosystem communications

### North Star
MAFIA becomes the default intelligence layer that other ACP agents query before making trading decisions — the "market brain" of the Virtuals ecosystem.

---

## 12. Content & Marketing Angle

Building the agent IS the marketing. Every interaction generates potential content:

- **"MAFIA just called the bottom"** — When a smart_buy triggers at F&G 18 and the market bounces 20%, that's a Twitter thread.
- **Live monitoring updates** — MAFIA can post status updates from active jobs (anonymized) as social proof.
- **Agent-to-agent interactions** — Every time MAFIA hires Axelrod to execute a swap, that's a visible ACP transaction that demonstrates the ecosystem in action.
- **Builder content** — Document the build process for Virtuals community (dev logs, architecture decisions).

This aligns with the discovery-style content approach that performs well in crypto — showing real utility rather than promoting.
