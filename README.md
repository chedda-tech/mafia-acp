# MAFIA ACP Agent

Market intelligence and conditional execution orchestrator for [Virtuals ACP](https://whitepaper.virtuals.io/acp-product-resources/acp-concepts-terminologies-and-architecture).

MAFIA acts as both an ACP **Provider** (selling intelligence jobs) and **Client** (hiring swap agents when market conditions trigger).

## Jobs

| Job | Price | Type | Status | Description |
|-----|-------|------|--------|-------------|
| `fear_and_greed` | $0.10 | Service | Live | Current F&G Index with trend context |
| `market_sentiment` | $0.25 | Service | Live | Full market report with AI analysis |
| `smart_buy` | $0.50 | Fund-transfer | Phase 2 | Conditional buy when conditions align |
| `take_profit` | $0.50 | Fund-transfer | Phase 2 | Conditional sell on exit signals |

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
# Install dependencies
uv sync

# Configure environment
cp .env.example .env
# Fill in your credentials (see below)
```

### Environment Variables

```
WHITELISTED_WALLET_PRIVATE_KEY=0x...   # Dev wallet (0x prefix required)
AGENT_WALLET_ADDRESS=0x...             # Smart contract wallet from ACP portal
ENTITY_ID=                             # Integer from agent registration
MAFIA_API_BASE_URL=https://...           # MAFIA Backend API for metric snapshots
LLM_BASE_URL=https://openrouter.ai/api/v1  # Any OpenAI-compatible provider
LLM_API_KEY=sk-or-...                 # Provider API key
LLM_MODEL=deepseek/deepseek-chat      # Model identifier
```

## Run

```bash
uv run python -m src.main
```

## Development

```bash
uv run pytest                      # Run tests
uv run pytest tests/test_fear_and_greed.py -v  # Single file
uv run ruff check src/             # Lint
uv run ruff format src/            # Format
```

## Architecture

See [docs/MAFIA_ACP_AGENT_ARCHITECTURE.md](docs/MAFIA_ACP_AGENT_ARCHITECTURE.md) for the full design.

```
src/
├── agent/          # ACP client, job routing, config
├── intelligence/   # F&G, market analysis, signal detection, AI narrator
├── monitor/        # Condition evaluation loop (Phase 2 — smart_buy/take_profit)
├── execution/      # Swap agent orchestration via nested ACP jobs (Phase 2)
└── data/           # Terminal API feed, in-memory cache, models
```
