#!/usr/bin/env python3
"""
Final Model Comparison - All 3 Models

Compares:
1. Random Baseline
2. Conservative Model (Enhanced, 100K, Sharpe reward)
3. Improved Model (100K, 60% Return + 20% Risk + 20% Activity)
"""

import yfinance as yf
import pandas as pd
import numpy as np
from stable_baselines3 import PPO
from utils.feature_engineering import add_all_features
from utils.advanced_env import SharpeRewardEnv

print("=" * 60)
print("FINAL MODEL COMPARISON")
print("=" * 60)
print()

# Fetch test data
print("📊 Fetching test data (2 months EUR/USD)...")
raw = yf.download("EURUSD=X", period="2mo", interval="1h", progress=False)
if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.droplevel(1)

test_data = raw.reset_index()
test_data = add_all_features(test_data)
print(f"✅ Test data: {len(test_data)} candles\n")

# Create environment for models
env = SharpeRewardEnv(df=test_data, initial_balance=10000)


def test_model(name, model_path=None):
    """Test a model or random baseline"""
    print(f"🔄 Testing {name}...")

    if model_path:
        model = PPO.load(model_path)
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

        pv = info["portfolio_value"]
        trades = info["total_trades"]
    else:
        # Random baseline
        capital = 10000
        position = None
        trades = 0

        for i in range(min(len(test_data), 1000)):
            price = test_data["Close"].iloc[i]
            action = np.random.choice([0, 1, 2])

            if action == 1 and position is None:
                position = price
            elif action == 2 and position:
                pips = (price - position) / 0.0001
                capital += pips * 10
                position = None
                trades += 1

        pv = capital
        total_reward = 0

    ret = (pv - 10000) / 10000 * 100
    print(f"   Return: {ret:+.2f}% | Trades: {trades} | Portfolio: ${pv:,.2f}\n")
    return {"return": ret, "trades": trades, "portfolio": pv}


# Test all models
results = {}
results["random"] = test_model("Random Baseline")
results["conservative"] = test_model(
    "Conservative (Enhanced)", "models/ppo_enhanced_final"
)
results["improved"] = test_model("Improved Reward", "models/ppo_improved_final")

# Display results
print("=" * 60)
print("RESULTS SUMMARY")
print("=" * 60)
print()

scenarios = [
    ("Random Baseline", results["random"]),
    ("Conservative (Sharpe)", results["conservative"]),
    ("Improved (Balanced)", results["improved"]),
]

for name, res in scenarios:
    print(
        f"{name:25} {res['return']:+7.2f}%  | {res['trades']:4d} trades | ${res['portfolio']:>10,.2f}"
    )

# Analysis
print("\n" + "=" * 60)
print("ANALYSIS")
print("=" * 60)

baseline_ret = results["random"]["return"]
cons_ret = results["conservative"]["return"]
imp_ret = results["improved"]["return"]

print(
    f"\nConservative vs Random: {((cons_ret - baseline_ret) / abs(baseline_ret) * 100) if baseline_ret != 0 else 0:+.1f}%"
)
print(
    f"Improved vs Random:     {((imp_ret - baseline_ret) / abs(baseline_ret) * 100) if baseline_ret != 0 else 0:+.1f}%"
)
print(
    f"Improved vs Conservative: {((imp_ret - cons_ret) / abs(cons_ret) * 100) if cons_ret != 0 else 0:+.1f}%"
)

print("\n" + "=" * 60)
print("WINNER")
print("=" * 60)

best = max(scenarios, key=lambda x: x[1]["return"])
print(f"\n🏆 Best Performer: {best[0]}")
print(f"   Return: {best[1]['return']:+.2f}%")
print(f"   Trades: {best[1]['trades']}")

# Key insights
print("\n" + "=" * 60)
print("KEY INSIGHTS")
print("=" * 60)
print()

if results["conservative"]["trades"] == 0:
    print("⚠️  Conservative model: Too risk-averse (no trades)")
else:
    print(f"✅ Conservative model: {results['conservative']['trades']} trades")

if results["improved"]["trades"] > 0:
    print(f"✅ Improved model: ACTIVE ({results['improved']['trades']} trades)")
    if results["improved"]["return"] > results["conservative"]["return"]:
        print("   ✅ Better return than conservative!")
else:
    print("⚠️  Improved model: Still too conservative")

print("\n✅ Model comparison complete!")
