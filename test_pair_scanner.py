"""
Simplified Pair Scanner Test

Tests pair ranking based on spread, volatility, and trend WITHOUT model prediction.
This gives us immediate results to see which pairs are tradeable.
"""

import sys

sys.path.append("/Users/eatonjd/Github/forex_bot")

from utils.oanda_connector import OANDAConnector
import pandas as pd
import json
from datetime import datetime

print("=" * 60)
print("🔍 SIMPLIFIED PAIR SCANNER TEST")
print("=" * 60)

# Initialize OANDA
print("\n1. Connecting to OANDA...")
oanda = OANDAConnector(environment="practice")
print(f"   ✅ Connected - Account: {oanda.account_id}")

# Major pairs to scan
MAJOR_PAIRS = [
    "EUR_USD",
    "GBP_USD",
    "USD_JPY",
    "AUD_USD",
    "NZD_USD",
    "EUR_GBP",
    "EUR_JPY",
    "USD_CAD",
    "USD_CHF",
]

print(f"\n2. Scanning {len(MAJOR_PAIRS)} major forex pairs...")
print("=" * 60)

results = []

for symbol in MAJOR_PAIRS:
    try:
        # Get current price
        price_data = oanda.get_current_price(symbol)
        if not price_data:
            print(f"   ⚠️  {symbol}: No price data")
            continue

        spread_pips = price_data.get("spread", 10.0)

        # Get candles for volatility calculation
        candles = oanda.get_candles(symbol, granularity="H1", count=20)
        if not candles:
            print(f"   ⚠️  {symbol}: No candles")
            continue

        df = pd.DataFrame(candles)

        # Calculate simple volatility (high-low range average)
        df["range"] = (df["high"] - df["low"]).astype(float)
        avg_range = df["range"].mean()

        # Score based on spread and volatility
        spread_score = 10 - min(spread_pips, 5) * 2  # Lower spread = better
        volatility_score = (
            8 if 0.001 <= avg_range <= 0.003 else 5
        )  # Moderate volatility = better

        total_score = (spread_score * 0.6) + (
            volatility_score * 0.4
        )  # Weight spread more

        results.append(
            {
                "symbol": symbol,
                "score": round(total_score, 2),
                "spread": round(spread_pips, 2),
                "volatility": round(avg_range, 5),
                "spread_ok": spread_pips <= 3.0,
            }
        )

        status = "✅" if spread_pips <= 3.0 else "❌"
        print(
            f"   {status} {symbol}: Spread={spread_pips:.1f} pips, Vol={avg_range:.5f}, Score={total_score:.1f}/10"
        )

    except Exception as e:
        print(f"   ⚠️  {symbol}: Error - {e}")

# Sort by score
results.sort(key=lambda x: x["score"], reverse=True)

print("\n" + "=" * 60)
print("📊 TOP RANKED PAIRS")
print("=" * 60)

for i, pair in enumerate(results[:5], 1):
    status = "✅ TRADEABLE" if pair["spread_ok"] else "❌ WIDE SPREAD"
    print(f"\n{i}. {pair['symbol']} - Score: {pair['score']}/10 {status}")
    print(f"   • Spread: {pair['spread']} pips")
    print(f"   • Volatility: {pair['volatility']}")

# Save results
scanner_results = {
    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "pairs": [
        {
            "symbol": p["symbol"],
            "score": p["score"],
            "spread": p["spread"],
            "trend": "unknown",  # Would need RL model for this
        }
        for p in results[:3]
    ],
}

with open("pair_scanner_results.json", "w") as f:
    json.dump(scanner_results, f, indent=2)

print("\n" + "=" * 60)
print("✅ Results saved to pair_scanner_results.json")
print(f"   Dashboard will display top {len(scanner_results['pairs'])} pairs")
print("=" * 60)
