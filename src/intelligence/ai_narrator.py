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

from src.data.models import MarketDataCache, MarketOutlook, Signal

logger = logging.getLogger(__name__)

NARRATOR_PROMPT = """You are the Consigliere — MAFIA AI's strategic advisor.
Analyze this market data and provide a brief, trader-focused summary.
Speak with authority. Cite specific numbers. Never hype.

Rules:
- 2-3 sentences max for the summary
- Reference specific F&G values, price changes, and dominance shifts
- Use trader-native language (risk-off rotation, capitulation, exhaustion, etc.)
- Be direct about what the data suggests, not what you think will happen

Return ONLY valid JSON:
{"summary": "2-3 sentences", "outlook": "bullish_short_term | bearish_short_term | neutral"}"""


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

    market_context = {
        "fear_and_greed": data.fg_value,
        "fg_classification": data.fg_classification,
        "fg_change_24h": data.fg_change_24h,
        "fg_change_7d": data.fg_change_7d,
        "btc_price": data.btc_price,
        "btc_change_24h": data.btc_change_24h,
        "btc_dominance": data.btc_dominance,
        "btc_dominance_change_24h": data.btc_dominance_change_24h,
        "eth_price": data.eth_price,
        "eth_change_24h": data.eth_change_24h,
        "sol_price": data.sol_price,
        "sol_change_24h": data.sol_change_24h,
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
        # Validate outlook is a valid enum value
        outlook = result.get("outlook", "neutral")
        valid_outlooks = [o.value for o in MarketOutlook]
        if outlook not in valid_outlooks:
            outlook = "neutral"

        return {
            "summary": result.get("summary", ""),
            "signals": [s.to_dict() for s in signals],
            "outlook": outlook,
        }

    except Exception as e:
        logger.error("LLM narrative generation failed: %s", e)
        return _fallback_analysis(data, signals)


def _fallback_analysis(data: MarketDataCache, signals: list[Signal]) -> dict[str, Any]:
    """Generate a basic analysis without AI when the LLM is unavailable."""
    outlook = _determine_outlook(data, signals)

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
        "outlook": outlook,
    }


def _determine_outlook(data: MarketDataCache, signals: list[Signal]) -> str:
    """Determine market outlook from data and signals."""
    signal_types = {s.signal for s in signals}

    if "fear_capitulation" in signal_types:
        return MarketOutlook.BEARISH_SHORT_BULLISH_MEDIUM.value
    if "greed_exhaustion" in signal_types:
        return MarketOutlook.BULLISH_SHORT_BEARISH_MEDIUM.value
    if data.fg_value < 25:
        return MarketOutlook.BEARISH_SHORT_TERM.value
    if data.fg_value > 75:
        return MarketOutlook.BULLISH_SHORT_TERM.value
    return MarketOutlook.NEUTRAL.value
