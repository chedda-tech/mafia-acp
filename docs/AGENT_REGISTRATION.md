# MAFIA AI — Agent Registration Metadata

**Created:** 2026-03-08
**Purpose:** All metadata needed to register MAFIA AI on the ACP portal and CLI.

---

## Agent Profile

| Field | Value |
|---|---|
| **Name** | MAFIA AI |
| **Role** | Hybrid (Provider + Client) |

### Business Description (500 char max)

> MAFIA AI is a market intelligence and conditional execution orchestrator. Get real-time Fear & Greed data, AI-powered sentiment analysis with signal detection, or set conditions and deposit funds — MAFIA monitors 24/7 and executes buys/sells via swap agents when your conditions trigger. Refunds if conditions aren't met.

(296 characters)

---

## Jobs Overview

| Job | Fee | Fee Type | SLA | Required Funds |
|---|---|---|---|---|
| `fear_and_greed` | $0.10 | fixed | 1 min | No |
| `market_sentiment` | $0.25 | fixed | 2 min | No |
| `smart_buy` | $0.50 | fixed | 72 hours (4320 min) | Yes |
| `take_profit` | $0.50 | fixed | 7 days (10080 min) | Yes |

---

## Job 1: `fear_and_greed`

**Description:** Current Fear & Greed Index with trend context. Returns F&G value, classification, and multi-period changes (1h, 24h, 7d, 30d).

| Field | Value |
|---|---|
| **Name** | `fear_and_greed` |
| **Job Fee** | 0.10 |
| **Job Fee Type** | fixed |
| **Required Funds** | false |
| **SLA (minutes)** | 1 |

### Requirement (JSON Schema)

```json
{
  "type": "object",
  "properties": {},
  "description": "No input required. Returns current market sentiment snapshot."
}
```

### Sample Request

```json
{}
```

### Sample Deliverable

```json
{
  "fear_and_greed": 22,
  "classification": "extreme_fear",
  "change_1h": -1,
  "change_24h": -7,
  "change_7d": -12,
  "change_30d": -24,
  "regime": "Extreme Fear",
  "timestamp": "2026-02-08T14:30:00Z",
  "source": "alternative_me"
}
```

### Signal Types

| Signal ID | Description |
|---|---|
| `fear_capitulation` | F&G < 25 + volume spike > 40% |
| `greed_exhaustion` | F&G > 75 + declining momentum |
| `btc_dominance_rising` | Capital rotating to BTC (risk-off) |
| `btc_dominance_falling` | Capital rotating to alts (risk-on) |
| `volume_spike` | 24h volume up 40%+ |
| `volume_dry_up` | 24h volume down 30%+ |

### Outlook Values

`bullish_short_term` · `bullish_medium_term` · `bearish_short_term` · `bearish_medium_term` · `bearish_short_term_bullish_medium_term` · `bullish_short_term_bearish_medium_term` · `neutral`

---

## Job 3: `smart_buy`

**Description:** Conditional buy execution. Monitors market conditions (Fear & Greed, price, BTC dominance) and executes a token purchase via swap agent when conditions align. Principal refunded if conditions not met within wait window.

| Field | Value |
|---|---|
| **Name** | `smart_buy` |
| **Job Fee** | 0.50 |
| **Job Fee Type** | fixed |
| **Required Funds** | true |
| **SLA (minutes)** | 4320 (72 hours) |

### Requirement (JSON Schema)

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
      "description": "Max monitoring time in hours. Principal refunded if conditions not met."
    },
    "swap_agent_preference": {
      "type": "string",
      "description": "Preferred swap agent name. Auto-selected if not specified."
    }
  }
}
```

### Sample Request — Preset Strategy

```json
{
  "buy_token": "ETH",
  "spend_token": "USDC",
  "spend_amount": 3000,
  "strategy": "fear_dip_buy",
  "max_wait_hours": 48
}
```

### Sample Request — Custom Strategy

```json
{
  "buy_token": "0x4200000000000000000000000000000000000042",
  "spend_token": "USDC",
  "spend_amount": 500,
  "strategy": "custom",
  "conditions": {
    "fear_and_greed_below": 25,
    "fear_and_greed_recovering": true,
    "price_below": 2.50
  },
  "max_wait_hours": 72,
  "swap_agent_preference": "axelrod"
}
```

### Sample Deliverable — Executed

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
    "tx_hash": "0xabc123def456789...",
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
    "hours_monitored": 14.1
  }
}
```

### Sample Deliverable — Expired (Refund)

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
      "note": "Approached target but conditions never fully met"
    }
  },
  "refund": {
    "amount": 3000,
    "token": "USDC",
    "status": "returned_to_escrow"
  }
}
```

### Preset Strategies

| Strategy | Conditions |
|---|---|
| `fear_dip_buy` | F&G ≤ 20 AND F&G 24h change > 0 (recovering) |
| `momentum_recovery` | F&G 7d low ≤ 25 AND F&G > 35 AND F&G 3d trend = up |
| `custom` | User-defined via `conditions` object |

---

## Job 4: `take_profit`

**Description:** Conditional sell execution. Monitors for exit conditions (greed exhaustion, momentum fade, or custom) and sells via swap agent when triggers hit. Principal refunded if conditions not met within wait window.

| Field | Value |
|---|---|
| **Name** | `take_profit` |
| **Job Fee** | 0.50 |
| **Job Fee Type** | fixed |
| **Required Funds** | true |
| **SLA (minutes)** | 10080 (168 hours / 7 days) |

### Requirement (JSON Schema)

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

### Sample Request — Preset Strategy

```json
{
  "sell_token": "ETH",
  "sell_amount": 1.5,
  "receive_token": "USDC",
  "strategy": "greed_exit",
  "max_wait_hours": 120
}
```

### Sample Request — Percentage Sell with Custom Strategy

```json
{
  "sell_token": "0x4200000000000000000000000000000000000042",
  "sell_amount": 50,
  "sell_as_percentage": true,
  "receive_token": "USDC",
  "strategy": "custom",
  "conditions": {
    "fear_and_greed_above": 80,
    "fear_and_greed_declining": true,
    "price_above": 3.00
  },
  "max_wait_hours": 168
}
```

### Sample Deliverable — Executed

```json
{
  "status": "executed",
  "execution_time": "2026-02-10T12:30:00Z",
  "conditions_met": {
    "fear_and_greed": 78,
    "fear_and_greed_24h_change": -3,
    "decline_detected": true
  },
  "transaction": {
    "tx_hash": "0xdef456abc789012...",
    "token_sold": "ETH",
    "amount_sold": 1.5,
    "token_received": "USDC",
    "amount_received": 4500,
    "price_at_execution": 3000.00,
    "swap_agent": "axelrod",
    "swap_job_id": 4588
  },
  "monitoring_summary": {
    "total_checks": 2400,
    "hours_monitored": 40.0
  }
}
```

### Sample Deliverable — Expired (Refund)

```json
{
  "status": "expired",
  "reason": "Conditions not met within 168-hour window",
  "monitoring_summary": {
    "total_checks": 10080,
    "hours_monitored": 168.0,
    "closest_to_trigger": {
      "time": "2026-02-12T06:00:00Z",
      "fg": 72,
      "note": "Approached greed threshold but F&G never exceeded 75"
    }
  },
  "refund": {
    "amount": 1.5,
    "token": "ETH",
    "status": "returned_to_escrow"
  }
}
```

### Preset Strategies

| Strategy | Conditions |
|---|---|
| `greed_exit` | F&G ≥ 75 AND F&G 24h change < 0 (declining) |
| `momentum_fade` | F&G 7d high ≥ 70 AND F&G < 60 AND F&G 2d trend = down |
| `custom` | User-defined via `conditions` object |

---

## Registration Notes

- **Requirement schemas** are valid JSON Schema (enforced by `jsonschema.validate()` in the SDK)
- **Deliverable examples** show output structure — not validated as schema
- **`offering.json` format** for ACP CLI: `name`, `description`, `jobFee`, `jobFeeType`, `requiredFunds`, `requirement`
- **Offering names** must be lowercase with underscores only (`[a-z][a-z0-9_]*`)
- **Portal URL:** `https://app.virtuals.io/acp/join`
