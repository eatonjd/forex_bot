#!/usr/bin/env python3
"""
RL Agent Training Script - PPO with Sharpe Reward

Trains a PPO agent for forex trading with:
- SharpeRewardEnv for risk-adjusted rewards
- EUR/USD hourly data
- Position Manager integration ready

Author: Forex Bot Team
Created: 2025-12-19
"""

import os
import yfinance as yf
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv
from stable_baselines3.common.callbacks import EvalCallback, CheckpointCallback
from utils.advanced_env import SharpeRewardEnv
from utils.indicators import add_technical_indicators
import matplotlib.pyplot as plt
import numpy as np

print("=" * 60)
print("RL AGENT TRAINING - PPO with Sharpe Reward")
print("=" * 60)
print()

# Configuration
SYMBOL = "EURUSD=X"
TRAIN_PERIOD = "6mo"  # 6 months for training
EVAL_PERIOD = "2mo"  # 2 months for evaluation
INTERVAL = "1h"
TOTAL_TIMESTEPS = 50000  # Quick training for demo
MODEL_NAME = "ppo_forex_sharpe"

# Create directories
os.makedirs("models", exist_ok=True)
os.makedirs("logs", exist_ok=True)

# Step 1: Fetch and prepare data
print("📊 Step 1: Fetching EUR/USD data...")
print(f"   Symbol: {SYMBOL}")
print(f"   Training: {TRAIN_PERIOD}, Eval: {EVAL_PERIOD}, Interval: {INTERVAL}\n")

# Training data
train_data = yf.download(SYMBOL, period=TRAIN_PERIOD, interval=INTERVAL, progress=False)
train_data = train_data.reset_index()
train_data = add_technical_indicators(train_data)
train_data = train_data.dropna()
print(f"✅ Training data: {len(train_data)} candles")

# Evaluation data
eval_data = yf.download(SYMBOL, period=EVAL_PERIOD, interval=INTERVAL, progress=False)
eval_data = eval_data.reset_index()
eval_data = add_technical_indicators(eval_data)
eval_data = eval_data.dropna()
print(f"✅ Evaluation data: {len(eval_data)} candles\n")

# Step 2: Create environments
print("🎮 Step 2: Creating training environment...")
train_env = SharpeRewardEnv(
    df=train_data,
    initial_balance=10000,
    transaction_cost=0.001,
    trade_fraction=0.3,
    reward_type="sharpe",  # Risk-adjusted rewards
    use_realistic_execution=True,
)

# Wrap in DummyVecEnv for SB3
train_env = DummyVecEnv(
    [
        lambda: SharpeRewardEnv(
            df=train_data,
            initial_balance=10000,
            transaction_cost=0.001,
            trade_fraction=0.3,
            reward_type="sharpe",
            use_realistic_execution=True,
        )
    ]
)

# Evaluation environment
eval_env = DummyVecEnv(
    [
        lambda: SharpeRewardEnv(
            df=eval_data,
            initial_balance=10000,
            transaction_cost=0.001,
            trade_fraction=0.3,
            reward_type="sharpe",
            use_realistic_execution=True,
        )
    ]
)

print("✅ Environments created\n")

# Step 3: Create PPO agent
print("🤖 Step 3: Creating PPO agent...")
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
    verbose=1,
    tensorboard_log="./logs/",
)
print("✅ PPO agent created\n")

# Step 4: Setup callbacks
print("📋 Step 4: Setting up callbacks...")

# Evaluation callback
eval_callback = EvalCallback(
    eval_env,
    best_model_save_path=f"./models/best_{MODEL_NAME}",
    log_path="./logs/",
    eval_freq=5000,
    n_eval_episodes=5,
    deterministic=True,
    render=False,
)

# Checkpoint callback
checkpoint_callback = CheckpointCallback(
    save_freq=10000,
    save_path=f"./models/checkpoints_{MODEL_NAME}",
    name_prefix=MODEL_NAME,
)

print("✅ Callbacks configured\n")

# Step 5: Train!
print("=" * 60)
print(f"🚀 Step 5: Training PPO for {TOTAL_TIMESTEPS:,} timesteps...")
print("   This may take 10-30 minutes depending on hardware")
print("=" * 60)
print()

try:
    model.learn(
        total_timesteps=TOTAL_TIMESTEPS,
        callback=[eval_callback, checkpoint_callback],
        progress_bar=True,
    )

    print("\n✅ Training complete!\n")

    # Step 6: Save final model
    print("💾 Step 6: Saving model...")
    model.save(f"models/{MODEL_NAME}_final")
    print(f"✅ Model saved to: models/{MODEL_NAME}_final.zip\n")

    # Step 7: Quick evaluation
    print("=" * 60)
    print("📊 Step 7: Quick evaluation on test data")
    print("=" * 60)

    obs = eval_env.reset()
    total_reward = 0
    steps = 0
    done = False

    while not done and steps < len(eval_data):
        action, _states = model.predict(obs, deterministic=True)
        obs, reward, done, info = eval_env.step(action)
        total_reward += reward
        steps += 1

    final_value = info[0]["portfolio_value"]
    initial_value = 10000
    total_return = (final_value - initial_value) / initial_value * 100

    print(f"\n📈 Evaluation Results:")
    print(f"   Steps: {steps}")
    print(f"   Total Reward: {total_reward[0]:.2f}")
    print(f"   Initial Balance: ${initial_value:,.2f}")
    print(f"   Final Balance: ${final_value:,.2f}")
    print(f"   Total Return: {total_return:+.2f}%")
    print(f"   Total Trades: {info[0]['total_trades']}")

    print("\n" + "=" * 60)
    print("✅ TRAINING COMPLETE!")
    print("=" * 60)
    print(f"\nModel saved at: models/{MODEL_NAME}_final.zip")
    print("\nNext steps:")
    print("1. Run backtest with RL agent: python backtest_rl.py")
    print("2. Integrate with Position Manager")
    print("3. Compare: Baseline vs RL vs RL+PM")

except KeyboardInterrupt:
    print("\n\n⚠️ Training interrupted by user")
    print("Saving current model...")
    model.save(f"models/{MODEL_NAME}_interrupted")
    print(f"Model saved to: models/{MODEL_NAME}_interrupted.zip")

except Exception as e:
    print(f"\n❌ Error during training: {e}")
    import traceback

    traceback.print_exc()
    print("\nAttempting to save model...")
    try:
        model.save(f"models/{MODEL_NAME}_error")
        print(f"Model saved to: models/{MODEL_NAME}_error.zip")
    except:
        print("Could not save model")

print("\n🎉 Script complete!")
