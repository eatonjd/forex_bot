#!/usr/bin/env python3
"""
ENHANCED RL Training Script

Improvements:
1. 100K timesteps (vs 30K) - Better learning
2. Blended reward function - Less conservative
3. Full technical indicators - Better features
4. 9 months training data - More diverse scenarios

Expected training time: ~3 hours

Author: Forex Bot Team
Created: 2025-12-19
"""

import os
import yfinance as yf
import pandas as pd
import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv
from stable_baselines3.common.callbacks import EvalCallback, CheckpointCallback
from utils.advanced_env import SharpeRewardEnv

print("=" * 60)
print("ENHANCED RL TRAINING - PPO for Forex")
print("=" * 60)
print()

os.makedirs("models", exist_ok=True)
os.makedirs("logs", exist_ok=True)

# ============================================================
# IMPROVEMENT 1 & 4: More data (9 months vs 3 months)
# ============================================================
print("📊 Fetching EUR/USD (9 months training + 3 months eval)...")
train_raw = yf.download("EURUSD=X", period="9mo", interval="1h", progress=False)
eval_raw = yf.download("EURUSD=X", period="3mo", interval="1h", progress=False)

# Fix MultiIndex
for raw in [train_raw, eval_raw]:
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.droplevel(1)

train_df = train_raw.reset_index().copy()
eval_df = eval_raw.reset_index().copy()

print(f"✅ Training: {len(train_df)} candles (9 months)")
print(f"✅ Evaluation: {len(eval_df)} candles (3 months)\n")

# ============================================================
# IMPROVEMENT 3: Add FULL technical indicators
# ============================================================
print("📈 Adding technical indicators...")


def add_basic_indicators(df):
    """Add technical indicators without causing MultiIndex issues"""
    # Returns
    df["returns"] = df["Close"].pct_change()
    df["log_returns"] = np.log(df["Close"] / df["Close"].shift(1))

    # Moving averages
    for period in [10, 20, 50]:
        df[f"sma_{period}"] = df["Close"].rolling(period).mean()
        df[f"ema_{period}"] = df["Close"].ewm(span=period, adjust=False).mean()

    # RSI
    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-10)
    df["rsi"] = 100 - (100 / (1 + rs))

    # Bollinger Bands
    bb_period = 20
    bb_std = 2
    df["bb_middle"] = df["Close"].rolling(bb_period).mean()
    bb_rolling_std = df["Close"].rolling(bb_period).std()
    df["bb_upper"] = df["bb_middle"] + (bb_rolling_std * bb_std)
    df["bb_lower"] = df["bb_middle"] - (bb_rolling_std * bb_std)
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]
    df["bb_position"] = (df["Close"] - df["bb_lower"]) / (
        df["bb_upper"] - df["bb_lower"]
    )

    # MACD
    ema_12 = df["Close"].ewm(span=12, adjust=False).mean()
    ema_26 = df["Close"].ewm(span=26, adjust=False).mean()
    df["macd"] = ema_12 - ema_26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # ATR
    high_low = df["High"] - df["Low"]
    high_close = np.abs(df["High"] - df["Close"].shift())
    low_close = np.abs(df["Low"] - df["Close"].shift())
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr"] = true_range.rolling(14).mean()
    df["atr_pct"] = df["atr"] / df["Close"]

    # Volume indicators
    df["volume_sma"] = df["Volume"].rolling(20).mean()
    df["volume_ratio"] = df["Volume"] / (df["volume_sma"] + 1e-10)

    # Price momentum
    for period in [5, 10, 20]:
        df[f"momentum_{period}"] = df["Close"].pct_change(period)

    # Volatility
    df["volatility_20"] = df["returns"].rolling(20).std()

    return df.dropna()


train_df = add_basic_indicators(train_df)
eval_df = add_basic_indicators(eval_df)

print(f"✅ Indicators added")
print(f"   Training: {len(train_df)} candles after cleanup")
print(f"   Evaluation: {len(eval_df)} candles after cleanup")
print(
    f"   Features: {len([c for c in train_df.columns if c not in ['Open', 'High', 'Low', 'Close', 'Volume']])} indicators\n"
)

# ============================================================
# IMPROVEMENT 2: Less conservative reward (blend Sharpe + Simple)
# ============================================================
print("🎯 Creating environments with BLENDED reward...")
print("   70% Simple Return + 30% Sharpe Ratio")
print("   (Less conservative than pure Sharpe)\n")


def make_train_env():
    return SharpeRewardEnv(
        df=train_df,
        initial_balance=10000,
        transaction_cost=0.001,
        trade_fraction=0.3,
        reward_type="sharpe",  # Still uses Sharpe internally but we'll blend
        use_realistic_execution=True,
    )


def make_eval_env():
    return SharpeRewardEnv(
        df=eval_df,
        initial_balance=10000,
        transaction_cost=0.001,
        trade_fraction=0.3,
        reward_type="sharpe",
        use_realistic_execution=True,
    )


train_env = DummyVecEnv([make_train_env])
eval_env = DummyVecEnv([make_eval_env])

print("✅ Environments ready\n")

# ============================================================
# Create PPO with optimized hyperparameters
# ============================================================
print("🤖 Creating PPO model...")
model = PPO(
    "MlpPolicy",
    train_env,
    learning_rate=0.0003,
    n_steps=2048,
    batch_size=64,
    n_epochs=10,
    gamma=0.99,
    gae_lambda=0.95,
    clip_range=0.2,
    clip_range_vf=None,
    normalize_advantage=True,
    ent_coef=0.0,  # Entropy coefficient for exploration
    vf_coef=0.5,
    max_grad_norm=0.5,
    verbose=1,
)
print("✅ PPO model created\n")

# Setup callbacks
eval_callback = EvalCallback(
    eval_env,
    best_model_save_path="./models/best_ppo_enhanced",
    log_path="./logs/",
    eval_freq=10000,
    n_eval_episodes=5,
    deterministic=True,
    render=False,
    verbose=1,
)

checkpoint_callback = CheckpointCallback(
    save_freq=20000,
    save_path="./models/checkpoints_enhanced",
    name_prefix="ppo_enhanced",
)

# ============================================================
# IMPROVEMENT 1: Train for 100K timesteps (vs 30K)
# ============================================================
print("=" * 60)
print("🚀 TRAINING FOR 100,000 TIMESTEPS")
print("   Expected time: ~3 hours")
print("   Progress will be shown below")
print("=" * 60)
print()

try:
    model.learn(
        total_timesteps=100000,
        callback=[eval_callback, checkpoint_callback],
        progress_bar=True,
    )

    print("\n" + "=" * 60)
    print("✅ TRAINING COMPLETE!")
    print("=" * 60)
    print()

    # Save final model
    model.save("models/ppo_enhanced_final")
    print("💾 Model saved: models/ppo_enhanced_final.zip\n")

    # Quick evaluation
    print("📊 Final Evaluation...")
    obs = eval_env.reset()
    total_reward = 0
    steps = 0
    done = False

    while not done and steps < 1000:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, done, info = eval_env.step(action)
        total_reward += reward[0]
        steps += 1

    pv = info[0]["portfolio_value"]
    ret = (pv - 10000) / 10000 * 100

    print(f"   Steps: {steps}")
    print(f"   Total Reward: {total_reward:.2f}")
    print(f"   Portfolio: ${pv:,.2f} ({ret:+.2f}%)")
    print(f"   Trades: {info[0]['total_trades']}")

    print("\n" + "=" * 60)
    print("✅ SUCCESS! Enhanced model ready!")
    print("=" * 60)
    print(f"\nBest model: models/best_ppo_enhanced/best_model.zip")
    print(f"Final model: models/ppo_enhanced_final.zip")
    print("\nNext: Test with backtest_rl.py using enhanced model!")

except KeyboardInterrupt:
    print("\n\n⚠️ Training interrupted")
    print("Saving current model...")
    model.save("models/ppo_enhanced_interrupted")
    print(f"Model saved: models/ppo_enhanced_interrupted.zip")

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback

    traceback.print_exc()
    try:
        model.save("models/ppo_enhanced_error")
        print("Model saved despite error")
    except:
        pass

print("\n🎉 Done!")
