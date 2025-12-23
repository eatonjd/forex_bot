#!/usr/bin/env python3
"""
Enhanced Model Test with Correct Features

Tests enhanced RL model with proper feature pipeline.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from stable_baselines3 import PPO
from utils.advanced_env import SharpeRewardEnv
from utils.feature_engineering import add_all_features

print("=" * 60)
print("ENHANCED MODEL TEST - With Correct Features")
print("=" * 60)
print()

# Fetch test data
print("📊 Fetching test data (2 months EUR/USD)...")
raw = yf.download("EURUSD=X", period="2mo", interval="1h", progress=False)

if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.droplevel(1)

test_data = raw.reset_index()

# Add ALL features (matching training)
print("📈 Adding features (matching training pipeline)...")
test_data = add_all_features(test_data)

feature_cols = [
    c for c in test_data.columns if c not in ["Open", "High", "Low", "Close", "Volume"]
]
print(f"✅ Features added: {len(feature_cols)} indicators")
print(f"   Test data: {len(test_data)} candles\n")

# Create environment
env = SharpeRewardEnv(
    df=test_data, initial_balance=10000, transaction_cost=0.001, trade_fraction=0.3
)

print(f"🔍 Environment observation shape: {env.observation_space.shape}")
print()

# Run scenarios
scenarios = []

# 1. Random Baseline
print("🎲 Running Random Baseline...")
capital_random = 10000
position_random = None
trades_random = 0

for i in range(min(len(test_data), 1000)):
    price = test_data["Close"].iloc[i]
    action = np.random.choice([0, 1, 2])

    if action == 1 and position_random is None:
        position_random = price
    elif action == 2 and position_random:
        pips = (price - position_random) / 0.0001
        capital_random += pips * 10
        position_random = None
        trades_random += 1

ret_random = (capital_random - 10000) / 10000 * 100
print(f"   Return: {ret_random:+.2f}% | Trades: {trades_random}\n")
scenarios.append(("Random Baseline", ret_random, trades_random, capital_random))

# 2. Enhanced Model
print("🤖 Testing Enhanced Model (100K timesteps)...")
try:
    model = PPO.load("models/ppo_enhanced_final")

    obs = env.reset()[0]
    total_reward = 0
    steps = 0

    while steps < min(len(test_data), 1000):
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, done, _, info = env.step(action)
        total_reward += reward
        steps += 1
        if done:
            break

    final_pv = info["portfolio_value"]
    ret_enhanced = (final_pv - 10000) / 10000 * 100
    trades_enhanced = info["total_trades"]

    print(f"   Steps: {steps}")
    print(f"   Total Reward: {total_reward:.2f}")
    print(f"   Return: {ret_enhanced:+.2f}%")
    print(f"   Trades: {trades_enhanced}\n")

    scenarios.append(("RL Enhanced (100K)", ret_enhanced, trades_enhanced, final_pv))

except Exception as e:
    print(f"   ❌ Error: {e}\n")
    scenarios.append(("RL Enhanced (100K)", 0, 0, 10000))

# Results
print("=" * 60)
print("RESULTS")
print("=" * 60)
print()

for name, ret, trades, capital in scenarios:
    print(f"{name:25} {ret:+7.2f}%  | {trades:3d} trades | ${capital:>10,.2f}")

# Analysis
if len(scenarios) > 1:
    print("\n" + "=" * 60)
    print("ANALYSIS")
    print("=" * 60)

    baseline_ret = scenarios[0][1]
    enhanced_ret = scenarios[1][1]

    if baseline_ret != 0:
        improvement = ((enhanced_ret - baseline_ret) / abs(baseline_ret)) * 100
        print(f"\nEnhanced vs Baseline: {improvement:+.1f}% improvement")

    if enhanced_ret > 0:
        print("\n✅ Enhanced model shows POSITIVE returns!")
    elif enhanced_ret == 0:
        print("\n⚠️  Enhanced model is conservative (not trading)")
    else:
        print("\n❌ Enhanced model shows negative returns")

print("\n" + "=" * 60)
print("✅ Test complete!")
print("=" * 60)
