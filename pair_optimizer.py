#!/usr/bin/env python3
"""
Automated Forex Pair Optimizer
Backtests a candidate universe of forex pairs on 60-day M15 candles
and filters pairs using statistical edge gates.
"""

import os
import json
import numpy as np
import pandas as pd
from datetime import datetime
from oandapyV20 import API
from oandapyV20.endpoints.instruments import InstrumentsCandles

CANDIDATE_UNIVERSE = ["USD_JPY", "USD_CAD", "GBP_USD", "EUR_USD", "AUD_USD", "EUR_JPY"]

WIN_RATE_THRESHOLD = 58.0      # Min 58% Win Rate
PROFIT_FACTOR_THRESHOLD = 1.3  # Min 1.3 Profit Factor
MAX_DRAWDOWN_LIMIT = 15.0      # Max 15% Drawdown

def fetch_candles(api, instrument, count=2500):
    """Fetch M15 candles from OANDA."""
    params = {"count": count, "granularity": "M15"}
    r = InstrumentsCandles(instrument=instrument, params=params)
    api.request(r)
    candles = r.response.get("candles", [])
    
    data = []
    for c in candles:
        if c["complete"]:
            data.append({
                "time": c["time"],
                "open": float(c["mid"]["o"]),
                "high": float(c["mid"]["h"]),
                "low": float(c["mid"]["l"]),
                "close": float(c["mid"]["c"])
            })
    return pd.DataFrame(data)

def run_backtest_on_pair(df):
    """Simulate Mean Reversion strategy (Bollinger Bands + RSI)."""
    if len(df) < 50:
        return {"win_rate": 0, "profit_factor": 0, "max_drawdown": 100, "trades": 0, "pnl": 0}
        
    # Indicators
    df['ma'] = df['close'].rolling(20).mean()
    df['std'] = df['close'].rolling(20).std()
    df['upper'] = df['ma'] + (2.0 * df['std'])
    df['lower'] = df['ma'] - (2.0 * df['std'])
    
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-9)
    df['rsi'] = 100 - (100 / (1 + rs))

    trades = []
    position = None
    
    for i in range(20, len(df)):
        price = df['close'].iloc[i]
        rsi = df['rsi'].iloc[i]
        lower = df['lower'].iloc[i]
        upper = df['upper'].iloc[i]
        
        # Long entry
        if position is None and price <= lower and rsi < 32:
            position = {"side": "buy", "entry": price}
        # Short entry
        elif position is None and price >= upper and rsi > 68:
            position = {"side": "sell", "entry": price}
        # Exit Long
        elif position and position["side"] == "buy" and (price >= df['ma'].iloc[i] or rsi > 60):
            pnl = price - position["entry"]
            trades.append(pnl)
            position = None
        # Exit Short
        elif position and position["side"] == "sell" and (price <= df['ma'].iloc[i] or rsi < 40):
            pnl = position["entry"] - price
            trades.append(pnl)
            position = None

    if not trades:
        return {"win_rate": 0, "profit_factor": 0, "max_drawdown": 0, "trades": 0, "pnl": 0}

    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]
    
    win_rate = (len(wins) / len(trades)) * 100.0 if trades else 0.0
    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 1e-9
    profit_factor = gross_profit / gross_loss
    
    cum_pnl = np.cumsum(trades)
    peak = np.maximum.accumulate(cum_pnl)
    drawdown = peak - cum_pnl
    max_dd = np.max(drawdown) if len(drawdown) > 0 else 0.0

    return {
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "max_drawdown": max_dd,
        "trades": len(trades),
        "pnl": sum(trades)
    }

def optimize_portfolio():
    """Run optimization over universe and output selected roster."""
    api_key = os.getenv("OANDA_API_KEY_LIVE") or os.getenv("OANDA_API_KEY")
    env = "live" if os.getenv("OANDA_API_KEY_LIVE") else "practice"
    
    if not api_key:
        print("❌ No API key available for optimization.")
        return {"active_instruments": ["USD_JPY", "USD_CAD"], "results": {}}

    api = API(access_token=api_key, environment=env)
    results = {}
    active_roster = []

    print("🔍 Optimizing Forex Roster across Candidate Universe...", flush=True)
    for pair in CANDIDATE_UNIVERSE:
        try:
            df = fetch_candles(api, pair)
            res = run_backtest_on_pair(df)
            results[pair] = res
            
            # Check Gates
            if (res["win_rate"] >= WIN_RATE_THRESHOLD and 
                res["profit_factor"] >= PROFIT_FACTOR_THRESHOLD):
                active_roster.append(pair)
                print(f"  ✅ [QUALIFIED] {pair}: WR={res['win_rate']:.1f}%, PF={res['profit_factor']:.2f}")
            else:
                print(f"  ❌ [REJECTED]  {pair}: WR={res['win_rate']:.1f}%, PF={res['profit_factor']:.2f}")
        except Exception as e:
            print(f"  ❌ Error optimizing {pair}: {e}")

    # Fallback safety if market filter rejects all
    if not active_roster:
        active_roster = ["USD_JPY", "USD_CAD"]

    output_file = "active_instruments.json"
    data = {
        "timestamp": datetime.utcnow().isoformat(),
        "active_instruments": active_roster,
        "results": results
    }
    
    with open(output_file, "w") as f:
        json.dump(data, f, indent=4)
        
    print(f"📁 Updated Active Portfolio Roster: {active_roster}")
    return data

if __name__ == "__main__":
    optimize_portfolio()
