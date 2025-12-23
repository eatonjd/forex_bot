#!/usr/bin/env python3
"""
Simple Enhanced Model Test

Tests the enhanced RL model performance.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from stable_baselines3 import PPO
from utils.advanced_env import SharpeRewardEnv

print("=" * 60)
print("ENHANCED RL MODEL TEST")
print("=" * 60)
print()

# Fetch data
print("📊 Fetching test data...")
raw = yf.download("EURUSD=X", period="2mo", interval="1h", progress=False)
if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.droplevel(1)

test_data = raw.reset_index().copy()


# Add features (same as training)
def add_features(df):
    df["returns"] = df["Close"].pct_change()
    for period in [10, 20, 50]:
        df[f"sma_{period}"] = df["Close"].rolling(period).mean()
        df[f"ema_{period}"] = df["Close"].ewm(span=period, adjust=False).mean()
    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df["rsi"] = 100 - (100 / (1 + gain / (loss + 1e-10)))
    df["volatility_20"] = df["returns"].rolling(20).std()
    return df.dropna()


test_data = add_features(test_data)
print(f"✅ Test data: {len(test_data)} candles\n")

# Create environment
env = SharpeRewardEnv(df=test_data, initial_balance=10000)

# Test enhanced model
print("🤖 Testing Enhanced Model (100K timesteps)...")
model = PPO.load("models/ppo_enhanced_final")

obs = env.reset()[0]
total_reward = 0
steps = 0

while steps < len(test_data) and steps < 1000:
    action, _ = model.predict(obs, deterministic=True)
    obs, reward, done, _, info = env.step(action)
    total_reward += reward
    steps += 1
    if done:
        break

final_pv = info["portfolio_value"]
ret = (final_pv - 10000) / 10000 * 100

print(f"\n📊 Results:")
print(f"   Steps: {steps}")
print(f"   Total Reward: {total_reward:.2f}")
print(f"   Final Portfolio: ${final_pv:,.2f}")
print(f"   Return: {ret:+.2f}%")
print(f"   Trades: {info['total_trades']}")

print("\n" + "=" * 60)
if ret > 0:
    print("✅ Enhanced model shows POSITIVE returns!")
elif ret == 0:
    print("⚠️  Enhanced model is conservative (not trading)")
else:
    print("❌ Enhanced model shows negative returns")
print("=" * 60)

print("\n✅ Test complete!")
print("\nNOTE: This model is trained for 100K timesteps on 9 months")
print("of data with 26 indicators. Performance depends on market conditions.")
