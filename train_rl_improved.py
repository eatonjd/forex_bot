#!/usr/bin/env python3
"""
RL Training with IMPROVED Reward Function

Changes from previous:
1. 60% Simple Return + 20% Sharpe + 20% Activity Bonus
2. Penalizes excessive holding (encourages trading)
3. Rewards profitable trades more
4. Less conservative overall

Expected: More active trading with acceptable risk

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
import gymnasium as gym
from gymnasium import spaces
from utils.feature_engineering import add_all_features

print("=" * 60)
print("RL TRAINING - Improved Reward Function")
print("=" * 60)
print()

os.makedirs("models", exist_ok=True)
os.makedirs("logs", exist_ok=True)


# =============================================================================
# IMPROVED REWARD ENVIRONMENT
# =============================================================================


class ImprovedRewardEnv(gym.Env):
    """
    Trading environment with BALANCED reward function.

    Reward = 60% Simple Return + 20% Risk-Adjusted + 20% Activity

    This encourages trading while maintaining risk awareness.
    """

    metadata = {"render_modes": ["human"]}

    def __init__(self, df: pd.DataFrame, initial_balance: float = 10000):
        super().__init__()

        self.df = df.reset_index(drop=True)
        self.initial_balance = initial_balance

        # Feature columns
        self.ohlcv_cols = ["Open", "High", "Low", "Close", "Volume"]
        self.feature_cols = [c for c in df.columns if c not in self.ohlcv_cols]

        # Spaces
        n_features = len(self.feature_cols) + 4  # features + account info
        self.action_space = spaces.Discrete(3)  # Hold, Buy, Sell
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(n_features,), dtype=np.float32
        )

        self.reset()

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)

        self.current_step = 0
        self.balance = self.initial_balance
        self.shares_held = 0
        self.avg_entry_price = 0
        self.total_trades = 0
        self.recent_actions = []  # Track recent activity

        self.portfolio_values = [self.initial_balance]
        self.returns = []
        self.max_portfolio_value = self.initial_balance

        return self._get_observation(), {}

    def _get_current_price(self):
        return float(self.df.iloc[self.current_step]["Close"])

    def _get_portfolio_value(self):
        price = self._get_current_price()
        return self.balance + (self.shares_held * price)

    def _get_observation(self):
        if self.current_step < len(self.df):
            features = self.df.iloc[self.current_step][self.feature_cols].values.astype(
                np.float32
            )
        else:
            features = np.zeros(len(self.feature_cols), dtype=np.float32)

        price = self._get_current_price()
        pv = self._get_portfolio_value()

        account_features = np.array(
            [
                self.balance / self.initial_balance,
                (self.shares_held * price) / self.initial_balance,
                pv / self.initial_balance,
                (price - self.avg_entry_price) / self.avg_entry_price
                if self.avg_entry_price > 0
                else 0,
            ],
            dtype=np.float32,
        )

        return np.concatenate([features, account_features])

    def _calculate_reward(self, prev_value, curr_value, action):
        """
        IMPROVED REWARD: 60% Returns + 20% Risk-Adjusted + 20% Activity
        """
        # 1. Simple return (60% weight)
        simple_return = (curr_value - prev_value) / prev_value if prev_value > 0 else 0
        return_component = simple_return * 60

        # 2. Risk-adjusted component (20% weight)
        self.returns.append(simple_return)
        recent_returns = self.returns[-20:]

        if len(recent_returns) > 2:
            mean_ret = np.mean(recent_returns)
            std_ret = np.std(recent_returns) + 1e-8
            sharpe = mean_ret / std_ret
            risk_component = sharpe * 20
        else:
            risk_component = 0

        # 3. Activity bonus (20% weight)
        # Encourages trading vs always holding
        self.recent_actions.append(action)
        if len(self.recent_actions) > 10:
            self.recent_actions = self.recent_actions[-10:]

        # Reward variety in actions (not just holding)
        unique_actions = len(set(self.recent_actions))
        activity_bonus = (unique_actions / 3.0) * 20  # Max when using all 3 actions

        # 4. Trade bonus (small reward for completing trades)
        trade_bonus = 5 if action in [1, 2] and self.shares_held > 0 else 0

        total_reward = return_component + risk_component + activity_bonus + trade_bonus

        return total_reward

    def step(self, action: int):
        prev_value = self._get_portfolio_value()

        # Execute action
        if action == 1:  # Buy
            if self.balance > 0:
                price = self._get_current_price()
                amount = self.balance * 0.3
                shares = amount / price
                cost = amount * 1.001  # 0.1% fee

                if cost <= self.balance:
                    self.balance -= cost

                    if self.shares_held > 0:
                        self.avg_entry_price = (
                            (self.shares_held * self.avg_entry_price) + (shares * price)
                        ) / (self.shares_held + shares)
                    else:
                        self.avg_entry_price = price

                    self.shares_held += shares
                    self.total_trades += 1

        elif action == 2:  # Sell
            if self.shares_held > 0:
                price = self._get_current_price()
                shares = self.shares_held * 0.3
                proceeds = shares * price * 0.999  # 0.1% fee

                self.balance += proceeds
                self.shares_held -= shares
                self.total_trades += 1

                if self.shares_held < 0.0001:
                    self.shares_held = 0
                    self.avg_entry_price = 0

        # Move forward
        self.current_step += 1

        # Calculate reward
        curr_value = self._get_portfolio_value()
        self.portfolio_values.append(curr_value)
        self.max_portfolio_value = max(self.max_portfolio_value, curr_value)

        reward = self._calculate_reward(prev_value, curr_value, action)

        done = self.current_step >= len(self.df) - 1
        truncated = False

        info = {
            "portfolio_value": curr_value,
            "balance": self.balance,
            "shares": self.shares_held,
            "total_trades": self.total_trades,
        }

        return self._get_observation(), reward, done, truncated, info


# =============================================================================
# TRAINING
# =============================================================================

print("📊 Fetching EUR/USD data...")
train_raw = yf.download("EURUSD=X", period="9mo", interval="1h", progress=False)
eval_raw = yf.download("EURUSD=X", period="3mo", interval="1h", progress=False)

# Fix MultiIndex
for raw in [train_raw, eval_raw]:
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.droplevel(1)

train_df = train_raw.reset_index()
eval_df = eval_raw.reset_index()

print("📈 Adding features...")
train_df = add_all_features(train_df)
eval_df = add_all_features(eval_df)

print(f"✅ Training: {len(train_df)} candles")
print(f"✅ Evaluation: {len(eval_df)} candles\n")

# Create environments
print("🎯 Creating environments with IMPROVED reward...")
print("   60% Simple Return + 20% Risk-Adjusted + 20% Activity\n")


def make_train_env():
    return ImprovedRewardEnv(df=train_df)


def make_eval_env():
    return ImprovedRewardEnv(df=eval_df)


train_env = DummyVecEnv([make_train_env])
eval_env = DummyVecEnv([make_eval_env])

# Create model
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
    ent_coef=0.01,  # Increased for more exploration
    verbose=1,
)
print("✅ Model created\n")

# Callbacks
eval_callback = EvalCallback(
    eval_env,
    best_model_save_path="./models/best_ppo_improved",
    log_path="./logs/",
    eval_freq=10000,
    n_eval_episodes=5,
    deterministic=True,
)

checkpoint_callback = CheckpointCallback(
    save_freq=20000,
    save_path="./models/checkpoints_improved",
    name_prefix="ppo_improved",
)

# Train
print("=" * 60)
print("🚀 TRAINING FOR 100,000 TIMESTEPS")
print("   Expected: ~5 minutes")
print("   Reward: 60% Return + 20% Risk + 20% Activity")
print("=" * 60)
print()

try:
    model.learn(
        total_timesteps=100000,
        callback=[eval_callback, checkpoint_callback],
        progress_bar=True,
    )

    print("\n✅ TRAINING COMPLETE!\n")

    model.save("models/ppo_improved_final")
    print("💾 Saved: models/ppo_improved_final.zip\n")

    # Quick eval
    print("📊 Quick evaluation...")
    obs = eval_env.reset()
    total_reward = 0
    steps = 0

    while steps < 1000:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, done, info = eval_env.step(action)
        total_reward += reward[0]
        steps += 1
        if done[0]:
            break

    pv = info[0]["portfolio_value"]
    ret = (pv - 10000) / 10000 * 100

    print(f"   Steps: {steps}")
    print(f"   Total Reward: {total_reward:.2f}")
    print(f"   Portfolio: ${pv:,.2f} ({ret:+.2f}%)")
    print(f"   Trades: {info[0]['total_trades']}")

    print("\n" + "=" * 60)
    print("✅ SUCCESS! Improved model ready!")
    print("=" * 60)
    print("\nModel: models/ppo_improved_final.zip")
    print("Best: models/best_ppo_improved/best_model.zip")

except KeyboardInterrupt:
    print("\n⚠️ Interrupted")
    model.save("models/ppo_improved_interrupted")
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback

    traceback.print_exc()

print("\n🎉 Done!")
