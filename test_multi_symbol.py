#!/usr/bin/env python3
"""
Multi-Symbol RL + PM Integration Test

Tests the improved RL model + Position Manager across multiple forex pairs:
- EUR/USD (trained on this)
- GBP/USD
- USD/JPY
- AUD/USD
- USD/CHF

This validates model generalization and robustness.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from stable_baselines3 import PPO
from utils.feature_engineering import add_all_features
from utils.advanced_env import SharpeRewardEnv
from utils.position_manager import PositionManager

print("=" * 60)
print("MULTI-SYMBOL RL + PM INTEGRATION TEST")
print("=" * 60)
print()

# Configuration
SYMBOLS = {
    "EURUSD=X": "EUR/USD (Trained)",
    "GBPUSD=X": "GBP/USD",
    "USDJPY=X": "USD/JPY",
    "AUDUSD=X": "AUD/USD",
    "USDCHF=X": "USD/CHF",
}

INITIAL_CAPITAL = 10000
PIP_SIZE = 0.0001
PIP_VALUE = 10.0

PM_CONFIG = {
    "enable_breakeven": True,
    "breakeven_pips": 20.0,
    "breakeven_offset": 5.0,
    "enable_trailing": True,
    "trailing_start_pips": 30.0,
    "trailing_step_pips": 10.0,
    "trailing_distance_pips": 15.0,
    "enable_auto_close": False,
}


def test_symbol(symbol, symbol_name):
    """Test RL+PM on a single symbol"""
    print(f"\n{'=' * 60}")
    print(f"Testing: {symbol_name}")
    print(f"{'=' * 60}")

    try:
        # Fetch data
        print(f"📊 Fetching {symbol} data...")
        raw = yf.download(symbol, period="2mo", interval="1h", progress=False)

        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.droplevel(1)

        if len(raw) == 0:
            print(f"❌ No data available for {symbol}")
            return None

        test_data = raw.reset_index()
        test_data = add_all_features(test_data)

        if len(test_data) < 100:
            print(f"❌ Insufficient data ({len(test_data)} candles)")
            return None

        print(f"✅ Data ready: {len(test_data)} candles")

        # Create environment
        env = SharpeRewardEnv(df=test_data, initial_balance=INITIAL_CAPITAL)

        # Load model
        model = PPO.load("models/ppo_improved_final")

        # Initialize PM
        pm = PositionManager(**PM_CONFIG)

        # Run backtest
        capital = INITIAL_CAPITAL
        position = None
        trades_count = 0
        winning_trades = 0
        current_sl = None

        obs = env.reset()[0]

        for i in range(min(len(test_data), 1000)):
            price = test_data["Close"].iloc[i]

            # Get RL action
            action, _ = model.predict(obs, deterministic=True)
            action = int(action)

            # Check PM
            if position and pm:
                pips_profit = (price - position["entry"]) / PIP_SIZE
                profit_usd = pips_profit * PIP_VALUE

                pm_result = pm.manage_position(
                    position_id=f"pos_{position['id']}",
                    symbol=symbol,
                    direction="BUY",
                    entry_price=position["entry"],
                    current_price=price,
                    current_sl=current_sl,
                    current_profit_usd=profit_usd,
                )

                if pm_result["action"] == "modify_sl":
                    current_sl = pm_result["new_sl"]
                elif pm_result["action"] == "close":
                    capital += profit_usd
                    trades_count += 1
                    if profit_usd > 0:
                        winning_trades += 1
                    position = None
                    current_sl = None
                    pm.remove_position(f"pos_{position['id'] if position else 0}")
                    obs, _, done, _, _ = env.step(2)  # Exit action
                    if done:
                        obs = env.reset()[0]
                    continue

            # Check SL
            if position and current_sl and price <= current_sl:
                pips = (current_sl - position["entry"]) / PIP_SIZE
                capital += pips * PIP_VALUE
                trades_count += 1
                if pips > 0:
                    winning_trades += 1
                position = None
                current_sl = None
                if pm:
                    pm.remove_position(f"pos_{position['id'] if position else 0}")

            # Execute action
            if action == 1 and position is None:
                position = {"entry": price, "id": i}
                current_sl = price - (30 * PIP_SIZE)
            elif action == 2 and position:
                pips = (price - position["entry"]) / PIP_SIZE
                capital += pips * PIP_VALUE
                trades_count += 1
                if pips > 0:
                    winning_trades += 1
                position = None
                current_sl = None
                if pm:
                    pm.remove_position(f"pos_{position['id'] if position else 0}")

            # Step
            obs, _, done, _, _ = env.step(action)
            if done:
                obs = env.reset()[0]

        # Close remaining
        if position:
            pips = (test_data["Close"].iloc[-1] - position["entry"]) / PIP_SIZE
            capital += pips * PIP_VALUE
            trades_count += 1
            if pips > 0:
                winning_trades += 1

        ret = (capital - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
        win_rate = (winning_trades / trades_count * 100) if trades_count > 0 else 0

        print(f"\n📊 Results:")
        print(f"   Return: {ret:+.2f}%")
        print(f"   Trades: {trades_count}")
        print(f"   Win Rate: {win_rate:.1f}%")
        print(f"   Portfolio: ${capital:,.2f}")

        return {
            "symbol": symbol_name,
            "return": ret,
            "trades": trades_count,
            "win_rate": win_rate,
            "portfolio": capital,
            "candles": len(test_data),
        }

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return None


# Test all symbols
print("Testing RL + Position Manager across multiple forex pairs...")
print()

results = []
for symbol, name in SYMBOLS.items():
    result = test_symbol(symbol, name)
    if result:
        results.append(result)

# Summary
print("\n" + "=" * 60)
print("MULTI-SYMBOL RESULTS SUMMARY")
print("=" * 60)
print()

print(f"{'Symbol':<25} {'Return':>10} {'Trades':>8} {'Win Rate':>10} {'Portfolio':>12}")
print("-" * 60)

for res in results:
    print(
        f"{res['symbol']:<25} {res['return']:>+9.2f}% {res['trades']:>8d} {res['win_rate']:>9.1f}% ${res['portfolio']:>10,.2f}"
    )

# Statistics
if results:
    returns = [r["return"] for r in results]
    win_rates = [r["win_rate"] for r in results]

    print("\n" + "=" * 60)
    print("AGGREGATE STATISTICS")
    print("=" * 60)
    print(f"\nAverage Return: {np.mean(returns):+.2f}%")
    print(f"Median Return:  {np.median(returns):+.2f}%")
    print(
        f"Best Return:    {max(returns):+.2f}% ({results[returns.index(max(returns))]['symbol']})"
    )
    print(
        f"Worst Return:   {min(returns):+.2f}% ({results[returns.index(min(returns))]['symbol']})"
    )

    print(f"\nAverage Win Rate: {np.mean(win_rates):.1f}%")
    print(f"Median Win Rate:  {np.median(win_rates):.1f}%")

    positive = sum(1 for r in returns if r > 0)
    print(
        f"\nPositive Returns: {positive}/{len(results)} ({positive / len(results) * 100:.1f}%)"
    )

    print("\n" + "=" * 60)
    print("GENERALIZATION ASSESSMENT")
    print("=" * 60)

    if np.mean(returns) > 5:
        print("\n✅ EXCELLENT - Model generalizes very well!")
        print("   Average return > 5%")
    elif np.mean(returns) > 0:
        print("\n✅ GOOD - Model shows positive generalization")
        print(f"   Average return: {np.mean(returns):+.2f}%")
    else:
        print("\n⚠️  CAUTION - Mixed results across symbols")
        print("   May need symbol-specific training")

    if positive / len(results) >= 0.6:
        print(f"✅ ROBUST - {positive / len(results) * 100:.0f}% profitable symbols")
    else:
        print(f"⚠️  VARIABLE - Only {positive / len(results) * 100:.0f}% profitable")

print("\n" + "=" * 60)
print("✅ Multi-symbol test complete!")
print("=" * 60)
