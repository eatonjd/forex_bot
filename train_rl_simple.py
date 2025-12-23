#!/usr/bin/env python3
"""
Simplified RL Training Script - Handles yfinance MultiIndex

Trains PPO on EUR/USD with proper data handling.
"""

import os
import yfinance as yf
import pandas as pd
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv
from utils.advanced_env import SharpeRewardEnv
from utils.indicators import add_technical_indicators

print("=" * 60)
print("RL TRAINING - PPO for Forex")
print("=" * 60)
print()

# Create directories
os.makedirs("models", exist_ok=True)

# Step 1: Fetch data with proper handling
print("📊 Fetching EUR/USD data...")
raw_data = yf.download("EURUSD=X", period="6mo", interval="1h", progress=False)

# Handle MultiIndex if present
if isinstance(raw_data.columns, pd.MultiIndex):
    raw_data.columns = raw_data.columns.droplevel(1)

# Reset index and clean
train_data = raw_data.reset_index()
print(f"✅ Downloaded {len(train_data)} candles\n")

# Step 2: Add indicators safely
print("📈 Adding technical indicators...")
try:
    train_data = add_technical_indicators(train_data)
    train_data = train_data.dropna()
    print(f"✅ Indicators added: {len(train_data)} candles after cleanup\n")
except Exception as e:
    print(f"⚠️ Error adding indicators: {e}")
    print("Proceeding with basic features only...\n")
    # Use only OHLCV
    train_data = train_data[["Open", "High", "Low", "Close", "Volume"]].copy()

# Step 3: Create environment
print("🎮 Creating environment...")


def make_env():
    return SharpeRewardEnv(
        df=train_data,
        initial_balance=10000,
        transaction_cost=0.001,
        trade_fraction=0.3,
        reward_type="sharpe",
    )


env = DummyVecEnv([make_env])
print("✅ Environment created\n")

# Step 4: Create PPO model
print("🤖 Creating PPO model...")
model = PPO(
    "MlpPolicy", env, learning_rate=0.0003, n_steps=2048, batch_size=64, verbose=1
)
print("✅ Model created\n")

# Step 5: Train
print("=" * 60)
print("🚀 Training for 50,000 timesteps...")
print("   This will take 10-30 minutes")
print("=" * 60)
print()

try:
    model.learn(total_timesteps=50000, progress_bar=True)
    print("\n✅ Training complete!\n")

    # Save
    model.save("models/ppo_forex_simple")
    print("💾 Model saved: models/ppo_forex_simple.zip\n")

    # Quick test
    print("📊 Quick test...")
    obs = env.reset()
    for _ in range(100):
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, done, info = env.step(action)
        if done:
            break

    final_value = info[0]["portfolio_value"]
    ret = (final_value - 10000) / 10000 * 100
    print(f"   Final value: ${final_value:,.2f} ({ret:+.2f}%)\n")

    print("✅ COMPLETE! Model ready at: models/ppo_forex_simple.zip")

except KeyboardInterrupt:
    print("\n⚠️ Training interrupted, saving...")
    model.save("models/ppo_forex_interrupted")
except Exception as e:
    print(f"\n❌ Error: {e}")
    try:
        model.save("models/ppo_forex_error")
        print("Model saved despite error")
    except:
        pass

print("\n🎉 Done!")
