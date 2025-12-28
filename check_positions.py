#!/usr/bin/env python3
"""Check open positions on OANDA"""

import os
from dotenv import load_dotenv
from oandapyV20 import API
from oandapyV20.endpoints import positions, trades

load_dotenv()

api_key = os.getenv("OANDA_API_KEY")
account_id = os.getenv("OANDA_ACCOUNT_ID")
api = API(access_token=api_key, environment="practice")

print("=" * 60)
print("OANDA Open Positions")
print("=" * 60)

# Get open positions
endpoint = positions.OpenPositions(accountID=account_id)
response = api.request(endpoint)

for pos in response.get("positions", []):
    instrument = pos["instrument"]
    long_units = float(pos["long"]["units"])
    short_units = float(pos["short"]["units"])
    unrealized_pl = float(pos["unrealizedPL"])

    if long_units != 0:
        avg_price = pos["long"].get("averagePrice", "N/A")
        print(
            f"📈 {instrument}: LONG {int(long_units)} units @ {avg_price}, P/L: ${unrealized_pl:.2f}"
        )
    if short_units != 0:
        avg_price = pos["short"].get("averagePrice", "N/A")
        print(
            f"📉 {instrument}: SHORT {int(abs(short_units))} units @ {avg_price}, P/L: ${unrealized_pl:.2f}"
        )

print("\n" + "=" * 60)
print("Open Trades")
print("=" * 60)

# Get open trades
endpoint = trades.OpenTrades(accountID=account_id)
response = api.request(endpoint)

for trade in response.get("trades", []):
    trade_id = trade["id"]
    instrument = trade["instrument"]
    units = int(trade["currentUnits"])
    price = trade["price"]
    unrealized_pl = float(trade["unrealizedPL"])
    direction = "LONG" if units > 0 else "SHORT"

    print(
        f"Trade #{trade_id}: {instrument} {direction} {abs(units)} units @ {price}, P/L: ${unrealized_pl:.2f}"
    )
