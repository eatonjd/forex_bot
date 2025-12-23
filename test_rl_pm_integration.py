#!/usr/bin/env python3
"""
RL + Position Manager Integration Backtest

Tests the improved RL model integrated with Position Manager:
- RL Model: Decides WHEN to enter (1000 active trades)
- Position Manager: Decides HOW to exit (breakeven, trailing, auto-close)

This combines the best of both:
- RL's active trading
- PM's profit protection
"""

import yfinance as yf
import pandas as pd
import numpy as np
from stable_baselines3 import PPO
from utils.feature_engineering import add_all_features
from utils.advanced_env import SharpeRewardEnv
from utils.position_manager import PositionManager

print("=" * 60)
print("RL + POSITION MANAGER INTEGRATION")
print("=" * 60)
print()

# Configuration
INITIAL_CAPITAL = 10000
PIP_SIZE = 0.0001
PIP_VALUE = 10.0

# Fetch test data
print("📊 Fetching test data (2 months EUR/USD)...")
raw = yf.download("EURUSD=X", period="2mo", interval="1h", progress=False)
if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.droplevel(1)

test_data = raw.reset_index()
test_data = add_all_features(test_data)
print(f"✅ Test data: {len(test_data)} candles\n")

# Create environment
env = SharpeRewardEnv(df=test_data, initial_balance=INITIAL_CAPITAL)


def run_backtest(name, model_path=None, use_pm=False, pm_config=None):
    """Run backtest with or without Position Manager"""
    print(f"{'=' * 60}")
    print(f"Testing: {name}")
    print(f"{'=' * 60}")

    # Initialize
    capital = INITIAL_CAPITAL
    position = None
    trades_count = 0
    winning_trades = 0
    pm = None
    current_sl = None

    # Load model
    if model_path:
        model = PPO.load(model_path)
        print(f"✅ Loaded model: {model_path}")
    else:
        model = None
        print(f"📊 Using random baseline")

    # Initialize PM if requested
    if use_pm:
        pm = PositionManager(**(pm_config or {}))
        print(f"✅ Position Manager enabled")
        print(f"   Breakeven: {pm_config.get('breakeven_pips', 20)} pips")
        print(f"   Trailing: {pm_config.get('trailing_start_pips', 30)} pips")

    print()

    # Run backtest
    if model:
        obs = env.reset()[0]

    for i in range(min(len(test_data), 1000)):
        price = test_data["Close"].iloc[i]

        # Get action
        if model:
            action, _ = model.predict(obs, deterministic=True)
            action = int(action)
        else:
            action = np.random.choice([0, 1, 2])

        # Check PM first if we have a position
        if position and pm:
            pips_profit = (price - position["entry"]) / PIP_SIZE
            profit_usd = pips_profit * PIP_VALUE

            pm_result = pm.manage_position(
                position_id=f"pos_{position['id']}",
                symbol="EURUSD",
                direction="BUY",
                entry_price=position["entry"],
                current_price=price,
                current_sl=current_sl,
                current_profit_usd=profit_usd,
            )

            if pm_result["action"] == "modify_sl":
                current_sl = pm_result["new_sl"]
            elif pm_result["action"] == "close":
                # PM says close
                capital += profit_usd
                trades_count += 1
                if profit_usd > 0:
                    winning_trades += 1
                position = None
                current_sl = None
                pm.remove_position(f"pos_{position['id'] if position else 0}")
                continue

        # Check SL hit
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

        # Execute RL action
        if action == 1 and position is None:  # BUY
            position = {"entry": price, "id": i}
            current_sl = price - (30 * PIP_SIZE)  # Initial 30-pip SL

            if pm:
                # Register with PM
                pm_result = pm.manage_position(
                    position_id=f"pos_{i}",
                    symbol="EURUSD",
                    direction="BUY",
                    entry_price=price,
                    current_price=price,
                    current_sl=current_sl,
                    current_profit_usd=0,
                )

        elif action == 2 and position:  # SELL
            pips = (price - position["entry"]) / PIP_SIZE
            capital += pips * PIP_VALUE
            trades_count += 1
            if pips > 0:
                winning_trades += 1
            position = None
            current_sl = None
            if pm:
                pm.remove_position(f"pos_{position['id'] if position else 0}")

        # Step environment
        if model:
            obs, _, done, _, _ = env.step(action)
            if done:
                obs = env.reset()[0]

    # Close any remaining position
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
    print(f"   Portfolio: ${capital:,.2f}\n")

    return {
        "return": ret,
        "trades": trades_count,
        "win_rate": win_rate,
        "portfolio": capital,
    }


# Run tests
pm_config = {
    "enable_breakeven": True,
    "breakeven_pips": 20.0,
    "breakeven_offset": 5.0,
    "enable_trailing": True,
    "trailing_start_pips": 30.0,
    "trailing_step_pips": 10.0,
    "trailing_distance_pips": 15.0,
    "enable_auto_close": False,
}

results = {}
results["random"] = run_backtest("Random Baseline")
results["rl_only"] = run_backtest("RL Model Only", "models/ppo_improved_final")
results["rl_pm"] = run_backtest(
    "RL Model + Position Manager",
    "models/ppo_improved_final",
    use_pm=True,
    pm_config=pm_config,
)

# Final comparison
print("=" * 60)
print("FINAL RESULTS")
print("=" * 60)
print()

scenarios = [
    ("Random Baseline", results["random"]),
    ("RL Only", results["rl_only"]),
    ("RL + PM (INTEGRATED)", results["rl_pm"]),
]

for name, res in scenarios:
    print(
        f"{name:30} {res['return']:+7.2f}%  | {res['trades']:4d} trades | {res['win_rate']:5.1f}% WR | ${res['portfolio']:>10,.2f}"
    )

# Analysis
print("\n" + "=" * 60)
print("IMPROVEMENT ANALYSIS")
print("=" * 60)

rl_ret = results["rl_only"]["return"]
pm_ret = results["rl_pm"]["return"]

if rl_ret != 0:
    improvement = ((pm_ret - rl_ret) / abs(rl_ret)) * 100
    print(f"\nPosition Manager Impact: {improvement:+.1f}% improvement")
else:
    improvement = pm_ret

print(f"RL Only:  {rl_ret:+.2f}% ({results['rl_only']['win_rate']:.1f}% WR)")
print(f"RL + PM:  {pm_ret:+.2f}% ({results['rl_pm']['win_rate']:.1f}% WR)")

if pm_ret > rl_ret:
    print("\n✅ Position Manager IMPROVES performance!")
    print(f"   Extra return: {pm_ret - rl_ret:+.2f}%")
    print(
        f"   Win rate boost: {results['rl_pm']['win_rate'] - results['rl_only']['win_rate']:+.1f}%"
    )
else:
    print("\n⚠️  Position Manager didn't help this time")

print("\n" + "=" * 60)
print("✅ Integration test complete!")
print("=" * 60)
