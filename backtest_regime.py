#!/usr/bin/env python3
"""
Regime Bot Historical Backtester - Risk-Based Sizing

Validates the multi-regime strategy (Bollinger Bands + RSI Mean Reversion,
Donchian Breakout, and Range Trading) across USD_JPY, GBP_USD, and USD_CAD
using 1.5% account balance risk per trade.

Author: Antigravity AI
Date: 2026-07-20
"""

import sys
import os
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

# Ensure path imports work
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from utils.mean_reversion import MeanReversionStrategy
from utils.volatility_breakout import VolatilityBreakoutStrategy
from utils.range_trading import RangeTradingStrategy
from utils.regime_detector import RegimeDetector

# Pair configurations matched to usdjpy_regime_bot.py
PAIR_CONFIGS = {
    "USD_JPY": {
        "ticker": "USDJPY=X",
        "pip_size": 0.01,
        "max_spread": 2.5,
        "sl_pips": 30.0,
        "tp_pips": 60.0,
        "trailing_trigger": 25.0,
    },
    "GBP_USD": {
        "ticker": "GBPUSD=X",
        "pip_size": 0.0001,
        "max_spread": 2.5,
        "sl_pips": 35.0,
        "tp_pips": 70.0,
        "trailing_trigger": 30.0,
    },
    "USD_CAD": {
        "ticker": "USDCAD=X",
        "pip_size": 0.0001,
        "max_spread": 2.5,
        "sl_pips": 30.0,
        "tp_pips": 60.0,
        "trailing_trigger": 25.0,
    }
}

def calculate_position_size(symbol: str, sl_pips: float, balance: float, price: float) -> int:
    risk_amount = balance * 0.015  # 1.5% risk
    cfg = PAIR_CONFIGS[symbol]
    pip_size = cfg["pip_size"]
    
    if symbol in ["USD_JPY", "USD_CAD"]:
        pip_value_per_unit = pip_size / price
    else:
        pip_value_per_unit = pip_size
        
    size = int(risk_amount / (sl_pips * pip_value_per_unit))
    
    # Margin limit cap (max 20% margin utilization at 1:20 leverage / 5% margin rate)
    margin_rate = 0.05
    unit_price_usd = 1.0
    if symbol in ["GBP_USD", "USD_CAD"]:
        unit_price_usd = price
        
    max_margin = balance * 0.20
    max_units = int(max_margin / (margin_rate * unit_price_usd))
    size = min(size, max_units)
    
    return max(1000, min(size, 100000))

def calc_pnl_usd(symbol: str, pips: float, units: int, price: float) -> float:
    cfg = PAIR_CONFIGS[symbol]
    pip_size = cfg["pip_size"]
    if symbol in ["USD_JPY", "USD_CAD"]:
        # Quote currency is not USD -> divide by conversion rate to get USD
        return pips * (pip_size / price) * units
    else:
        # Quote currency is USD -> direct conversion
        return pips * pip_size * units

class RegimeBacktester:
    def __init__(self, initial_balance=5000.0):
        self.initial_balance = initial_balance
        self.mr_strategy = MeanReversionStrategy()
        self.vol_strategy = VolatilityBreakoutStrategy()
        self.range_strategy = RangeTradingStrategy()
        
    def run_backtest(self, symbol: str, df: pd.DataFrame) -> pd.DataFrame:
        cfg = PAIR_CONFIGS[symbol]
        pip_size = cfg["pip_size"]
        sl_pips = cfg["sl_pips"]
        tp_pips = cfg["tp_pips"]
        trailing_trigger_pips = cfg["trailing_trigger"]
        
        regime_detector = RegimeDetector()
        
        balance = self.initial_balance
        position = None  # None or Dict
        trades = []
        equity = []
        
        for i in range(50, len(df)):
            sub_df = df.iloc[:i+1]
            current_close = df.iloc[i]["Close"]
            current_high = df.iloc[i]["High"]
            current_low = df.iloc[i]["Low"]
            
            # Update equity
            current_equity = balance
            if position:
                pips = (current_close - position["entry_price"]) / pip_size * position["dir"]
                current_equity += calc_pnl_usd(symbol, pips, position["units"], current_close)
            equity.append({"idx": i, "equity": current_equity})
            
            # --- Manage Existing Position ---
            if position:
                # Check Time Stop (48 hourly candles = 2 days)
                hold_candles = i - position["entry_idx"]
                if hold_candles >= 48:
                    pips = (current_close - position["entry_price"]) / pip_size * position["dir"]
                    pnl = calc_pnl_usd(symbol, pips, position["units"], current_close)
                    balance += pnl
                    trades.append({
                        "entry_time": df.index[position["entry_idx"]],
                        "exit_time": df.index[i],
                        "dir": "LONG" if position["dir"] == 1 else "SHORT",
                        "entry_price": position["entry_price"],
                        "exit_price": current_close,
                        "pips": pips,
                        "pnl": pnl,
                        "exit_reason": "TIME_STOP",
                        "regime": position["entry_regime"]
                    })
                    position = None
                    continue
                
                # Trailing logic
                current_pips = (current_close - position["entry_price"]) / pip_size * position["dir"]
                if current_pips >= trailing_trigger_pips and not position["trailing_active"]:
                    position["trailing_active"] = True
                    position["peak_pips"] = current_pips
                
                if position["trailing_active"]:
                    if current_pips > position["peak_pips"]:
                        position["peak_pips"] = current_pips
                    # Giveback threshold (15% of peak profit, min 5, max 15 pips)
                    giveback = max(5.0, min(15.0, position["peak_pips"] * 0.15))
                    if current_pips <= position["peak_pips"] - giveback:
                        pips = (current_close - position["entry_price"]) / pip_size * position["dir"]
                        pnl = calc_pnl_usd(symbol, pips, position["units"], current_close)
                        balance += pnl
                        trades.append({
                            "entry_time": df.index[position["entry_idx"]],
                            "exit_time": df.index[i],
                            "dir": "LONG" if position["dir"] == 1 else "SHORT",
                            "entry_price": position["entry_price"],
                            "exit_price": current_close,
                            "pips": pips,
                            "pnl": pnl,
                            "exit_reason": "TRAILING_STOP",
                            "regime": position["entry_regime"]
                        })
                        position = None
                        continue
                
                # Check fixed TP/SL
                if position["dir"] == 1:
                    if current_low <= position["sl"]:
                        pnl = calc_pnl_usd(symbol, -sl_pips, position["units"], position["sl"])
                        balance += pnl
                        trades.append({
                            "entry_time": df.index[position["entry_idx"]],
                            "exit_time": df.index[i],
                            "dir": "LONG",
                            "entry_price": position["entry_price"],
                            "exit_price": position["sl"],
                            "pips": -sl_pips,
                            "pnl": pnl,
                            "exit_reason": "STOP_LOSS",
                            "regime": position["entry_regime"]
                        })
                        position = None
                    elif current_high >= position["tp"]:
                        pnl = calc_pnl_usd(symbol, tp_pips, position["units"], position["tp"])
                        balance += pnl
                        trades.append({
                            "entry_time": df.index[position["entry_idx"]],
                            "exit_time": df.index[i],
                            "dir": "LONG",
                            "entry_price": position["entry_price"],
                            "exit_price": position["tp"],
                            "pips": tp_pips,
                            "pnl": pnl,
                            "exit_reason": "TAKE_PROFIT",
                            "regime": position["entry_regime"]
                        })
                        position = None
                else:  # SHORT
                    if current_high >= position["sl"]:
                        pnl = calc_pnl_usd(symbol, -sl_pips, position["units"], position["sl"])
                        balance += pnl
                        trades.append({
                            "entry_time": df.index[position["entry_idx"]],
                            "exit_time": df.index[i],
                            "dir": "SHORT",
                            "entry_price": position["entry_price"],
                            "exit_price": position["sl"],
                            "pips": -sl_pips,
                            "pnl": pnl,
                            "exit_reason": "STOP_LOSS",
                            "regime": position["entry_regime"]
                        })
                        position = None
                    elif current_low <= position["tp"]:
                        pnl = calc_pnl_usd(symbol, tp_pips, position["units"], position["tp"])
                        balance += pnl
                        trades.append({
                            "entry_time": df.index[position["entry_idx"]],
                            "exit_time": df.index[i],
                            "dir": "SHORT",
                            "entry_price": position["entry_price"],
                            "exit_price": position["tp"],
                            "pips": tp_pips,
                            "pnl": pnl,
                            "exit_reason": "TAKE_PROFIT",
                            "regime": position["entry_regime"]
                        })
                        position = None
                continue
                
            # --- Entry Logic ---
            regime_state = regime_detector.detect(sub_df)
            active_regime = regime_state.regime
            
            if active_regime == "TRANSITIONAL" or not regime_state.confirmed:
                continue
                
            signal = "HOLD"
            entry_regime = active_regime
            
            if active_regime == "MEAN_REVERSION":
                sig_data = self.mr_strategy.get_signal(sub_df, i)
                signal = sig_data["signal"]
                
                sma_dir = regime_state.sma_direction
                if signal == "BUY" and sma_dir == "BEARISH":
                    signal = "HOLD"
                elif signal == "SELL" and sma_dir == "BULLISH":
                    signal = "HOLD"
                
                if signal == "HOLD":
                    sig_data_range = self.range_strategy.get_signal(sub_df, i, pip_size)
                    if sig_data_range["signal"] != "HOLD":
                        signal = sig_data_range["signal"]
                        entry_regime = "RANGE"
            else:  # BREAKOUT
                sig_data = self.vol_strategy.get_signal(sub_df, i)
                signal = sig_data["signal"]
                
            if signal != "HOLD":
                direction = 1 if signal == "BUY" else -1
                sl = current_close - (sl_pips * pip_size * direction)
                tp = current_close + (tp_pips * pip_size * direction)
                
                units = calculate_position_size(symbol, sl_pips, balance, current_close)
                
                position = {
                    "dir": direction,
                    "entry_price": current_close,
                    "entry_idx": i,
                    "sl": sl,
                    "tp": tp,
                    "units": units,
                    "trailing_active": False,
                    "peak_pips": 0.0,
                    "entry_regime": entry_regime
                }
                
        return pd.DataFrame(trades), pd.DataFrame(equity)

def main():
    print("=" * 60)
    print("📈 REGIME TRADING BOT HISTORICAL BACKTEST - RISK-BASED SIZING")
    print("=" * 60)
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)
    
    backtester = RegimeBacktester()
    all_summary = []
    
    for symbol, cfg in PAIR_CONFIGS.items():
        print(f"\n📥 Fetching {symbol} ({cfg['ticker']}) historical hourly candles...")
        df = yf.download(cfg["ticker"], start=start_date, end=end_date, interval="1h", progress=False)
        if df.empty:
            print(f"❌ Failed to fetch data for {symbol}")
            continue
            
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        print(f"✅ Loaded {len(df)} candles. Running backtest...")
        trades, equity = backtester.run_backtest(symbol, df)
        
        if trades.empty:
            print(f"⚠️ No trades executed for {symbol}")
            continue
            
        total_trades = len(trades)
        wins = len(trades[trades["pnl"] > 0])
        win_rate = (wins / total_trades) * 100
        total_pnl = trades["pnl"].sum()
        max_drawdown = 0.0
        
        if not equity.empty:
            peak = equity["equity"].cummax()
            drawdown = (equity["equity"] - peak) / peak * 100
            max_drawdown = abs(drawdown.min())
            
        print(f"📊 {symbol} Backtest Results:")
        print(f"   * Total Trades: {total_trades}")
        print(f"   * Win Rate: {win_rate:.1f}%")
        print(f"   * Net Profit/Loss: ${total_pnl:+.2f}")
        print(f"   * Max Drawdown: {max_drawdown:.2f}%")
        
        all_summary.append({
            "Symbol": symbol,
            "Trades": total_trades,
            "Win Rate": f"{win_rate:.1f}%",
            "P/L": f"${total_pnl:+.2f}",
            "Max Drawdown": f"{max_drawdown:.2f}%"
        })
        
    print("\n" + "=" * 60)
    print("📋 SUMMARY REPORT")
    print("=" * 60)
    summary_df = pd.DataFrame(all_summary)
    print(summary_df.to_string(index=False))
    print("=" * 60)

if __name__ == "__main__":
    main()
