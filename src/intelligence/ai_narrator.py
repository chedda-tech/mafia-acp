"""AI-powered market narrative generation using an OpenAI-compatible API.

Generates the Consigliere's market analysis — strategic, data-driven,
trader-focused language. Never hypes, always cites data.

Works with any OpenAI-compatible provider (OpenRouter, Together, Groq, etc.).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import openai

from src.data.models import MarketDataCache, Signal
from src.intelligence.signal_detector import map_market_regime

logger = logging.getLogger(__name__)

NARRATOR_PROMPT = """You are the Consigliere — MAFIA AI's strategic advisor.
Analyze the provided market regimes and provide a brief, trader-focused summary.
Speak with authority. Cite specific numbers in the regimes.

CRITICAL RULES:
1. NEVER GIVE "BUY", "SELL", OR EXPLICIT FINANCIAL ADVICE. You are a commentator, not a financial advisor.
2. Rely EXCLUSIVELY on the deterministic regimes provided in the payload (Trend, Sentiment, Dominance, Volume). Form your narrative explicitly around these mappings.
3. 2-3 sentences max for the summary.
4. Reference specific F&G values and price changes mapped in the regimes.
5. Use trader-native language (e.g. risk-off rotation, capitulation, exhaustion, etc.) strictly matching the rules given.

Return ONLY valid JSON in this exact structure:
{
  "summary": "2-3 sentences describing the current deterministic regimes",
  "regime": "The string mapped as 'trend_regime' inside the prompt payload"
}"""


async def generate_narrative(
    data: MarketDataCache,
    signals: list[Signal],
    *,
    base_url: str,
    api_key: str,
    model: str,
) -> dict[str, Any]:
    """Generate AI market narrative from structured data.

    Falls back to a data-only response if the LLM API call fails.
    """
    if not api_key:
        logger.warning("No LLM API key — returning data-only analysis")
        return _fallback_analysis(data, signals)

    regimes = map_market_regime(data)

    market_context = {
        "regimes": regimes,
        "btc_price": data.btc_price,
        "btc_dominance": data.btc_dominance,
        "eth_price": data.eth_price,
        "sol_price": data.sol_price,
        "signals": [s.to_dict() for s in signals],
    }

    try:
        client = openai.AsyncOpenAI(base_url=base_url, api_key=api_key)
        response = await client.chat.completions.create(
            model=model,
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"{NARRATOR_PROMPT}\n\nMarket Data:\n{json.dumps(market_context, indent=2)}"
                    ),
                }
            ],
        )

        result = json.loads(response.choices[0].message.content)

        return {
            "summary": result.get("summary", ""),
            "signals": [s.to_dict() for s in signals],
            "regime": regimes["trend_regime"],
        }

    except Exception as e:
        logger.error("LLM narrative generation failed: %s", e)
        return _fallback_analysis(data, signals)


def _fallback_analysis(data: MarketDataCache, signals: list[Signal]) -> dict[str, Any]:
    """Generate a basic analysis without AI when the LLM is unavailable."""
    regimes = map_market_regime(data)

    parts = [f"F&G at {data.fg_value} ({data.fg_classification})."]

    if data.fg_change_24h != 0:
        direction = "up" if data.fg_change_24h > 0 else "down"
        parts.append(f"Sentiment {direction} {abs(data.fg_change_24h):.0f} pts in 24h.")

    if data.btc_dominance > 0 and data.btc_dominance_change_24h != 0:
        parts.append(
            f"BTC dominance at {data.btc_dominance:.1f}% "
            f"({'rising' if data.btc_dominance_change_24h > 0 else 'falling'})."
        )

    return {
        "summary": " ".join(parts),
        "signals": [s.to_dict() for s in signals],
        "regime": regimes["trend_regime"],
    }
