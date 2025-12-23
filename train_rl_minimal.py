#!/usr/bin/env python3
"""
Minimal RL Training - Get it working first!

Uses only OHLCV data to train PPO quickly.
Can add indicators later once training works.
"""

import os
import yfinance as yf
import pandas as pd
import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv
from utils.advanced_env import SharpeRewardEnv

print("=" * 60)
print("MINIMAL RL TRAINING - PPO for Forex")
print("=" * 60)
print()

os.makedirs("models", exist_ok=True)

# Step 1: Get data
print("📊 Fetching EUR/USD...")
raw = yf.download("EURUSD=X", period="3mo", interval="1h", progress=False)

# Fix MultiIndex
if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.droplevel(1)

df = raw.reset_index().copy()

# Just keep OHLCV
df = df[["Open", "High", "Low", "Close", "Volume"]].copy()

# Add minimal features manually
df["returns"] = df["Close"].pct_change()
df["volume_ma"] = df["Volume"].rolling(20).mean()
df["close_ma"] = df["Close"].rolling(20).mean()
df = df.dropna()

print(f"✅ Data ready: {len(df)} candles\n")

# Step 2: Create env
print("🎮 Creating environment...")


def make_env():
    return SharpeRewardEnv(
        df=df,
        initial_balance=10000,
        transaction_cost=0.001,
        trade_fraction=0.3,
        reward_type="sharpe",
    )


env = DummyVecEnv([make_env])
print("✅ Environment ready\n")

# Step 3: Create model
print("🤖 Creating PPO...")
model = PPO(
    "MlpPolicy", env, learning_rate=0.0003, n_steps=2048, batch_size=64, verbose=1
)
print("✅ Model ready\n")

# Step 4: Train!
print("=" * 60)
print("🚀 Training for 30,000 timesteps (10-15 min)...")
print("=" * 60)
print()

try:
    model.learn(total_timesteps=30000, progress_bar=True)
    print("\n✅ Training complete!\n")

    # Save
    model.save("models/ppo_forex_minimal")
    print("💾 Saved: models/ppo_forex_minimal.zip\n")

    # Quick eval
    print("📊 Quick evaluation...")
    obs = env.reset()
    total_reward = 0
    done = False
    steps = 0

    while not done and steps < 500:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, done, info = env.step(action)
        total_reward += reward[0]
        steps += 1

    pv = info[0]["portfolio_value"]
    ret = (pv - 10000) / 10000 * 100

    print(f"   Steps: {steps}")
    print(f"   Total Reward: {total_reward:.2f}")
    print(f"   Portfolio: ${pv:,.2f} ({ret:+.2f}%)")
    print(f"   Trades: {info[0]['total_trades']}")

    print("\n" + "=" * 60)
    print("✅ SUCCESS! Model trained and saved!")
    print("=" * 60)
    print(f"\nModel: models/ppo_forex_minimal.zip")
    print("\nNext: Create backtestRL script to test it!")

except KeyboardInterrupt:
    print("\n⚠️ Interrupted")
    model.save("models/ppo_forex_interrupted")
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback

    traceback.print_exc()

print("\n🎉 Done!")
