#!/usr/bin/env python3
"""
Custom Loss Functions for Hyperopt

Different objectives for optimization:
- Sharpe Ratio (risk-adjusted returns)
- Sortino Ratio (downside risk)
- Calmar Ratio (return/max drawdown)
- Custom weighted combinations

Author: Forex Bot Team
Created: 2025-12-18
"""

import numpy as np
from typing import Dict
import logging

logger = logging.getLogger(__name__)


class HyperoptLoss:
    """Base class for Hyperopt loss functions"""

    @staticmethod
    def calculate_loss(results: Dict) -> float:
        """
        Calculate loss from backtest results.

        Args:
            results: Dict with backtest metrics

        Returns:
            Loss value (lower is better)
        """
        raise NotImplementedError


class SharpeLoss(HyperoptLoss):
    """
    Maximize Sharpe Ratio.

    Sharpe = (Return - RiskFreeRate) / Volatility

    Loss = -Sharpe (negative for minimization)
    """

    @staticmethod
    def calculate_loss(results: Dict) -> float:
        sharpe = results.get("sharpe_ratio", 0)
        return -sharpe  # Negative for minimization


class SortinoLoss(HyperoptLoss):
    """
    Maximize Sortino Ratio.

    Sortino = (Return - RiskFreeRate) / DownsideDeviation

    Better than Sharpe as it only penalizes downside volatility.
    """

    @staticmethod
    def calculate_loss(results: Dict) -> float:
        sortino = results.get("sortino_ratio", 0)
        return -sortino


class CalmarLoss(HyperoptLoss):
    """
    Maximize Calmar Ratio.

    Calmar = AnnualReturn / MaxDrawdown

    Focuses on return relative to worst drawdown.
    """

    @staticmethod
    def calculate_loss(results: Dict) -> float:
        calmar = results.get("calmar_ratio", 0)
        return -calmar


class ProfitFactorLoss(HyperoptLoss):
    """
    Maximize Profit Factor.

    Profit Factor = GrossProfit / GrossLoss

    Simple but effective metric.
    """

    @staticmethod
    def calculate_loss(results: Dict) -> float:
        profit_factor = results.get("profit_factor", 1.0)
        return -profit_factor


class CustomLoss(HyperoptLoss):
    """
    Custom weighted loss function.

    Combines multiple objectives:
    - Maximize Sharpe
    - Minimize drawdown
    - Minimize volatility
    - Maximize win rate
    """

    @staticmethod
    def calculate_loss(results: Dict) -> float:
        sharpe = results.get("sharpe_ratio", 0)
        max_dd = results.get("max_drawdown", 0.5)  # 0-1 range
        volatility = results.get("volatility", 0.3)
        win_rate = results.get("win_rate", 0.5)

        # Weighted combination
        # Goal: High Sharpe, Low DD, Low Vol, High Win Rate
        loss = (
            -sharpe * 1.0  # Maximize Sharpe (weight: 1.0)
            + max_dd * 2.0  # Minimize drawdown (weight: 2.0)
            + volatility * 0.5  # Minimize volatility (weight: 0.5)
            - win_rate * 0.5  # Maximize win rate (weight: 0.5)
        )

        return loss


class SharpeDrawdownLoss(HyperoptLoss):
    """
    Balanced: Maximize Sharpe while minimizing drawdown.

    Loss = -Sharpe + (2 × MaxDrawdown)
    """

    @staticmethod
    def calculate_loss(results: Dict) -> float:
        sharpe = results.get("sharpe_ratio", 0)
        max_dd = results.get("max_drawdown", 0.5)

        return -sharpe + (2.0 * max_dd)


class WinRateWeightedLoss(HyperoptLoss):
    """
    Win rate weighted Sharpe.

    Loss = -(Sharpe × WinRate)

    Encourages strategies with both good returns AND high win rate.
    """

    @staticmethod
    def calculate_loss(results: Dict) -> float:
        sharpe = results.get("sharpe_ratio", 0)
        win_rate = results.get("win_rate", 0.5)

        return -(sharpe * win_rate)


class ExpectancyLoss(HyperoptLoss):
    """
    Maximize expectancy per trade.

    Expectancy = (WinRate × AvgWin) - (LossRate × AvgLoss)
    """

    @staticmethod
    def calculate_loss(results: Dict) -> float:
        expectancy = results.get("expectancy", 0)
        return -expectancy


def get_loss_function(name: str) -> HyperoptLoss:
    """
    Get loss function by name.

    Args:
        name: Loss function name
            ('sharpe', 'sortino', 'calmar', 'custom', etc.)

    Returns:
        HyperoptLoss class
    """
    loss_functions = {
        "sharpe": SharpeLoss,
        "sortino": SortinoLoss,
        "calmar": CalmarLoss,
        "profit_factor": ProfitFactorLoss,
        "custom": CustomLoss,
        "sharpe_dd": SharpeDrawdownLoss,
        "win_rate_weighted": WinRateWeightedLoss,
        "expectancy": ExpectancyLoss,
    }

    if name not in loss_functions:
        logger.warning(f"Unknown loss function '{name}', using 'sharpe'")
        return SharpeLoss

    return loss_functions[name]


# Demo/Testing
if __name__ == "__main__":
    print("📉 Hyperopt Loss Functions - Demo\n")

    # Sample backtest results
    sample_results = {
        "sharpe_ratio": 1.75,
        "sortino_ratio": 2.15,
        "calmar_ratio": 1.20,
        "max_drawdown": 0.12,
        "volatility": 0.18,
        "win_rate": 0.62,
        "profit_factor": 1.85,
        "expectancy": 0.25,
        "total_return": 0.45,
    }

    print("Sample Backtest Results:")
    for key, value in sample_results.items():
        print(f"  {key}: {value:.3f}")

    print("\n" + "=" * 50)
    print("\nLoss Function Comparison:\n")

    loss_names = [
        "sharpe",
        "sortino",
        "calmar",
        "profit_factor",
        "custom",
        "sharpe_dd",
        "win_rate_weighted",
        "expectancy",
    ]

    for name in loss_names:
        loss_fn = get_loss_function(name)
        loss_value = loss_fn.calculate_loss(sample_results)
        print(f"{name:20s}: {loss_value:8.4f}")

    print("\n" + "=" * 50)
    print("\nLower loss = better performance")
    print("Negative values = positive objectives (Sharpe, etc.)")
    print("Positive values = penalties (drawdown, volatility)")

    print("\n✅ Demo complete!")
