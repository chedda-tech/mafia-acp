# MAFIA ACP Agent — Implementation Plan

**Created:** 2026-03-02
**Status:** In Progress

---

## Overview

MAFIA AI is a market intelligence and conditional execution orchestrator for Virtuals ACP. This plan covers the full implementation from greenfield to production-ready agent.

**Delivery is split into two phases:**
- **Phase 1 (Data):** Project scaffolding, market data feed, ACP integration, `fear_and_greed` + `market_sentiment` jobs
- **Phase 2 (Execution):** Condition monitoring engine, `smart_buy` + `take_profit` jobs, swap agent orchestration

**Key decisions:**
- Terminal API is already running (abstraction layer built for flexibility)
- ACP agent registration needed as part of Phase 1
- Supabase project is ready (connection string via env)
- F&G data: Alternative.me (primary) + CoinMarketCap (fallback)

---

## Phase 1: Data & Intelligence Layer

### Step 1.1 — Project Scaffolding
- [ ] Create `pyproject.toml` — Python 3.11+, uv-managed
  - Dependencies: `virtuals-acp>=0.3.8`, `httpx`, `anthropic`, `supabase`, `python-dotenv`, `pydantic`
  - Dev deps: `pytest`, `pytest-asyncio`, `ruff`, `mypy`
- [ ] Create `.env.example` with all env vars
- [ ] Create directory structure with `__init__.py` files:
  - `src/`, `src/agent/`, `src/intelligence/`, `src/monitor/`, `src/execution/`, `src/data/`, `tests/`
- [ ] Run `uv sync` to generate `uv.lock`
- [ ] Verify: `uv run python -c "import src"`

### Step 1.2 — Configuration & Models
- [ ] `src/agent/config.py` — Pydantic `BaseSettings` for env var loading
  - ACP: wallet key, wallet address, entity_id
  - Database: database_url
  - Terminal: terminal_api_url
  - API keys: coinmarketcap_api_key, anthropic_api_key
  - Monitoring: log_level, status_update_interval, stale_data_threshold, max_swap_retries
- [ ] `src/data/models.py` — Data models
  - `MarketDataCache` dataclass (20 fields from architecture.md)
  - `classify_fg(value) -> str` mapping (0-24=extreme_fear, 25-44=fear, etc.)
  - Response models for job deliverables (Pydantic)
  - `SignalType` enum, `Signal` model, `MarketOutlook` enum

### Step 1.3 — Market Data Feed
- [ ] `src/data/terminal_feed.py` — `TerminalFeed` class
  - `async start()` kicks off 60s refresh loop
  - `async fetch()` hits Terminal API, parses into `MarketDataCache`
  - Abstraction layer (interface-first, actual endpoint details plugged in later)
- [ ] `src/data/fear_and_greed.py` — `FearAndGreedFeed`
  - Primary: Alternative.me API (free, no key)
  - Fallback: CoinMarketCap API (requires key)
  - Historical values for change calculations (30-day cache)
- [ ] `src/data/cache.py` — `DataCache` singleton
  - `get_latest() -> MarketDataCache`
  - `is_stale() -> bool` (threshold from config)
  - Thread-safe via `asyncio.Lock`
  - `update(data)` called by feeds

### Step 1.4 — ACP Agent Setup & Registration
- [ ] `src/agent/offerings.py` — Job offering definitions
  - All 4 offerings with exact schemas from job-schemas.md
  - Pricing: $0.10, $0.25, $0.50, $0.50 VIRTUAL
  - SLA timeouts per job type
- [ ] `src/agent/router.py` — `on_new_task` callback
  - Guard: skip if `memo_to_sign` is None or not PENDING
  - Route by `job.get_service_name()` to handlers
  - Reject unknown services with reason
  - Exception handling: never leave pending memos unsigned
- [ ] `src/agent/main.py` — ACP client initialization
  - `VirtualsACP` with `ACPContractClientV2` and `BASE_MAINNET_ACP_X402_CONFIG_V2`
  - Wire `on_new_task` callback
  - Start terminal feed + ACP client

### Step 1.5 — `fear_and_greed` Job Handler
- [ ] `src/intelligence/fear_and_greed.py`
  - NEGOTIATION: always accept (no input required)
  - TRANSACTION: fetch from cache, format deliverable, call `deliver_job()`
  - Deliverable: `{fear_and_greed, classification, change_1h, change_24h, change_7d, change_30d, timestamp, source}`
- [ ] `tests/test_fear_and_greed.py`
  - Test classification mapping
  - Test deliverable JSON structure
  - Test with mock ACP client

### Step 1.6 — `market_sentiment` Job Handler
- [ ] `src/intelligence/signal_detector.py` — Signal detection engine
  - 6 signals: fear_capitulation, greed_exhaustion, btc_dominance_rising/falling, volume_spike, volume_dry_up
  - Strength: weak/moderate/strong based on magnitude
  - Input: `MarketDataCache`, Output: `list[Signal]`
- [ ] `src/intelligence/ai_narrator.py` — Claude API narrative
  - Call `claude-sonnet-4-20250514` with structured data
  - Consigliere personality prompt
  - Returns: `{summary, signals, outlook}` JSON
  - Graceful fallback if Claude unavailable
- [ ] `src/intelligence/market_analysis.py` — Market sentiment handler
  - NEGOTIATION: accept, parse `focus_assets` + `include_analysis`
  - TRANSACTION: aggregate data, run signals, call narrator
  - Full deliverable matching job-schemas.md
- [ ] `tests/test_intelligence.py`
  - Test signal detection with known patterns
  - Test market analysis aggregation
  - Test AI narrator prompt (mock API)

### Step 1.7 — Entry Point & Integration
- [ ] `src/main.py` — Top-level entry point
- [ ] `src/__main__.py` — Allow `python -m src` invocation
- [ ] Wire everything: settings → feeds → cache → ACP client → router → handlers
- [ ] `tests/test_integration.py` — End-to-end with mock ACP
- [ ] Verify: `uv run python -m src.main` boots and connects
- [ ] Verify: `uv run pytest tests/ -v` all pass
- [ ] Verify: `uv run ruff check src/` clean

---

## Phase 2: Execution Layer

### Step 2.1 — Database Schema & Persistence
- [ ] `migrations/001_create_tables.sql` — SQL migration
  - `monitoring_jobs` table (all state for smart_buy/take_profit)
  - `execution_history` table (completed executions)
  - `condition_check_log` table (audit trail, 30-day retention)
- [ ] `src/data/database.py` — Supabase client
  - CRUD for monitoring_jobs
  - Insert/query execution_history
  - Batch insert condition_check_log
- [ ] Run migration against Supabase

### Step 2.2 — Condition Engine
- [ ] `src/monitor/conditions.py` — Condition evaluation
  - `Condition` dataclass (metric, operator, threshold)
  - `build_conditions(reqs)` — strategy → list of Conditions
  - `evaluate_conditions(conditions, data)` — AND logic, all must be True
  - `get_metric_value(metric, data)` — maps metric names to cache fields
  - Missing data = condition not met (safe default)
- [ ] `src/monitor/strategies.py` — Preset strategy definitions
  - `fear_dip_buy`: F&G <= 20 AND F&G_24h_change > 0
  - `momentum_recovery`: F&G_7d_low <= 25 AND F&G > 35 AND F&G_trend_3d == up
  - `greed_exit`: F&G >= 75 AND F&G_24h_change < 0
  - `momentum_fade`: F&G_7d_high >= 70 AND F&G < 60 AND F&G_trend_2d == down
  - `custom`: parse user's conditions dict
- [ ] `tests/test_monitor.py`
  - Test each preset strategy builds correct conditions
  - Test condition evaluation with various data states
  - Test custom condition parsing
  - Test edge cases: missing data, boundary values

### Step 2.3 — Monitoring Engine
- [ ] `src/monitor/engine.py` — `MonitoringEngine`
  - `active_jobs: dict` — in-memory + backed by Supabase
  - `async run()` — main loop, evaluates every 60s
  - `async add_job()` — add to active set + persist to DB
  - `async remove_job()` — remove + update DB
  - `async recover_jobs()` — on startup, reload from DB + ACP
  - Status updates via `send_message()` every 15 min
- [ ] `src/monitor/timeout.py` — Timeout handling
  - `check_timeout(job)` — elapsed hours vs max_wait_hours
  - `handle_timeout(job)` — deliver expired result, cleanup, record history

### Step 2.4 — `smart_buy` Job Handler
- [ ] `src/intelligence/smart_buy.py`
  - NEGOTIATION: validate buy_token, spend_amount, spend_token; apply defaults; check strategy constraints
  - TRANSACTION: create MonitoringJob, add to engine, send initial status memo
  - Delegate to orchestrator when conditions trigger

### Step 2.5 — Execution Orchestrator (Swap Agent Integration)
- [ ] `src/execution/agent_selector.py` — Browse and select swap agent
  - `browse_agents()` with keyword="token swap Base", GRADUATED+ONLINE
  - Prefer user's agent (substring match)
  - Fallback to highest success rate
  - Find swap/trade/exchange offering
- [ ] `src/execution/orchestrator.py` — Main orchestration
  - `execute_swap(monitoring_job, market_data)` — select agent, build requirements, initiate nested ACP job
  - `handle_swap_result(swap_job_id, result)` — package into MAFIA deliverable
  - `handle_swap_failure(monitoring_job, error)` — retry up to 3x, then refund
- [ ] `src/execution/tracker.py` — Nested job tracking
  - Map swap_job_id → monitoring_job_id
  - Handle nested job callbacks (MAFIA as Client)
  - Detect completion, extract tx_hash
  - 1-hour timeout per swap attempt

### Step 2.6 — `take_profit` Job Handler
- [ ] `src/intelligence/take_profit.py`
  - Same structure as smart_buy, sell-specific:
  - Validate: sell_token, sell_amount, sell_as_percentage
  - Strategies: greed_exit, momentum_fade, custom
  - Max wait: 168 hours
  - Swap action: "sell"

### Step 2.7 — Integration, Recovery & Polish
- [ ] Startup recovery: `recover_active_jobs()` on boot
- [ ] Stale data detection: pause monitoring + warning when data > 5 min old
- [ ] Execution history recording for completed/failed/expired jobs
- [ ] Condition check log entries on each evaluation cycle
- [ ] `tests/test_execution.py`
  - Test swap agent selection with mock browse
  - Test orchestrator retry logic
  - Test timeout/refund flow
  - Test startup recovery from DB state
- [ ] Error handling audit: no pending memos left unsigned
- [ ] Verify: `uv run pytest tests/ -v` all pass
- [ ] Verify: full end-to-end flow works

---

## File Map

### Phase 1 Files
| File | Purpose |
|------|---------|
| `pyproject.toml` | Project config, dependencies |
| `.env.example` | Environment variable template |
| `src/__init__.py` | Package init |
| `src/__main__.py` | Module runner |
| `src/main.py` | Top-level entry point |
| `src/agent/__init__.py` | Package init |
| `src/agent/config.py` | Settings via pydantic |
| `src/agent/main.py` | ACP client init |
| `src/agent/router.py` | Job routing callback |
| `src/agent/offerings.py` | 4 job offering definitions |
| `src/data/__init__.py` | Package init |
| `src/data/models.py` | MarketDataCache, response models |
| `src/data/terminal_feed.py` | Terminal API integration |
| `src/data/fear_and_greed.py` | F&G from Alternative.me + CMC |
| `src/data/cache.py` | In-memory data cache |
| `src/intelligence/__init__.py` | Package init |
| `src/intelligence/fear_and_greed.py` | F&G job handler |
| `src/intelligence/market_analysis.py` | Market sentiment handler |
| `src/intelligence/signal_detector.py` | Signal detection |
| `src/intelligence/ai_narrator.py` | Claude API narrative |
| `tests/__init__.py` | Package init |
| `tests/test_fear_and_greed.py` | F&G tests |
| `tests/test_intelligence.py` | Intelligence tests |
| `tests/test_integration.py` | Integration tests |

### Phase 2 Files
| File | Purpose |
|------|---------|
| `migrations/001_create_tables.sql` | DB schema |
| `src/data/database.py` | Supabase CRUD |
| `src/monitor/__init__.py` | Package init |
| `src/monitor/conditions.py` | Condition evaluation |
| `src/monitor/strategies.py` | Preset strategies |
| `src/monitor/engine.py` | Monitoring loop |
| `src/monitor/timeout.py` | Timeout/refund |
| `src/intelligence/smart_buy.py` | smart_buy handler |
| `src/intelligence/take_profit.py` | take_profit handler |
| `src/execution/__init__.py` | Package init |
| `src/execution/orchestrator.py` | Swap orchestration |
| `src/execution/agent_selector.py` | Agent selection |
| `src/execution/tracker.py` | Nested job tracking |
| `tests/test_monitor.py` | Monitor tests |
| `tests/test_execution.py` | Execution tests |
