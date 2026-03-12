"""Job offering definitions for the MAFIA ACP agent.

These define the 4 services MAFIA provides via ACP:
1. fear_and_greed — Simple F&G data ($0.10)
2. market_sentiment — Full market analysis ($0.25)
3. smart_buy — Conditional buy execution ($0.50)
4. take_profit — Conditional sell execution ($0.50)
"""

from __future__ import annotations

import json

# --- Requirement Schemas ---

FEAR_AND_GREED_REQUIREMENTS = json.dumps(
    {
        "type": "object",
        "properties": {},
        "description": "No input required. Returns current market sentiment snapshot.",
    }
)

MARKET_SENTIMENT_REQUIREMENTS = json.dumps(
    {
        "type": "object",
        "properties": {
            "focus_assets": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional. Assets to highlight. Defaults to ['BTC', 'ETH', 'SOL'].",
            },
            "include_analysis": {
                "type": "boolean",
                "default": True,
                "description": "Whether to include AI narrative interpretation.",
            },
        },
    }
)

SMART_BUY_REQUIREMENTS = json.dumps(
    {
        "type": "object",
        "required": ["buy_token", "spend_amount", "spend_token"],
        "properties": {
            "buy_token": {
                "type": "string",
                "description": "Token to purchase (symbol or contract address)",
            },
            "spend_token": {"type": "string", "default": "USDC", "description": "Token to spend"},
            "spend_amount": {"type": "number", "description": "Amount of spend_token to use"},
            "strategy": {
                "type": "string",
                "enum": ["fear_dip_buy", "momentum_recovery", "custom"],
                "default": "fear_dip_buy",
            },
            "conditions": {
                "type": "object",
                "description": "Custom conditions (when strategy='custom')",
                "properties": {
                    "fear_and_greed_below": {"type": "number"},
                    "fear_and_greed_recovering": {"type": "boolean"},
                    "price_below": {"type": "number"},
                    "btc_dominance_above": {"type": "number"},
                },
            },
            "max_wait_hours": {"type": "number", "default": 72},
            "swap_agent_preference": {"type": "string"},
        },
    }
)

TAKE_PROFIT_REQUIREMENTS = json.dumps(
    {
        "type": "object",
        "required": ["sell_token", "sell_amount"],
        "properties": {
            "sell_token": {"type": "string", "description": "Token to sell"},
            "sell_amount": {"type": "number", "description": "Amount to sell"},
            "sell_as_percentage": {"type": "boolean", "default": False},
            "receive_token": {"type": "string", "default": "USDC"},
            "strategy": {
                "type": "string",
                "enum": ["greed_exit", "momentum_fade", "custom"],
                "default": "greed_exit",
            },
            "conditions": {
                "type": "object",
                "properties": {
                    "fear_and_greed_above": {"type": "number"},
                    "fear_and_greed_declining": {"type": "boolean"},
                    "price_above": {"type": "number"},
                    "btc_dominance_below": {"type": "number"},
                },
            },
            "max_wait_hours": {"type": "number", "default": 168},
        },
    }
)

# --- Deliverable Schemas ---

FEAR_AND_GREED_DELIVERABLE = json.dumps(
    {
        "fear_and_greed": 50,
        "classification": "neutral",
        "change_1h": 0,
        "change_24h": 0,
        "change_7d": 0,
        "change_30d": 0,
        "timestamp": "2026-01-01T00:00:00Z",
        "source": "mafia_terminal",
    }
)

MARKET_SENTIMENT_DELIVERABLE = json.dumps(
    {
        "timestamp": "2026-01-01T00:00:00Z",
        "fear_and_greed": {"value": 50, "classification": "neutral"},
        "btc_dominance": {"value": 50.0, "trend": "flat"},
        "total_market_cap": {"value_usd": "2.0T"},
        "assets": [],
        "analysis": {"summary": "", "signals": [], "outlook": "neutral"},
        "source": "mafia_terminal",
    }
)


# --- Offering Definitions ---

# These are the params used to register offerings with the ACP agent registry.
# The actual registration is done via the ACP portal or CLI, not in code.
# This module provides the schemas for reference and for the router to validate against.

OFFERINGS = {
    "fear_and_greed": {
        "name": "fear_and_greed",
        "description": (
            "Current Fear & Greed Index with trend context. "
            "Returns F&G value, classification, and multi-period changes."
        ),
        "price": 0.10,
        "required_funds": False,
        "sla_minutes": 1,
        "requirement": FEAR_AND_GREED_REQUIREMENTS,
        "deliverable": FEAR_AND_GREED_DELIVERABLE,
    },
    "market_sentiment": {
        "name": "market_sentiment",
        "description": (
            "Comprehensive market intelligence report. F&G, BTC dominance, "
            "asset metrics, signal detection, and AI-generated analysis."
        ),
        "price": 0.25,
        "required_funds": False,
        "sla_minutes": 2,
        "requirement": MARKET_SENTIMENT_REQUIREMENTS,
        "deliverable": MARKET_SENTIMENT_DELIVERABLE,
    },
    "smart_buy": {
        "name": "smart_buy",
        "description": (
            "Conditional buy execution. Monitors market conditions and "
            "executes via swap agent when conditions align."
        ),
        "price": 0.50,
        "required_funds": True,
        "sla_minutes": 4320,  # 72 hours
        "requirement": SMART_BUY_REQUIREMENTS,
    },
    "take_profit": {
        "name": "take_profit",
        "description": (
            "Conditional sell execution. Monitors for exit conditions "
            "and sells via swap agent when triggers hit."
        ),
        "price": 0.50,
        "required_funds": True,
        "sla_minutes": 10080,  # 168 hours
        "requirement": TAKE_PROFIT_REQUIREMENTS,
    },
}
