#!/usr/bin/env python3
"""
Advanced Trading Environment with Sharpe Ratio Reward.

Improvements over base environment:
1. Risk-adjusted reward (Sharpe ratio based)
2. Multi-symbol support
3. Longer lookback support
4. Better position sizing rewards
"""

import numpy as np
import pandas as pd
from typing import Optional, Dict, List, Tuple
import gymnasium as gym
from gymnasium import spaces


class SharpeRewardEnv(gym.Env):
    """
    Trading environment with Sharpe ratio-based reward.

    Instead of simple P&L, rewards consider:
    - Risk-adjusted returns
    - Volatility penalty
    - Drawdown penalty
    - Transaction cost drag
    """

    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        df: pd.DataFrame,
        initial_balance: float = 10000,
        transaction_cost: float = 0.001,
        trade_fraction: float = 0.3,
        reward_type: str = "sharpe",  # "sharpe", "sortino", "calmar", "simple"
        lookback_window: int = 20,  # For rolling metrics
        render_mode: Optional[str] = None,
        # Realistic execution parameters
        execution_delay: int = 1,  # Execute at next candle's Open (avoids look-ahead)
        slippage_factor: float = 0.5,  # ATR multiplier for slippage
        use_realistic_execution: bool = True,  # Enable/disable for comparison
    ):
        super().__init__()

        self.df = df.reset_index(drop=True)
        self.initial_balance = initial_balance
        self.transaction_cost = transaction_cost
        self.trade_fraction = trade_fraction
        self.reward_type = reward_type
        self.lookback_window = lookback_window
        self.render_mode = render_mode

        # Execution realism
        self.execution_delay = execution_delay
        self.slippage_factor = slippage_factor
        self.use_realistic_execution = use_realistic_execution

        # Feature columns (everything except OHLCV)
        self.ohlcv_cols = ["Open", "High", "Low", "Close", "Volume"]
        exclude = self.ohlcv_cols + [
            "Datetime",
            "Date",
            "Adj Close",
            "Dividends",
            "Stock Splits",
            "Capital Gains",
        ]
        self.feature_cols = [col for col in self.df.columns if col not in exclude]

        # Observation size
        self.n_features = len(self.feature_cols)
        self.n_account_features = 4
        obs_size = self.n_features + self.n_account_features

        # Spaces
        self.action_space = spaces.Discrete(3)  # Hold, Buy, Sell
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(obs_size,), dtype=np.float32
        )

        self.reset()

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)

        self.current_step = 0
        self.balance = self.initial_balance
        self.shares_held = 0
        self.avg_entry_price = 0
        self.total_trades = 0

        # For Sharpe calculation
        self.portfolio_values = [self.initial_balance]
        self.returns = []
        self.max_portfolio_value = self.initial_balance

        return self._get_observation(), {}

    def _get_current_price(self) -> float:
        if self.current_step < len(self.df):
            return float(self.df.iloc[self.current_step]["Close"])
        return float(self.df.iloc[-1]["Close"])

    def _get_portfolio_value(self) -> float:
        price = self._get_current_price()
        return self.balance + (self.shares_held * price)

    def _get_observation(self) -> np.ndarray:
        if self.current_step < len(self.df):
            features = self.df.iloc[self.current_step][self.feature_cols].values.astype(
                np.float32
            )
        else:
            features = np.zeros(self.n_features, dtype=np.float32)

        price = self._get_current_price()
        portfolio_value = self._get_portfolio_value()

        # Normalized account features
        account_features = np.array(
            [
                self.balance / self.initial_balance,
                (self.shares_held * price) / self.initial_balance,
                portfolio_value / self.initial_balance,
                (price - self.avg_entry_price) / self.avg_entry_price
                if self.avg_entry_price > 0
                else 0,
            ],
            dtype=np.float32,
        )

        return np.concatenate([features, account_features])

    def _calculate_reward(
        self, prev_value: float, curr_value: float, action: int
    ) -> float:
        """
        Calculate risk-adjusted reward.
        """
        # Simple return
        simple_return = (curr_value - prev_value) / prev_value if prev_value > 0 else 0
        self.returns.append(simple_return)

        # Keep only recent returns for rolling metrics
        recent_returns = self.returns[-self.lookback_window :]

        if self.reward_type == "simple":
            return simple_return * 100  # Scale for learning

        elif self.reward_type == "sharpe":
            # Sharpe-inspired reward
            if len(recent_returns) < 2:
                return simple_return * 100

            mean_return = np.mean(recent_returns)
            std_return = np.std(recent_returns) + 1e-8  # Avoid division by zero
            sharpe = mean_return / std_return

            # Blend with immediate return for responsiveness
            reward = 0.7 * simple_return * 100 + 0.3 * sharpe * 10
            return reward

        elif self.reward_type == "sortino":
            # Sortino - only penalize downside volatility
            if len(recent_returns) < 2:
                return simple_return * 100

            mean_return = np.mean(recent_returns)
            downside_returns = [r for r in recent_returns if r < 0]
            downside_std = np.std(downside_returns) if downside_returns else 1e-8
            sortino = mean_return / (downside_std + 1e-8)

            reward = 0.7 * simple_return * 100 + 0.3 * sortino * 10
            return reward

        elif self.reward_type == "calmar":
            # Calmar - penalize drawdowns
            curr_drawdown = (
                self.max_portfolio_value - curr_value
            ) / self.max_portfolio_value
            drawdown_penalty = -curr_drawdown * 50 if curr_drawdown > 0.05 else 0

            return simple_return * 100 + drawdown_penalty

        return simple_return * 100

    def _get_execution_price(self, is_buy: bool) -> float:
        """
        Get realistic execution price with:
        1. Next-open execution (avoids look-ahead bias)
        2. ATR-based slippage (volatility-dependent)
        """
        if not self.use_realistic_execution:
            return self._get_current_price()

        # Get execution candle (next open vs current close)
        exec_step = min(self.current_step + self.execution_delay, len(self.df) - 1)

        if self.execution_delay > 0 and exec_step < len(self.df):
            # Execute at next candle's Open
            base_price = float(self.df.iloc[exec_step]["Open"])
        else:
            # Fallback to current Close
            base_price = self._get_current_price()

        # Apply ATR-based slippage
        slippage = 0.0
        if self.slippage_factor > 0 and "atr_norm" in self.df.columns:
            atr_norm = float(self.df.iloc[self.current_step].get("atr_norm", 0))
            # Random slippage between 0 and (atr_norm * factor)
            slippage = atr_norm * self.slippage_factor * np.random.uniform(0, 1)

        if is_buy:
            # Buyers pay more (slippage hurts)
            return base_price * (1 + slippage)
        else:
            # Sellers receive less (slippage hurts)
            return base_price * (1 - slippage)

    def step(self, action: int):
        prev_value = self._get_portfolio_value()

        # Execute action
        if action == 1:  # Buy
            if self.balance > 0:
                exec_price = self._get_execution_price(is_buy=True)
                amount_to_invest = self.balance * self.trade_fraction
                shares_to_buy = amount_to_invest / exec_price
                cost = amount_to_invest * (1 + self.transaction_cost)

                if cost <= self.balance:
                    self.balance -= cost

                    # Update average entry price
                    if self.shares_held > 0:
                        total_cost = (self.shares_held * self.avg_entry_price) + (
                            shares_to_buy * exec_price
                        )
                        self.avg_entry_price = total_cost / (
                            self.shares_held + shares_to_buy
                        )
                    else:
                        self.avg_entry_price = exec_price

                    self.shares_held += shares_to_buy
                    self.total_trades += 1

        elif action == 2:  # Sell
            if self.shares_held > 0:
                exec_price = self._get_execution_price(is_buy=False)
                shares_to_sell = self.shares_held * self.trade_fraction
                proceeds = shares_to_sell * exec_price * (1 - self.transaction_cost)

                self.balance += proceeds
                self.shares_held -= shares_to_sell
                self.total_trades += 1

                if self.shares_held < 0.0001:
                    self.shares_held = 0
                    self.avg_entry_price = 0

        # Move to next step
        self.current_step += 1

        # Calculate reward
        curr_value = self._get_portfolio_value()
        self.portfolio_values.append(curr_value)
        self.max_portfolio_value = max(self.max_portfolio_value, curr_value)

        reward = self._calculate_reward(prev_value, curr_value, action)

        # Check if done
        done = self.current_step >= len(self.df) - 1
        truncated = False

        info = {
            "portfolio_value": curr_value,
            "balance": self.balance,
            "shares": self.shares_held,
            "total_trades": self.total_trades,
        }

        return self._get_observation(), reward, done, truncated, info


class MultiSymbolEnv(gym.Env):
    """
    Train on multiple symbols simultaneously for better generalization.

    Randomly samples from different symbols during training to learn
    patterns that work across markets.
    """

    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        symbol_dfs: Dict[str, pd.DataFrame],  # {symbol: dataframe}
        initial_balance: float = 10000,
        transaction_cost: float = 0.001,
        trade_fraction: float = 0.3,
        reward_type: str = "sharpe",
        render_mode: Optional[str] = None,
    ):
        super().__init__()

        self.symbol_dfs = symbol_dfs
        self.symbols = list(symbol_dfs.keys())
        self.initial_balance = initial_balance
        self.transaction_cost = transaction_cost
        self.trade_fraction = trade_fraction
        self.reward_type = reward_type
        self.render_mode = render_mode

        # Use first symbol as reference for observation space
        ref_df = list(symbol_dfs.values())[0]
        self.ohlcv_cols = ["Open", "High", "Low", "Close", "Volume"]
        exclude = self.ohlcv_cols + [
            "Datetime",
            "Date",
            "Adj Close",
            "Dividends",
            "Stock Splits",
        ]
        self.feature_cols = [col for col in ref_df.columns if col not in exclude]

        self.n_features = len(self.feature_cols)
        self.n_account_features = 4
        obs_size = self.n_features + self.n_account_features

        self.action_space = spaces.Discrete(3)
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(obs_size,), dtype=np.float32
        )

        # Current environment
        self.current_symbol = None
        self.current_env = None

        self.reset()

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)

        # Randomly select a symbol
        self.current_symbol = np.random.choice(self.symbols)

        # Create environment for that symbol
        self.current_env = SharpeRewardEnv(
            df=self.symbol_dfs[self.current_symbol],
            initial_balance=self.initial_balance,
            transaction_cost=self.transaction_cost,
            trade_fraction=self.trade_fraction,
            reward_type=self.reward_type,
        )

        obs, info = self.current_env.reset(seed=seed)
        info["symbol"] = self.current_symbol

        return obs, info

    def step(self, action):
        obs, reward, done, truncated, info = self.current_env.step(action)
        info["symbol"] = self.current_symbol
        return obs, reward, done, truncated, info


def create_sharpe_env(df: pd.DataFrame, reward_type: str = "sharpe", **kwargs):
    """Factory function for creating Sharpe reward environment."""
    return SharpeRewardEnv(df, reward_type=reward_type, **kwargs)


def create_multi_symbol_env(
    symbols: List[str],
    start_date: str = "2014-01-01",
    end_date: str = None,
    reward_type: str = "sharpe",
    **kwargs,
) -> MultiSymbolEnv:
    """
    Create multi-symbol training environment.

    Args:
        symbols: List of stock symbols to train on
        start_date: Training data start date
        end_date: Training data end date
        reward_type: Type of reward function

    Returns:
        MultiSymbolEnv ready for training
    """
    import yfinance as yf
    from utils.indicators import add_technical_indicators

    symbol_dfs = {}

    for symbol in symbols:
        print(f"📥 Downloading {symbol}...")
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_date, end=end_date)

        if len(df) > 100:  # Minimum data requirement
            # Reset index and add indicators
            df = df.reset_index()
            df = df.rename(columns={"index": "Datetime"})
            if "Datetime" not in df.columns and "Date" in df.columns:
                df = df.rename(columns={"Date": "Datetime"})

            df = add_technical_indicators(df)
            df = df.dropna()

            if len(df) > 50:
                symbol_dfs[symbol] = df
                print(f"   ✅ {symbol}: {len(df)} days")
            else:
                print(f"   ⚠️ {symbol}: Not enough data after processing")
        else:
            print(f"   ⚠️ {symbol}: Not enough data")

    # CRITICAL: Standardize columns across all symbols to prevent shape mismatch
    if len(symbol_dfs) > 1:
        # Find common columns across ALL DataFrames
        common_cols = set(symbol_dfs[list(symbol_dfs.keys())[0]].columns)
        for sym, df in symbol_dfs.items():
            common_cols = common_cols.intersection(set(df.columns))

        common_cols = list(common_cols)
        print(
            f"📐 Standardizing to {len(common_cols)} common columns across {len(symbol_dfs)} symbols"
        )

        # Keep only common columns in each DataFrame
        for sym in symbol_dfs:
            symbol_dfs[sym] = symbol_dfs[sym][common_cols].copy()

    return MultiSymbolEnv(symbol_dfs, reward_type=reward_type, **kwargs)


if __name__ == "__main__":
    # Demo
    print("📊 Advanced Trading Environment Demo\n")

    import yfinance as yf
    from utils.indicators import add_technical_indicators

    # Test Sharpe reward
    print("Testing Sharpe Reward Environment...")
    ticker = yf.Ticker("QQQ")
    df = ticker.history(period="2y")
    df = df.reset_index()
    df = add_technical_indicators(df)
    df = df.dropna()

    env = SharpeRewardEnv(df, reward_type="sharpe")
    obs, info = env.reset()

    print(f"Observation shape: {obs.shape}")
    print(f"Action space: {env.action_space}")

    # Run random episode
    total_reward = 0
    steps = 0
    done = False

    while not done:
        action = env.action_space.sample()
        obs, reward, done, truncated, info = env.step(action)
        total_reward += reward
        steps += 1

    print(f"Episode finished: {steps} steps, total reward: {total_reward:.2f}")
    print(f"Final portfolio: ${info['portfolio_value']:,.2f}")

    # Test multi-symbol
    print("\nTesting Multi-Symbol Environment...")
    symbols = ["QQQ", "SPY", "AAPL"]

    multi_env = create_multi_symbol_env(symbols, start_date="2022-01-01")
    obs, info = multi_env.reset()

    print(f"Training on: {info['symbol']}")

    # Quick test
    for _ in range(10):
        action = multi_env.action_space.sample()
        obs, reward, done, truncated, info = multi_env.step(action)
        if done:
            obs, info = multi_env.reset()
            print(f"Switched to: {info['symbol']}")

    print("\n✅ Advanced environments ready!")
