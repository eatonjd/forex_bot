#!/usr/bin/env python3
"""
Edge Positioning System

Calculates optimal stoploss and position size per trading pair based on
historical performance analysis. Based on Freqtrade's Edge positioning
algorithm from AI-Scalpel-Trading-Bot.

Core Concept:
- Tests multiple stoploss levels for each pair
- Calculates win rate, risk/reward ratio, and expectancy
- Selects optimal stoploss that maximizes expectancy
- Adjusts position size based on risk and optimal stoploss

Formulas:
- Win Rate = Winning Trades / Total Trades
- Risk/Reward Ratio = Average Win / Average Loss
- Expectancy = (RR * WinRate) - (1 - WinRate)
- Position Size = (Capital * Risk%) / |Optimal Stoploss|

Author: Forex Bot Team
Created: 2025-12-18
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class PairEdgeInfo:
    """Edge positioning information for a trading pair"""

    pair: str
    stoploss: float
    position_size: float
    winrate: float
    risk_reward_ratio: float
    expectancy: float
    nb_trades: int
    avg_trade_duration: float


class EdgePositioner:
    """
    Calculate optimal stoploss and position size per pair.

    This uses historical trade data to find the stoploss level
    that maximizes expectancy, then calculates appropriate position
    sizing based on allowed risk.
    """

    def __init__(
        self,
        capital_percentage: float = 0.5,
        allowed_risk: float = 0.01,
        stoploss_range_min: float = -0.01,
        stoploss_range_max: float = -0.10,
        stoploss_range_step: float = -0.01,
        min_winrate: float = 0.60,
        min_expectancy: float = 0.20,
        min_trade_number: int = 10,
        max_trade_duration_minutes: int = 1440,
    ):
        """
        Initialize Edge Positioner.

        Args:
            capital_percentage: Fraction of total capital available for Edge (default: 50%)
            allowed_risk: Percentage of capital to risk per trade (default: 1%)
            stoploss_range_min: Minimum stoploss to test (default: -1%)
            stoploss_range_max: Maximum stoploss to test (default: -10%)
            stoploss_range_step: Step size for stoploss testing (default: -1%)
            min_winrate: Minimum acceptable win rate (default: 60%)
            min_expectancy: Minimum acceptable expectancy (default: 0.20)
            min_trade_number: Minimum trades required for statistics (default: 10)
            max_trade_duration_minutes: Maximum trade duration to consider (default: 1440 = 1 day)
        """
        self.capital_pct = capital_percentage
        self.allowed_risk = allowed_risk
        self.min_winrate = min_winrate
        self.min_expectancy = min_expectancy
        self.min_trades = min_trade_number
        self.max_duration = max_trade_duration_minutes

        # Generate stoploss range to test
        self.stoploss_range = np.arange(
            stoploss_range_min, stoploss_range_max, stoploss_range_step
        )

        logger.info(
            f"EdgePositioner initialized: testing {len(self.stoploss_range)} "
            f"stoploss levels from {stoploss_range_min} to {stoploss_range_max}"
        )

    def calculate_for_pair(
        self, pair: str, historical_trades: pd.DataFrame, total_capital: float
    ) -> Optional[PairEdgeInfo]:
        """
        Calculate Edge metrics for a single pair.

        Args:
            pair: Trading pair symbol
            historical_trades: DataFrame with columns: 'entry_price', 'exit_price',
                              'entry_time', 'exit_time', 'profit_pct', 'trade_duration'
            total_capital: Total available capital

        Returns:
            PairEdgeInfo if pair meets criteria, None otherwise
        """
        if len(historical_trades) < self.min_trades:
            logger.warning(
                f"{pair}: Insufficient trades ({len(historical_trades)} < {self.min_trades})"
            )
            return None

        # Filter trades by duration
        trades = historical_trades[
            historical_trades["trade_duration"] <= self.max_duration
        ].copy()

        if len(trades) < self.min_trades:
            logger.warning(
                f"{pair}: Insufficient trades after duration filter "
                f"({len(trades)} < {self.min_trades})"
            )
            return None

        best_stoploss = None
        best_expectancy = -np.inf
        best_metrics = None

        # Test each stoploss level
        for sl in self.stoploss_range:
            # Simulate trades with this stoploss
            simulated_trades = self._simulate_trades_with_stoploss(trades, sl)

            if len(simulated_trades) < self.min_trades:
                continue

            # Calculate metrics for this stoploss level
            metrics = self._calculate_metrics(simulated_trades)

            # Track best expectancy
            if metrics["expectancy"] > best_expectancy:
                best_expectancy = metrics["expectancy"]
                best_stoploss = sl
                best_metrics = metrics

        if best_metrics is None:
            logger.warning(f"{pair}: No valid stoploss level found")
            return None

        # Check if pair meets minimum criteria
        if best_metrics["winrate"] < self.min_winrate:
            logger.info(
                f"{pair}: Win rate {best_metrics['winrate']:.1%} "
                f"below minimum {self.min_winrate:.1%}"
            )
            return None

        if best_metrics["expectancy"] < self.min_expectancy:
            logger.info(
                f"{pair}: Expectancy {best_metrics['expectancy']:.3f} "
                f"below minimum {self.min_expectancy:.3f}"
            )
            return None

        # Calculate position size
        position_size = self._calculate_position_size(best_stoploss, total_capital)

        logger.info(
            f"✅ {pair}: SL={best_stoploss:.3f}, "
            f"Size={position_size:.3f}, WR={best_metrics['winrate']:.1%}, "
            f"Exp={best_metrics['expectancy']:.3f}"
        )

        return PairEdgeInfo(
            pair=pair,
            stoploss=best_stoploss,
            position_size=position_size,
            winrate=best_metrics["winrate"],
            risk_reward_ratio=best_metrics["risk_reward_ratio"],
            expectancy=best_metrics["expectancy"],
            nb_trades=best_metrics["nb_trades"],
            avg_trade_duration=best_metrics["avg_duration"],
        )

    def calculate_for_all_pairs(
        self, pairs_data: Dict[str, pd.DataFrame], total_capital: float
    ) -> Dict[str, PairEdgeInfo]:
        """
        Calculate Edge for multiple pairs.

        Args:
            pairs_data: Dict mapping pair symbols to historical trade DataFrames
            total_capital: Total available capital

        Returns:
            Dict mapping pair symbols to PairEdgeInfo (only accepted pairs)
        """
        results = {}

        for pair, trades in pairs_data.items():
            logger.info(f"Calculating Edge for {pair}...")
            edge_info = self.calculate_for_pair(pair, trades, total_capital)

            if edge_info:
                results[pair] = edge_info

        logger.info(
            f"Edge calculation complete: {len(results)}/{len(pairs_data)} "
            f"pairs accepted"
        )

        return results

    def _simulate_trades_with_stoploss(
        self, trades: pd.DataFrame, stoploss: float
    ) -> pd.DataFrame:
        """
        Simulate how trades would have performed with a specific stoploss.

        Args:
            trades: Historical trades
            stoploss: Stoploss level to test (e.g., -0.05 for -5%)

        Returns:
            DataFrame with simulated profits
        """
        simulated = trades.copy()

        # For each trade, check if stoploss would have been hit
        # If actual profit is worse than stoploss, cap it at stoploss
        simulated["simulated_profit"] = simulated["profit_pct"].apply(
            lambda x: max(x, stoploss)
        )

        return simulated

    def _calculate_metrics(self, trades: pd.DataFrame) -> Dict:
        """
        Calculate performance metrics for a set of trades.

        Args:
            trades: DataFrame with 'simulated_profit' column

        Returns:
            Dict with winrate, risk_reward_ratio, expectancy, etc.
        """
        nb_trades = len(trades)
        profits = trades["simulated_profit"]

        # Separate winning and losing trades
        wins = profits[profits > 0]
        losses = profits[profits < 0]

        nb_wins = len(wins)
        nb_losses = len(losses)

        # Calculate win rate
        winrate = nb_wins / nb_trades if nb_trades > 0 else 0

        # Calculate average win and loss
        avg_win = wins.mean() if len(wins) > 0 else 0
        avg_loss = abs(losses.mean()) if len(losses) > 0 else 0

        # Calculate risk/reward ratio
        risk_reward_ratio = avg_win / avg_loss if avg_loss > 0 else 0

        # Calculate expectancy
        # Expectancy = (WinRate * AvgWin) - (LossRate * AvgLoss)
        expectancy = (winrate * avg_win) - ((1 - winrate) * avg_loss)

        # Calculate average trade duration
        if "trade_duration" in trades.columns:
            avg_duration = trades["trade_duration"].mean()
        else:
            avg_duration = 0

        return {
            "nb_trades": nb_trades,
            "winrate": winrate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "risk_reward_ratio": risk_reward_ratio,
            "expectancy": expectancy,
            "avg_duration": avg_duration,
        }

    def _calculate_position_size(self, stoploss: float, total_capital: float) -> float:
        """
        Calculate position size based on optimal stoploss and risk.

        Formula: Position Size = (Total Capital * Capital% * Risk%) / |Stoploss|

        Args:
            stoploss: Optimal stoploss level (e.g., -0.05)
            total_capital: Total available capital

        Returns:
            Position size as fraction of capital
        """
        available_capital = total_capital * self.capital_pct
        risk_amount = available_capital * self.allowed_risk

        # Position size = Risk Amount / |Stoploss|
        position_size = risk_amount / abs(stoploss) if stoploss != 0 else 0

        # Cap at available capital
        position_size = min(position_size, available_capital)

        # Return as fraction of total capital
        return position_size / total_capital if total_capital > 0 else 0

    def get_stake_amount(
        self,
        pair: str,
        edge_info: PairEdgeInfo,
        free_capital: float,
        total_capital: float,
        capital_in_trade: float,
    ) -> float:
        """
        Calculate the stake amount for a specific trade.

        Args:
            pair: Trading pair
            edge_info: Edge information for the pair
            free_capital: Currently available capital
            total_capital: Total account capital
            capital_in_trade: Capital currently in open positions

        Returns:
            Stake amount in USD
        """
        # Calculate available capital for Edge
        available_capital = (total_capital + capital_in_trade) * self.capital_pct

        # Calculate allowed risk amount
        risk_amount = available_capital * self.allowed_risk

        # Calculate max position size based on stoploss
        max_position_size = abs(risk_amount / edge_info.stoploss)

        # Use minimum of max position and free capital
        position_size = min(max_position_size, free_capital)

        logger.debug(
            f"{pair}: WR={edge_info.winrate:.1%}, "
            f"Exp={edge_info.expectancy:.3f}, "
            f"Size=${position_size:.2f}, "
            f"SL={edge_info.stoploss:.3f}"
        )

        return position_size


# Demo/testing
if __name__ == "__main__":
    print("📊 Edge Positioning System - Demo\n")

    # Create sample historical trades for EUR/USD
    np.random.seed(42)
    n_trades = 100

    # Simulate trades with 60% win rate
    profits = []
    for _ in range(n_trades):
        if np.random.random() < 0.6:  # Win
            profit = np.random.uniform(0.01, 0.05)  # 1-5% profit
        else:  # Loss
            profit = np.random.uniform(-0.08, -0.01)  # 1-8% loss
        profits.append(profit)

    trades_df = pd.DataFrame(
        {
            "entry_price": np.random.uniform(1.08, 1.12, n_trades),
            "exit_price": np.random.uniform(1.08, 1.12, n_trades),
            "entry_time": pd.date_range("2024-01-01", periods=n_trades, freq="H"),
            "exit_time": pd.date_range("2024-01-01", periods=n_trades, freq="H")
            + pd.Timedelta(hours=2),
            "profit_pct": profits,
            "trade_duration": np.random.uniform(60, 480, n_trades),  # 1-8 hours
        }
    )

    # Initialize Edge Positioner
    edge = EdgePositioner(
        capital_percentage=0.5, allowed_risk=0.01, min_winrate=0.55, min_expectancy=0.15
    )

    # Calculate Edge for EUR/USD
    print("Testing Edge Positioning on EUR/USD...")
    print(f"Total trades: {len(trades_df)}")
    print(f"Testing {len(edge.stoploss_range)} stoploss levels\n")

    result = edge.calculate_for_pair("EUR/USD", trades_df, total_capital=10000)

    if result:
        print("✅ Edge Analysis Results:")
        print(f"  Pair: {result.pair}")
        print(f"  Optimal Stoploss: {result.stoploss:.2%}")
        print(f"  Position Size: {result.position_size:.2%} of capital")
        print(f"  Win Rate: {result.winrate:.1%}")
        print(f"  Risk/Reward Ratio: {result.risk_reward_ratio:.2f}:1")
        print(f"  Expectancy: {result.expectancy:.3f}")
        print(f"  Number of Trades: {result.nb_trades}")
        print(f"  Avg Trade Duration: {result.avg_trade_duration:.0f} minutes")

        print(f"\n💰 With $10,000 capital:")
        stake = edge.get_stake_amount(
            "EUR/USD",
            result,
            free_capital=10000,
            total_capital=10000,
            capital_in_trade=0,
        )
        print(f"  Stake Amount: ${stake:.2f}")
        print(f"  Risk Amount: ${stake * abs(result.stoploss):.2f}")
    else:
        print("❌ Pair did not meet Edge criteria")

    print("\n✅ Demo complete!")
