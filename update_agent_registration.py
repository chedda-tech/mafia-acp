import re

filepath = "docs/AGENT_REGISTRATION.md"

with open(filepath, "r") as f:
    text = f.read()

# Replace fear_and_greed Sample Deliverable format completely
pattern_fg = r'### Sample Deliverable\n+```json\n\{\n  "fear_and_greed": 22.*?"source": "mafia_terminal"\n\}\n```'
new_fg = '''### Sample Deliverable

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
```'''

# Replace market_sentiment Deliverable format completely
pattern_ms = r'### Sample Deliverable\n+```json\n\{\n  "timestamp": "2026-02-08T14:30:00Z",\n  "fear_and_greed": \{.*?"outlook": "bearish_short_term_bullish_medium_term"\n  \},\n  "source": "mafia_terminal"\n\}\n```'
new_ms = '''### Sample Deliverable

```json
{
  "timestamp": "2026-02-08T14:30:00Z",
  "regimes": {
    "sentiment_regime": "Extreme Fear",
    "trend_regime": "Capitulation / Distribution regime",
    "volume_regime": "Average trading activity",
    "dominance_regime": "Flight to safety / BTC outperformance",
    "btc_change_24h": -2.1,
    "btc_change_7d": -5.4,
    "fg_value": 22
  },
  "fear_and_greed": {
    "value": 22,
    "classification": "extreme_fear",
    "change_24h": -7,
    "change_7d": -12,
    "change_30d": -24
  },
  "btc_dominance": {
    "value": 58.3,
    "change_24h": 0.8,
    "trend": "rising"
  },
  "total_market_cap": {
    "value_usd": "2.1T",
    "change_24h": -3.2,
    "change_7d": -8.1
  },
  "assets": [
    {
      "symbol": "BTC",
      "price": 94250,
      "change_24h": -2.1,
      "change_7d": -5.4,
      "volume_24h": "28.5B",
      "volume_change_24h": 45.2
    },
    {
      "symbol": "ETH",
      "price": 2857,
      "change_24h": -3.5,
      "change_7d": -8.2,
      "volume_24h": "14.2B",
      "volume_change_24h": 38.7
    }
  ],
  "source": "mafia_terminal",
  "analysis": {
    "summary": "F&G at 22 (extreme_fear). Sentiment down 7 pts in 24h. BTC dominance at 58.3% (rising).",
    "signals": [
      {
        "signal": "fear_capitulation",
        "strength": "strong",
        "description": "F&G at 22 with 45% volume spike — heavy selling pressure"
      },
      {
        "signal": "btc_dominance_rising",
        "strength": "moderate",
        "description": "BTC dominance up 0.8% over 24h — capital rotating out of alts"
      }
    ],
    "regime": "Capitulation / Distribution regime"
  }
}
```'''

text = re.sub(pattern_fg, new_fg, text, flags=re.DOTALL)
text = re.sub(pattern_ms, new_ms, text, flags=re.DOTALL)

with open(filepath, "w") as f:
    f.write(text)

print("Done replacing JSON schemas!")
