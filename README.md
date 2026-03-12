# MAFIA ACP Agent

Market intelligence and conditional execution orchestrator for [Virtuals ACP](https://whitepaper.virtuals.io/acp-product-resources/acp-concepts-terminologies-and-architecture).

MAFIA acts as both an ACP **Provider** (selling intelligence jobs) and **Client** (hiring swap agents when market conditions trigger).

## Jobs

| Job | Price | Type | Description |
|-----|-------|------|-------------|
| `fear_and_greed` | $0.10 | Service | Current F&G Index with trend context |
| `market_sentiment` | $0.25 | Service | Full market report with AI analysis |
| `smart_buy` | $0.50 | Fund-transfer | Conditional buy when conditions align |
| `take_profit` | $0.50 | Fund-transfer | Conditional sell on exit signals |

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
TERMINAL_API_URL=https://...           # MAFIA Terminal API (serves F&G + market data)
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
uv run pytest tests/test_monitor.py -v  # Single file
uv run ruff check src/             # Lint
uv run ruff format src/            # Format
```

## Architecture

See [docs/MAFIA_ACP_AGENT_ARCHITECTURE.md](docs/MAFIA_ACP_AGENT_ARCHITECTURE.md) for the full design.

```
src/
├── agent/          # ACP client, job routing, config
├── intelligence/   # F&G, market analysis, signal detection, AI narrator
├── monitor/        # Condition evaluation loop (smart_buy/take_profit)
├── execution/      # Swap agent orchestration via nested ACP jobs
└── data/           # Terminal API feed, in-memory cache, models
```
