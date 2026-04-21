#!/usr/bin/env python3
"""
Analyze all trades by direction (long/short) and outcome (win/loss)
"""

import os
from dotenv import load_dotenv
from oandapyV20 import API
from oandapyV20.endpoints.trades import TradesList

load_dotenv()

api = API(access_token=os.getenv("OANDA_API_KEY"), environment="practice")
account_id = os.getenv("OANDA_ACCOUNT_ID")

# Fetch all closed trades
all_trades = []
params = {"state": "CLOSED", "count": 500, "instrument": "USD_JPY"}
r = TradesList(accountID=account_id, params=params)
api.request(r)
all_trades.extend(r.response.get("trades", []))

print(f"\n{'=' * 60}")
print(f"TRADE DIRECTION ANALYSIS - {len(all_trades)} Total Trades")
print(f"{'=' * 60}\n")

# Categorize trades
long_winners = []
long_losers = []
short_winners = []
short_losers = []

for t in all_trades:
    units = int(t.get("initialUnits", 0))
    pnl = float(t.get("realizedPL", 0))

    is_long = units > 0
    is_winner = pnl > 0

    if is_long and is_winner:
        long_winners.append(t)
    elif is_long and not is_winner:
        long_losers.append(t)
    elif not is_long and is_winner:
        short_winners.append(t)
    else:
        short_losers.append(t)

total_winners = len(long_winners) + len(short_winners)
total_losers = len(long_losers) + len(short_losers)
total_longs = len(long_winners) + len(long_losers)
total_shorts = len(short_winners) + len(short_losers)

print("📊 BREAKDOWN BY DIRECTION")
print("-" * 40)
print(f"LONG trades:  {total_longs:3} ({total_longs / len(all_trades) * 100:.1f}%)")
print(f"SHORT trades: {total_shorts:3} ({total_shorts / len(all_trades) * 100:.1f}%)")

print(f"\n📈 WINNERS ({total_winners} total)")
print("-" * 40)
if total_winners > 0:
    print(
        f"  Long winners:  {len(long_winners):3} ({len(long_winners) / total_winners * 100:.1f}% of winners)"
    )
    print(
        f"  Short winners: {len(short_winners):3} ({len(short_winners) / total_winners * 100:.1f}% of winners)"
    )

print(f"\n📉 LOSERS ({total_losers} total)")
print("-" * 40)
if total_losers > 0:
    print(
        f"  Long losers:  {len(long_losers):3} ({len(long_losers) / total_losers * 100:.1f}% of losers)"
    )
    print(
        f"  Short losers: {len(short_losers):3} ({len(short_losers) / total_losers * 100:.1f}% of losers)"
    )

print(f"\n🎯 WIN RATE BY DIRECTION")
print("-" * 40)
if total_longs > 0:
    print(
        f"  Long win rate:  {len(long_winners) / total_longs * 100:.1f}% ({len(long_winners)}/{total_longs})"
    )
if total_shorts > 0:
    print(
        f"  Short win rate: {len(short_winners) / total_shorts * 100:.1f}% ({len(short_winners)}/{total_shorts})"
    )

# P/L by direction
long_pnl = sum(float(t.get("realizedPL", 0)) for t in long_winners + long_losers)
short_pnl = sum(float(t.get("realizedPL", 0)) for t in short_winners + short_losers)

print(f"\n💰 P/L BY DIRECTION")
print("-" * 40)
print(f"  Long P/L:  ${long_pnl:+,.2f}")
print(f"  Short P/L: ${short_pnl:+,.2f}")
print(f"  Total:     ${long_pnl + short_pnl:+,.2f}")

print(f"\n{'=' * 60}\n")
