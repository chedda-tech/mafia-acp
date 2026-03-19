# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MAFIA AI is a market intelligence and conditional execution orchestrator on Virtuals ACP (Agent Cooperation Protocol). It acts as both an ACP **Provider** (selling intelligence jobs) and **Client** (hiring swap agents like Axelrod/Ethy/Otto when market conditions trigger).

**Architecture doc:** `docs/MAFIA_ACP_AGENT_ARCHITECTURE.md`

## Skill Reference

The `.claude/skills/mafia-acp/` skill is **required reading** before writing any ACP agent code. It contains:

- ACP SDK usage patterns, job lifecycle phases, and memo handling
- Phase 1 job implementations (`fear_and_greed`, `market_sentiment`) — live
- Phase 2 job implementations (`smart_buy`, `take_profit`) — planned, not yet live
- Condition monitoring engine design (Phase 2)
- Nested ACP job orchestration (Phase 2 — MAFIA as both Provider and Client)
- Common pitfalls that cause stuck jobs or lost funds
- ACP CLI commands for development and testing

Reference files in `.claude/skills/mafia-acp/references/`:
- `architecture.md` — System components, data flow, DB schema, deployment
- `conditional-execution.md` — smart_buy/take_profit lifecycle, refund handling, edge cases (Phase 2)
- `job-schemas.md` — Exact JSON schemas for all job requirements and deliverables
- `acp-sdk-patterns.md` — SDK methods, phase transitions, memo types, error handling

## Tech Stack

- **Runtime:** Python 3.11+
- **Package manager:** `uv` (not pip)
- **ACP SDK:** `virtuals-acp` (v0.3.8+, ACP v2)
- **AI/LLM:** Claude API (for market_sentiment narratives)
- **Database:** Supabase (PostgreSQL)
- **Network:** Base (ERC-4337 wallet)

## Commands

```bash
# Install dependencies
uv sync

# Add a new dependency
uv add <package>

# Add a dev dependency
uv add --dev <package>

# Run the agent
uv run python -m src.main

# Run tests
uv run pytest

# Run a single test file
uv run pytest tests/test_fear_and_greed.py

# Run a specific test
uv run pytest tests/test_fear_and_greed.py::test_handle_fear_and_greed_request -v

# Type checking
uv run mypy src/

# Linting
uv run ruff check src/

# Format
uv run ruff format src/
```

## Architecture

MAFIA has 6 internal components across 5 source packages:

- `src/agent/` — Job Router: ACP registration, `on_new_task` callback routing, memo handling
- `src/intelligence/` — Intelligence Generator: F&G data, market analysis, signal detection, Claude API narrative
- `src/monitor/` — Condition Monitor: async 60s evaluation loop (Phase 2 — not yet active)
- `src/execution/` — Execution Orchestrator: nested ACP jobs to swap agents (Phase 2 — not yet active)
- `src/data/` — Data Layer: Terminal API feed (CoinMarketCap, 60s refresh), in-memory cache, Supabase history

### Key Design Decisions

- **Shared data feed**: One Terminal connection (60s refresh) serves ALL monitoring jobs — no per-job API calls
- **Nested ACP jobs**: When conditions trigger, MAFIA creates a new ACP job as Client to a swap agent
- **General Memos for status**: Long-running jobs send updates every ~15 min; these do NOT advance job phase
- **Timeout/refund** (Phase 2): `smart_buy` max 72h, `take_profit` max 168h — principal refunded via ACP escrow if conditions not met

### ACP Job Lifecycle (critical)

Every ACP job follows: `REQUEST → NEGOTIATION → TRANSACTION → EVALUATION → COMPLETED`. Never skip phases. Always respond to pending memos. See the skill for details.

## Environment Variables

```
WHITELISTED_WALLET_PRIVATE_KEY=0x...   # Dev wallet (must include 0x prefix)
AGENT_WALLET_ADDRESS=0x...             # Smart contract wallet from ACP portal
ENTITY_ID=...                          # Integer from agent registration
DATABASE_URL=postgresql://...
MAFIA_API_BASE_URL=https://...
COINMARKETCAP_API_KEY=...
ANTHROPIC_API_KEY=sk-ant-...
```
