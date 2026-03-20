# MAFIA AI — Job Offering Schemas

Complete JSON schemas for all 4 MAFIA job offerings. These are the exact structures registered in the ACP Agent Registry and expected by the agent code.

Jobs 1 & 2 (`fear_and_greed`, `market_sentiment`) are **live**. Jobs 3 & 4 (`smart_buy`, `take_profit`) are **Phase 2 — planned, not yet active**.

---

## Job 1: `fear_and_greed`

**Type:** Service-Only (`fundTransfer: false`)
**Price:** $0.10 VIRTUAL | **SLA:** 30 seconds

### Requirements (Buyer Input)

```json
{
  "type": "object",
  "properties": {},
  "description": "No input required. Returns current market sentiment snapshot."
}
```

### Deliverable (MAFIA Output)

```json
{
  "fear_and_greed": 31,
  "classification": "fear",
  "change_1h": -1,
  "change_24h": -4,
  "change_7d": -9,
  "change_30d": -18,
  "regime": "Fear",
  "timestamp": "2026-02-08T14:30:00Z",
  "source": "coinmarketcap"
}
```

> **Note:** `change_Xd` values are absolute point changes on the 0–100 scale. Source: CoinMarketCap via Mafia API.

### Classification Mapping

| F&G Value | Classification |
|-----------|---------------|
| 0–24 | `extreme_fear` |
| 25–44 | `fear` |
| 45–55 | `neutral` |
| 56–74 | `greed` |
| 75–100 | `extreme_greed` |

---

## Job 2: `market_sentiment`

**Type:** Service-Only (`fundTransfer: false`)
**Price:** $0.25 VIRTUAL | **SLA:** 60 seconds

### Requirements (Buyer Input)

```json
{
  "type": "object",
  "properties": {
    "focus_assets": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Optional. Assets to highlight. Defaults to ['BTC', 'ETH', 'SOL']."
    },
    "include_analysis": {
      "type": "boolean",
      "default": true,
      "description": "Whether to include AI narrative interpretation."
    }
  }
}
```

### Deliverable (MAFIA Output)

```json
{
  "timestamp": "2026-02-08T14:30:00Z",
  "regimes": {
    "sentiment_regime": "Fear",
    "trend_regime": "Capitulation / Distribution regime",
    "volume_regime": "Average trading activity",
    "dominance_regime": "Stable dominance",
    "fg_trajectory": "Fear Intensifying",
    "altseason_signal": "No rotation signal — dominance stable over 7d"
  },
  "fear_and_greed": {
    "value": 31,
    "classification": "fear",
    "change_24h": -4,
    "change_7d": -9,
    "change_30d": -18
  },
  "btc_dominance": {
    "value": 58.3,
    "change_24h": 0.8,
    "trend": "rising"
  },
  "rotation_signal": {
    "type": "no_rotation",
    "label": "No rotation signal — dominance stable over 7d",
    "btc_dominance_change_7d": 0.8
  },
  "total_market_cap": {
    "value_usd": "2.4T",
    "change_24h": -3.2,
    "change_7d": -8.1
  },
  "assets": [
    {
      "symbol": "BTC",
      "price": 70500,
      "change_24h": -5.2,
      "change_7d": -1.1,
      "volume_24h": "28.5B",
      "volume_change_24h": 12.4
    }
  ],
  "analysis": {
    "overview": "F&G at 31, BTC dropped 5.2% today — fear is intensifying.",
    "analysis": "Capitulation and distribution are clear, with average volume suggesting sustained selling.",
    "insight": "Deepening fear often precedes market bottoms — smart players prepare for opportunities as the crowd capitulates.",
    "altseason": "No rotation signal — dominance stable over 7d",
    "signals": [
      {
        "signal": "fear_capitulation",
        "strength": "strong",
        "description": "F&G below 25 with rising volume"
      }
    ],
    "regime": "Capitulation / Distribution regime"
  },
  "source": "mafia_terminal"
}
```

> **Note:** `fear_and_greed.change_Xd` values are absolute point changes on the 0–100 scale. Source: CoinMarketCap via Mafia API.
> **`rotation_signal.type`** values: `btc_dominant` (dominance up >2% over 7d), `altseason` (dominance down >2% over 7d), `no_rotation`.
> **`btc_dominance.trend`** values: `rising` (>0.3% change), `falling` (<-0.3%), `stable`.

### Regime Labels

**`fg_trajectory`** — combines F&G zone + momentum:

| Trajectory | Meaning |
|---|---|
| `Extreme Fear Deepening` | F&G ≤24, dropping fast (>3 pts in 24h) |
| `Extreme Fear Persisting` | F&G ≤24, flat |
| `Extreme Fear — Stabilizing` | F&G ≤24, recovering |
| `Fear Intensifying` | F&G 25–44, dropping fast |
| `Fear Consolidating` | F&G 25–44, flat |
| `Fear — Recovery in Progress` | F&G 25–44, recovering vs 30d |
| `Fear Easing` | F&G 25–44, rising fast |
| `Neutral` / `Neutral — Greed Building` / `Neutral — Softening` | F&G 45–54 |
| `Greed Building` / `Greed Persisting` / `Greed Cooling` | F&G 55–74 |
| `Extreme Greed Accelerating` / `Extreme Greed Persisting` / `Extreme Greed Cooling` | F&G ≥75 |

### Signal Types

| Signal ID | Trigger | Strength Values |
|-----------|---------|----------------|
| `fear_capitulation` | F&G < 25 + avg volume up >20% | weak, moderate, strong |
| `greed_exhaustion` | F&G > 75 + F&G declining 24h | weak, moderate, strong |
| `btc_dominance_rising` | BTC dominance up >1.5% in 24h | weak, moderate, strong |
| `btc_dominance_falling` | BTC dominance down >1.5% in 24h | weak, moderate, strong |
| `volume_spike` | Avg 24h volume up >40% | weak, moderate, strong |
| `volume_dry_up` | Avg 24h volume down >30% | weak, moderate, strong |

---

## Job 3: `smart_buy` *(Phase 2 — not yet active)*

**Type:** Fund-Transfer (`fundTransfer: true`)
**Price:** $0.50 VIRTUAL (service fee) | **SLA:** Variable, up to 72 hours

### Requirements (Buyer Input)

```json
{
  "type": "object",
  "required": ["buy_token", "spend_amount", "spend_token"],
  "properties": {
    "buy_token": {
      "type": "string",
      "description": "Token to purchase (symbol or contract address)"
    },
    "spend_token": {
      "type": "string",
      "default": "USDC",
      "description": "Token to spend"
    },
    "spend_amount": {
      "type": "number",
      "description": "Amount of spend_token to use"
    },
    "strategy": {
      "type": "string",
      "enum": ["fear_dip_buy", "momentum_recovery", "custom"],
      "default": "fear_dip_buy"
    },
    "conditions": {
      "type": "object",
      "description": "Custom conditions (when strategy='custom')",
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
      "description": "Max monitoring time. Refund if conditions not met."
    },
    "swap_agent_preference": {
      "type": "string",
      "description": "Preferred swap agent name. Auto-selected if not specified."
    }
  }
}
```

### Deliverable — Success

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

### Deliverable — Timeout

```json
{
  "status": "expired",
  "reason": "Conditions not met within 72-hour window",
  "monitoring_summary": {
    "total_checks": 4320,
    "hours_monitored": 72.0,
    "closest_to_trigger": {
      "time": "2026-02-09T18:00:00Z",
      "fg": 23,
      "note": "Approached target but F&G never dropped below 20"
    }
  },
  "refund": {
    "amount": 3000,
    "token": "USDC",
    "status": "returned_to_escrow"
  }
}
```

---

## Job 4: `take_profit` *(Phase 2 — not yet active)*

**Type:** Fund-Transfer (`fundTransfer: true`)
**Price:** $0.50 VIRTUAL (service fee) | **SLA:** Variable, up to 168 hours

### Requirements (Buyer Input)

```json
{
  "type": "object",
  "required": ["sell_token", "sell_amount"],
  "properties": {
    "sell_token": {
      "type": "string",
      "description": "Token to sell (symbol or contract address)"
    },
    "sell_amount": {
      "type": "number",
      "description": "Amount to sell (or percentage if sell_as_percentage is true)"
    },
    "sell_as_percentage": {
      "type": "boolean",
      "default": false
    },
    "receive_token": {
      "type": "string",
      "default": "USDC"
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

### Deliverable

Same structure as `smart_buy` but with sell transaction details instead of buy.

---

## General Memo Schemas (Status Updates)

These are sent as general memos during long-running jobs and do **not** advance the job phase.

### Monitoring Status Update

```json
{
  "type": "status_update",
  "status": "monitoring",
  "strategy": "fear_dip_buy",
  "current_conditions": {
    "fear_and_greed": 28,
    "fear_and_greed_24h_change": -3,
    "target": "fg <= 20 AND recovering"
  },
  "hours_remaining": 45.2,
  "total_checks": 412,
  "last_checked": "2026-02-08T20:30:00Z"
}
```

### Condition Triggered Notification

```json
{
  "type": "condition_triggered",
  "status": "executing_swap",
  "conditions_met": {
    "fear_and_greed": 19,
    "fear_and_greed_24h_change": 2,
    "recovery_detected": true
  },
  "swap_agent": "axelrod",
  "swap_job_id": 4521,
  "timestamp": "2026-02-09T03:30:00Z"
}
```

---

## Validation Rules

### `smart_buy`

1. `buy_token` must be a recognized symbol or valid contract address
2. `spend_amount` must be > 0
3. `spend_token` must be a supported token (USDC, ETH, VIRTUAL)
4. `max_wait_hours` must be between 1 and 168
5. If strategy is `custom`, at least one condition must be specified
6. `fear_and_greed_below` must be between 0–100

### `take_profit`

1. `sell_token` must be recognized
2. `sell_amount` must be > 0
3. If `sell_as_percentage`, must be between 1–100
4. `max_wait_hours` must be between 1 and 336
5. `fear_and_greed_above` must be between 0–100
