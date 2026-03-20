"""AI-powered market narrative generation using an OpenAI-compatible API.

Generates the Consigliere's market analysis — strategic, data-driven,
trader-focused language. Never hypes, always cites data.

Works with any OpenAI-compatible provider (OpenRouter, Together, Groq, etc.).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import openai

from src.data.models import MarketDataCache, Signal
from src.intelligence.signal_detector import map_market_regime

logger = logging.getLogger(__name__)

NARRATOR_PROMPT = """You are the Consigliere — the strategic voice of MAFIA AI. Sharp, cold-blooded, no filler. You've seen every cycle.

Produce exactly THREE narrative fields. Each has one job:

OVERVIEW — 1 sentence. Pure fact. Cite the numbers. No interpretation.
  Example: "F&G at 11, BTC bled 5.2% today — the market is in full capitulation."

ANALYSIS — 1 sentence. What this means in market structure terms. Regime, momentum, rotation.
  Example: "Selling pressure is broad-based with average volume, suggesting distribution rather than a panic flush."

INSIGHT — 1 sentence. The contrarian read. What a seasoned trader thinks RIGHT NOW. Be useful — this is what subscribers pay for.
  - In extreme fear: don't panic, fear marks bottoms, historical context, where to watch for opportunity.
  - In recovery: confirm with volume, position size matters, false dawns are common.
  - In greed/euphoria: smell the trap, protect profits, the crowd is always late.
  - Be direct and actionable. Smart insights are valuable. The only hard limit: no explicit "buy [asset]" or "sell [asset]" commands.
  Example (fear): "Extreme fear historically marks cycle bottoms — the crowd's panic is the Consigliere's signal to keep powder dry and stay ready."
  Example (greed): "The market is euphoric — this is when the smart money quietly reduces exposure while the crowd piles in."

RULES:
1. No explicit "buy [asset]" or "sell [asset]" commands — but smart, directional insights are encouraged.
2. Use ONLY data from market_state. No invented context.
3. Exactly 1 sentence per field. Dense. No passive voice.
4. NEVER reference field names from the payload (no "fg_value", "btc_change_24h", "fg_trajectory", etc.).
5. Tone MUST match the fear_and_greed trajectory. Deepening fear = grim and direct. Recovery = measured optimism. Greed peak = cold warning.

Return ONLY valid JSON:
{
  "overview":  "...",
  "analysis":  "...",
  "insight":   "...",
  "altseason": "rotation_outlook value verbatim",
  "regime":    "trend value verbatim"
}"""

# Deterministic contrarian insight per trajectory — used as fallback and as reference
# for what the LLM's insight should sound like.
_TRAJECTORY_INSIGHTS: dict[str, str] = {
    "Extreme Fear Deepening":      "Capitulation feels endless — but extreme fear historically marks where cycles bottom, not where they keep going.",
    "Extreme Fear Persisting":     "Fear is entrenched, but patience historically outperforms panic at these levels — keep powder dry.",
    "Extreme Fear — Stabilizing":  "Fear may be stabilizing — wait for volume confirmation before reading a trend change.",
    "Fear Intensifying":           "Sentiment is worsening — let the market show its hand before reading strength into any bounce.",
    "Fear Consolidating":          "Fear is holding steady. No edge here — let the structure develop before committing.",
    "Fear — Recovery in Progress": "Recovery is building from oversold territory — trend-followers tend to overstay the fear.",
    "Fear Easing":                 "Sentiment is thawing. Measured positioning outperforms chasing every recovery move.",
    "Neutral — Greed Building":    "Momentum is building, but neutrality cuts both ways — stay disciplined and size accordingly.",
    "Neutral — Softening":         "The market is losing momentum. Don't chase moves in either direction.",
    "Neutral":                     "No strong sentiment edge. Wait for conviction before committing size.",
    "Greed Building":              "Greed is accelerating — protection costs less than regret when the crowd is this confident.",
    "Greed Cooling":               "Greed is fading. When conviction drops, so does support — guard your positions.",
    "Greed Persisting":            "The trend holds, but exits get crowded fast when sentiment turns — stay light on your feet.",
    "Extreme Greed Accelerating":  "The market is euphoric. This is when the smart money quietly reduces exposure while the crowd piles in.",
    "Extreme Greed Cooling":       "Euphoria is fading — corrections from extreme greed tend to be sharp and fast.",
    "Extreme Greed Persisting":    "Extreme greed rarely lasts. Protect your upside before the crowd wakes up.",
}


def _trajectory_insight(trajectory: str) -> str:
    return _TRAJECTORY_INSIGHTS.get(
        trajectory,
        "Market conditions are mixed — maintain discipline and wait for clearer signals.",
    )


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
    market_context = _build_llm_context(regimes, signals)

    client = openai.AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=30.0)
    messages = [
        {
            "role": "user",
            "content": f"{NARRATOR_PROMPT}\n\nMarket Data:\n{json.dumps(market_context, indent=2)}",
        }
    ]

    last_error: Exception | None = None
    for attempt in range(2):
        if attempt > 0:
            await asyncio.sleep(3)
            logger.info("[NARRATOR] Retrying LLM call (attempt %d)", attempt + 1)
        try:
            response = await client.chat.completions.create(
                model=model,
                max_tokens=400,
                messages=messages,
            )
            result = json.loads(response.choices[0].message.content)
            if not _is_sentiment_consistent(result, regimes):
                logger.warning(
                    "[NARRATOR] Sentiment inconsistency for trajectory '%s' — using fallback",
                    regimes.get("fg_trajectory", ""),
                )
                return _fallback_analysis(data, signals)
            return {
                "overview":  result.get("overview", ""),
                "analysis":  result.get("analysis", ""),
                "insight":   result.get("insight", ""),
                "altseason": result.get("altseason", regimes.get("altseason_signal", "")),
                "signals":   [s.to_dict() for s in signals],
                "regime":    regimes["trend_regime"],
            }
        except Exception as e:
            last_error = e
            logger.warning("[NARRATOR] LLM attempt %d failed: %s", attempt + 1, e)

    logger.error("[NARRATOR] All LLM attempts failed, using fallback. Last error: %s", last_error)
    return _fallback_analysis(data, signals)


def _build_llm_context(regimes: dict, signals: list[Signal]) -> dict:
    """Format regimes into human-readable labels so the LLM can't cite field names verbatim."""
    btc_24h = regimes.get("btc_change_24h", 0.0)
    btc_7d = regimes.get("btc_change_7d", 0.0)
    return {
        "market_state": {
            "fear_and_greed": f"{regimes['fg_value']} — {regimes['fg_trajectory']}",
            "trend": regimes["trend_regime"],
            "volume": regimes["volume_regime"],
            "dominance": regimes["dominance_regime"],
            "rotation_outlook": regimes["altseason_signal"],
            "btc_performance": f"{btc_24h:+.1f}% today / {btc_7d:+.1f}% this week",
        },
        "signals": [s.to_dict() for s in signals],
    }


def _is_sentiment_consistent(result: dict, regimes: dict) -> bool:
    """Reject responses that contradict a clearly bearish trajectory."""
    trajectory = regimes.get("fg_trajectory", "")
    clearly_bearish = ("Deepening" in trajectory or "Intensifying" in trajectory) and "Fear" in trajectory
    if clearly_bearish:
        combined = " ".join([result.get("overview", ""), result.get("insight", "")])
        if re.search(r"\bbullish\b", combined, re.IGNORECASE):
            return False
    return True


def _fallback_analysis(data: MarketDataCache, signals: list[Signal]) -> dict[str, Any]:
    """Generate a basic analysis without AI when the LLM is unavailable."""
    regimes = map_market_regime(data)

    # Overview: factual snapshot
    overview_parts = [f"F&G at {data.fg_value} ({data.fg_classification})."]
    if data.btc_change_24h != 0:
        direction = "up" if data.btc_change_24h > 0 else "down"
        overview_parts.append(f"BTC {direction} {abs(data.btc_change_24h):.1f}% today.")
    if data.btc_dominance > 0 and data.btc_dominance_change_24h != 0:
        overview_parts.append(
            f"BTC dominance at {data.btc_dominance:.1f}% "
            f"({'rising' if data.btc_dominance_change_24h > 0 else 'falling'})."
        )
    overview = " ".join(overview_parts)

    # Analysis: regime label
    analysis = regimes["trend_regime"] + "."

    # Insight: deterministic contrarian read keyed by trajectory
    insight = _trajectory_insight(regimes.get("fg_trajectory", ""))

    return {
        "overview":  overview,
        "analysis":  analysis,
        "insight":   insight,
        "altseason": regimes.get("altseason_signal", ""),
        "signals":   [s.to_dict() for s in signals],
        "regime":    regimes["trend_regime"],
    }
