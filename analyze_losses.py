#!/usr/bin/env python3
"""Fetch and analyze recent losing trades from OANDA"""

import os
import sys
from oandapyV20 import API
from oandapyV20.endpoints.trades import TradesList
from datetime import datetime
import json

# Load env vars
api_key = os.getenv("OANDA_API_KEY")
account_id = os.getenv("OANDA_ACCOUNT_ID")

if not api_key or not account_id:
    print("Error: OANDA_API_KEY or OANDA_ACCOUNT_ID not set")
    sys.exit(1)

# Connect to OANDA
api = API(access_token=api_key, environment="practice")

# Fetch all closed trades
params = {"instrument": "USD_JPY", "state": "CLOSED", "count": 100}
r = TradesList(accountID=account_id, params=params)
api.request(r)

trades = r.response.get("trades", [])
print(f"\n📊 Total closed trades: {len(trades)}")

# Filter to losers only
losers = [t for t in trades if float(t.get("realizedPL", 0)) < 0]
print(f"❌ Total losing trades: {len(losers)}")

# Get last 6 losers
last_6_losers = sorted(losers, key=lambda x: x.get("closeTime", ""), reverse=True)[:6]

print(f"\n{'=' * 80}")
print("LAST 6 LOSING TRADES")
print(f"{'=' * 80}\n")

for i, trade in enumerate(last_6_losers, 1):
    print(f"--- LOSS #{i} ---")
    print(f"Trade ID: {trade.get('id')}")
    print(f"Open Time: {trade.get('openTime', '')}")
    print(f"Close Time: {trade.get('closeTime', '')}")

    # Calculate holding time
    if trade.get("openTime") and trade.get("closeTime"):
        open_dt = datetime.fromisoformat(trade.get("openTime").replace("Z", "+00:00"))
        close_dt = datetime.fromisoformat(trade.get("closeTime").replace("Z", "+00:00"))
        holding_time = close_dt - open_dt
        print(f"Holding Time: {holding_time}")

    units = int(float(trade.get("initialUnits", trade.get("currentUnits", 0))))
    direction = "LONG" if units > 0 else "SHORT"
    print(f"Direction: {direction}")
    print(f"Units: {abs(units):,}")
    print(f"Entry Price: {float(trade.get('price', 0)):.5f}")
    print(f"Average Close Price: {float(trade.get('averageClosePrice', 0)):.5f}")

    realized_pl = float(trade.get("realizedPL", 0))
    print(f"Realized P/L: ${realized_pl:.2f}")

    # Calculate pips
    entry = float(trade.get("price", 0))
    close = float(trade.get("averageClosePrice", 0))
    if direction == "LONG":
        pips = (close - entry) * 100  # USD/JPY pips
    else:
        pips = (entry - close) * 100
    print(f"Pips: {pips:.1f}")

    print()

# Save to JSON for further analysis
with open("last_6_losses.json", "w") as f:
    json.dump(last_6_losers, f, indent=2)

print(f"\n✅ Saved detailed data to last_6_losses.json")
