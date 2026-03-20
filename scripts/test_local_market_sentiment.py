import asyncio
import json
from pprint import pprint

from src.agent.config import Settings
from src.data.cache import DataCache
from src.data.terminal_feed import TerminalFeed
from src.intelligence.signal_detector import map_market_regime, detect_signals
from src.intelligence.ai_narrator import generate_narrative

async def main():
    print("1. Loading config...")
    settings = Settings()
    
    print(f"Target MAFIA_API_BASE_URL: {settings.mafia_api_base_url}")
    
    print("\n2. Initializing cache and feed...")
    cache = DataCache()
    feed = TerminalFeed(settings=settings, cache=cache)
    
    print("\n3. Refreshing feed (Calling Mafia API & Alternative.me)...")
    await feed._refresh()
    
    data = cache._data
    if not data:
        print("Failed to get market data cache.")
        return

    print("\n================== PARSED METRICS ==================")
    print(f"BTC Price:          ${data.btc_price:,.2f}")
    print(f"ETH Price:          ${data.eth_price:,.2f}")
    print(f"SOL Price:          ${data.sol_price:,.2f}")
    print(f"BTC 24h Change:      {data.btc_change_24h:.2f}%")
    print(f"ETH 24h Change:      {data.eth_change_24h:.2f}%")
    print(f"SOL 24h Change:      {data.sol_change_24h:.2f}%")
    print(f"BTC 7d Change:       {data.btc_change_7d:.2f}%")
    print(f"BTC Dominance:       {data.btc_dominance:.2f}%")
    print(f"Total Market Cap:   ${data.total_market_cap:,.2f}")
    print(f"Fear & Greed Value:  {data.fg_value} ({data.fg_classification})")
    
    print("\n================== DETERMINISTIC REGIMES ==================")
    regimes = map_market_regime(data)
    for k, v in regimes.items():
         print(f"{k}: {v}")
    
    print("\n================== DETECTED SIGNALS ==================")
    signals = detect_signals(data)
    if signals:
         for s in signals:
              print(f"- {s.signal} ({s.strength}): {s.description}")
    else:
         print("No signals triggered.")
    
    print("\n================== AI CONSIGLIERE NARRATIVE ==================")
    try:
        narrative = await generate_narrative(
            data,
            signals,
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
        )
        print(json.dumps(narrative, indent=2))
    except Exception as e:
        print(f"Failed to generate narrative: {e}")

if __name__ == "__main__":
    asyncio.run(main())