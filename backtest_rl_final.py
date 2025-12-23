#!/usr/bin/env python3
"""
Final RL Model Comparison Backtest

Compares 4 scenarios:
1. Random Baseline
2. RL Minimal (30K timesteps)
3. RL Enhanced (100K timesteps)
4. RL Enhanced + Position Manager

Author: Forex Bot Team
Created: 2025-12-19
"""

import yfinance as yf
import pandas as pd
import numpy as np
from stable_baselines3 import PPO
from utils.rl_trading_agent import RLTradingAgent
from utils.advanced_env import SharpeRewardEnv

print("=" * 60)
print("FINAL RL MODEL COMPARISON")
print("=" * 60)
print()

# Configuration
INITIAL_CAPITAL = 10000
PIP_SIZE = 0.0001
PIP_VALUE = 10.0

# Fetch test data
print("📊 Fetching test data (EUR/USD, 2 months)...")
raw = yf.download("EURUSD=X", period="2mo", interval="1h", progress=False)
if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.droplevel(1)

test_data = raw.reset_index().copy()
test_data = test_data[["Open", "High", "Low", "Close", "Volume"]].copy()

# Add features (matching enhanced training)
test_data["returns"] = test_data["Close"].pct_change()
for period in [10, 20, 50]:
    test_data[f"sma_{period}"] = test_data["Close"].rolling(period).mean()
test_data = test_data.dropna()

print(f"✅ Test data: {len(test_data)} candles\n")

# Create environment
env = SharpeRewardEnv(
    df=test_data,
    initial_balance=INITIAL_CAPITAL,
    transaction_cost=0.001,
    trade_fraction=0.3,
)


def run_scenario(name, model_path=None, use_pm=False):
    """Run a backtest scenario"""
    print(f"🔄 Running {name}...")

    capital = INITIAL_CAPITAL
    position = None
    trades_count = 0

    # Load model if provided
    if model_path:
        if use_pm:
            agent = RLTradingAgent(model_path, use_position_manager=True)
            model = agent.model
        else:
            model = PPO.load(model_path)
            agent = None
    else:
        model = None
        agent = None

    obs = env.reset()[0]

    for i in range(len(test_data)):
        price = test_data["Close"].iloc[i]

        # Get action
        if model is None:
            # Random baseline
            action = np.random.choice([0, 1, 2])
        elif use_pm:
            # RL with PM
            action = agent.predict(obs, price, deterministic=True)
        else:
            # RL only
            action, _ = model.predict(obs, deterministic=True)
            action = int(action)

        # Execute action
        if action == 1 and position is None:  # BUY
            position = {"entry": price, "type": "BUY"}
            if use_pm and agent:
                agent.open_position(
                    f"pos_{i}", "EURUSD", "BUY", price, price - 30 * PIP_SIZE
                )
        elif action == 2 and position:  # SELL
            pips = (price - position["entry"]) / PIP_SIZE
            capital += pips * PIP_VALUE
            position = None
            trades_count += 1

        # Step environment
        obs, _, done, _, _ = env.step(action)
        if done:
            obs = env.reset()[0]

    ret = (capital - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    print(
        f"   Return: {ret:+.2f}% | Trades: {trades_count} | Capital: ${capital:,.2f}\n"
    )
    return {"return": ret, "capital": capital, "trades": trades_count}


# Run all scenarios
results = {}
results["random"] = run_scenario("Random Baseline")
results["minimal"] = run_scenario("RL Minimal (30K)", "models/ppo_forex_minimal")
results["enhanced"] = run_scenario("RL Enhanced (100K)", "models/ppo_enhanced_final")
results["enhanced_pm"] = run_scenario(
    "RL Enhanced + PM", "models/ppo_enhanced_final", use_pm=True
)

# Display results
print("=" * 60)
print("RESULTS SUMMARY")
print("=" * 60)
print()

scenarios = [
    ("Random Baseline", results["random"]),
    ("RL Minimal (30K)", results["minimal"]),
    ("RL Enhanced (100K)", results["enhanced"]),
    ("RL Enhanced + PM", results["enhanced_pm"]),
]

for name, res in scenarios:
    print(
        f"{name:25} {res['return']:+7.2f}%  | {res['trades']:3d} trades | ${res['capital']:>10,.2f}"
    )

# Improvements
print("\n" + "=" * 60)
print("IMPROVEMENTS")
print("=" * 60)
baseline = results["random"]["return"]

if baseline != 0:
    for name in ["minimal", "enhanced", "enhanced_pm"]:
        improvement = ((results[name]["return"] - baseline) / abs(baseline)) * 100
        print(f"\n{name.replace('_', ' ').title():20} {improvement:+.1f}% vs baseline")

print("\n" + "=" * 60)
print("KEY FINDINGS")
print("=" * 60)
print(f"\nEnhanced (100K) vs Minimal (30K):")
if results["minimal"]["return"] != 0:
    enh_vs_min = (
        (results["enhanced"]["return"] - results["minimal"]["return"])
        / abs(results["minimal"]["return"])
    ) * 100
    print(f"  {enh_vs_min:+.1f}% improvement from more training")

print(f"\nEnhanced+PM vs Enhanced:")
if results["enhanced"]["return"] != 0:
    pm_impact = (
        (results["enhanced_pm"]["return"] - results["enhanced"]["return"])
        / abs(results["enhanced"]["return"])
    ) * 100
    print(f"  {pm_impact:+.1f}% improvement from Position Manager")

print("\n✅ Comparison complete!")
