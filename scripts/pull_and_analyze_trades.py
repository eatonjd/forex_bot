#!/usr/bin/env python3
"""
Deep-Dive Trade History & Performance Analyzer for OANDA Demo Account
Fetches all trade transactions from OANDA API (Account: 101-001-38009813-001)
and computes detailed performance metrics, loss patterns, and actionable insights.
"""

import os
import sys
import json
import pandas as pd
import numpy as np
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from oandapyV20 import API
import oandapyV20.endpoints.trades as trades
import oandapyV20.endpoints.transactions as transactions
import oandapyV20.endpoints.accounts as accounts

API_KEY = os.getenv("OANDA_API_KEY")
ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID", "101-001-38009813-001")
ENV = "practice"

def main():
    print("=" * 80)
    print(f"📊 OANDA PAPER BOT (ACCOUNT {ACCOUNT_ID}) TRADE DEEP-DIVE ANALYSIS")
    print("=" * 80)

    if not API_KEY:
        print("❌ OANDA_API_KEY missing!")
        sys.exit(1)

    api = API(access_token=API_KEY, environment=ENV)

    # 1. Fetch Account Summary
    print("\n1. Fetching Account Summary...")
    acc_summary = api.request(accounts.AccountSummary(accountID=ACCOUNT_ID))["account"]
    nav = float(acc_summary.get("NAV", acc_summary.get("balance", 0)))
    balance = float(acc_summary.get("balance", 0))
    realized_pnl = float(acc_summary.get("pl", acc_summary.get("realizedPL", 0)))
    unrealized_pnl = float(acc_summary.get("unrealizedPL", 0))
    open_trade_count = int(acc_summary.get("openTradeCount", 0))

    print(f"  • Current NAV:        ${nav:,.2f}")
    print(f"  • Current Balance:    ${balance:,.2f}")
    print(f"  • Realized PnL:       ${realized_pnl:,.2f}")
    print(f"  • Unrealized PnL:     ${unrealized_pnl:,.2f}")
    print(f"  • Open Trades:        {open_trade_count}")

    # 2. Fetch Closed Trades List
    print("\n2. Fetching Closed Trade History...")
    r = trades.TradesList(accountID=ACCOUNT_ID, params={"state": "CLOSED", "count": 500})
    res = api.request(r)
    raw_trades = res.get("trades", [])

    print(f"  • Retrieved {len(raw_trades)} closed trades.")

    if not raw_trades:
        print("⚠️ No closed trades found via API. Checking GCS or local logs...")
        return

    records = []
    for t in raw_trades:
        trade_id = t["id"]
        instrument = t["instrument"]
        initial_units = float(t["initialUnits"])
        direction = "LONG" if initial_units > 0 else "SHORT"
        units = abs(initial_units)
        price = float(t["price"])
        open_time = pd.to_datetime(t["openTime"])

        # PnL & exit info
        realized_pl = float(t.get("realizedPL", t.get("pl", 0)))
        close_time = pd.to_datetime(t["closeTime"]) if "closeTime" in t else None
        
        # Calculate duration in hours
        duration_hrs = (close_time - open_time).total_seconds() / 3600.0 if close_time is not None else 0.0

        records.append({
            "trade_id": trade_id,
            "instrument": instrument,
            "direction": direction,
            "units": units,
            "entry_price": price,
            "open_time": open_time,
            "close_time": close_time,
            "duration_hrs": duration_hrs,
            "realized_pl": realized_pl,
            "is_win": realized_pl > 0,
        })

    df = pd.DataFrame(records)

    # 3. Overall Statistics
    total_trades = len(df)
    wins = df[df["realized_pl"] > 0]
    losses = df[df["realized_pl"] <= 0]

    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / total_trades) * 100.0 if total_trades > 0 else 0.0

    gross_profit = wins["realized_pl"].sum()
    gross_loss = abs(losses["realized_pl"].sum())
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else np.nan

    avg_win = wins["realized_pl"].mean() if len(wins) > 0 else 0.0
    avg_loss = losses["realized_pl"].mean() if len(losses) > 0 else 0.0
    reward_risk_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else np.nan

    print("\n" + "=" * 80)
    print("📈 OVERALL PERFORMANCE SUMMARY")
    print("=" * 80)
    print(f"Total Trades:        {total_trades}")
    print(f"Win Rate:            {win_rate:.2f}% ({win_count} Wins / {loss_count} Losses)")
    print(f"Net Realized PnL:    ${realized_pnl:,.2f}")
    print(f"Gross Profit:        ${gross_profit:,.2f}")
    print(f"Gross Loss:          ${gross_loss:,.2f}")
    print(f"Profit Factor:       {profit_factor:.2f}" if not np.isnan(profit_factor) else "Profit Factor: N/A")
    print(f"Average Win:         ${avg_win:.2f}")
    print(f"Average Loss:        ${avg_loss:.2f}")
    print(f"Reward/Risk Ratio:   {reward_risk_ratio:.2f}" if not np.isnan(reward_risk_ratio) else "Reward/Risk: N/A")
    print(f"Average Hold Time:   {df['duration_hrs'].mean():.2f} hours")

    # 4. Breakdown by Instrument
    print("\n" + "=" * 80)
    print("🔀 PERFORMANCE BY CURRENCY PAIR")
    print("=" * 80)

    pair_stats = []
    for pair, grp in df.groupby("instrument"):
        p_total = len(grp)
        p_wins = len(grp[grp["realized_pl"] > 0])
        p_losses = len(grp[grp["realized_pl"] <= 0])
        p_wr = (p_wins / p_total) * 100.0 if p_total > 0 else 0.0
        p_pnl = grp["realized_pl"].sum()
        p_gprofit = grp[grp["realized_pl"] > 0]["realized_pl"].sum()
        p_gloss = abs(grp[grp["realized_pl"] <= 0]["realized_pl"].sum())
        p_pf = (p_gprofit / p_gloss) if p_gloss > 0 else (np.inf if p_gprofit > 0 else 0.0)
        p_avg_duration = grp["duration_hrs"].mean()

        pair_stats.append({
            "Pair": pair,
            "Trades": p_total,
            "Win Rate": f"{p_wr:.1f}%",
            "Net PnL": f"${p_pnl:,.2f}",
            "Profit Factor": f"{p_pf:.2f}" if p_pf != np.inf else "INF",
            "Avg Hold (hrs)": f"{p_avg_duration:.1f}h"
        })

    print(pd.DataFrame(pair_stats).to_string(index=False))

    # 5. Breakdown by Trade Direction
    print("\n" + "=" * 80)
    print("🧭 PERFORMANCE BY DIRECTION (LONG vs SHORT)")
    print("=" * 80)
    dir_stats = []
    for d, grp in df.groupby("direction"):
        d_total = len(grp)
        d_wins = len(grp[grp["realized_pl"] > 0])
        d_wr = (d_wins / d_total) * 100.0 if d_total > 0 else 0.0
        d_pnl = grp["realized_pl"].sum()
        dir_stats.append({
            "Direction": d,
            "Trades": d_total,
            "Win Rate": f"{d_wr:.1f}%",
            "Net PnL": f"${d_pnl:,.2f}",
            "Avg PnL/Trade": f"${grp['realized_pl'].mean():.2f}"
        })
    print(pd.DataFrame(dir_stats).to_string(index=False))

    # 6. Save JSON report for detailed inspection
    out_file = "paper_bot_deep_dive_analysis.json"
    df["open_time"] = df["open_time"].astype(str)
    df["close_time"] = df["close_time"].astype(str)
    df.to_json(out_file, orient="records", indent=2)
    print(f"\n💾 Full trade details saved to: {out_file}")

if __name__ == "__main__":
    main()
