#!/usr/bin/env python3
"""
Search Space Definitions for Hyperopt

Defines parameter search spaces for different components:
- RL hyperparameters (learning rate, gamma, batch size)
- Indicator parameters (RSI, MACD, ATR)
- Risk management parameters
- Edge positioning parameters

Author: Forex Bot Team
Created: 2025-12-18
"""

from skopt.space import Real, Integer, Categorical
from typing import List


def get_rl_search_space() -> List:
    """
    RL hyperparameter search space.

    Parameters optimized:
    - learning_rate: Step size for gradient descent
    - gamma: Discount factor for future rewards
    - batch_size: Number of samples per training batch
    - buffer_size: Size of replay buffer
    - tau: Soft update coefficient for target network
    - n_steps: Steps before update (for on-policy algorithms)

    Returns:
        List of skopt Dimension objects
    """
    return [
        Real(0.0001, 0.01, name="learning_rate", prior="log-uniform"),
        Real(0.90, 0.9999, name="gamma"),
        Integer(32, 512, name="batch_size"),
        Integer(256, 4096, name="buffer_size"),
        Real(0.001, 0.1, name="tau"),  # Soft update
        Integer(128, 2048, name="n_steps"),  # For A2C/PPO
    ]


def get_indicator_search_space() -> List:
    """
    Technical indicator parameter search space.

    Parameters optimized:
    - RSI period
    - Fast/Slow MA periods
    - ATR period and multipliers
    - Bollinger Band parameters

    Returns:
        List of skopt Dimension objects
    """
    return [
        Integer(5, 50, name="rsi_period"),
        Integer(5, 30, name="ma_fast_period"),
        Integer(20, 200, name="ma_slow_period"),
        Integer(10, 30, name="atr_period"),
        Real(0.5, 3.0, name="atr_sl_multiplier"),
        Real(1.0, 5.0, name="atr_tp_multiplier"),
        Integer(10, 30, name="bb_period"),
        Real(1.5, 3.0, name="bb_std_dev"),
    ]


def get_risk_search_space() -> List:
    """
    Risk management parameter search space.

    Parameters optimized:
    - Position sizing
    - Stop loss and take profit levels
    - Risk/reward ratios
    - Daily loss limits

    Returns:
        List of skopt Dimension objects
    """
    return [
        Real(0.005, 0.05, name="max_position_pct"),
        Real(0.01, 0.10, name="stoploss_pct"),
        Real(0.02, 0.20, name="takeprofit_pct"),
        Real(0.5, 3.0, name="risk_reward_ratio"),
        Real(0.01, 0.05, name="max_daily_loss_pct"),
        Real(0.001, 0.01, name="risk_percent_per_trade"),
    ]


def get_edge_search_space() -> List:
    """
    Edge positioning parameter search space.

    Parameters optimized:
    - Capital allocation for Edge
    - Risk per trade
    - Minimum winrate and expectancy filters

    Returns:
        List of skopt Dimension objects
    """
    return [
        Real(0.3, 0.7, name="edge_capital_pct"),
        Real(0.005, 0.02, name="edge_allowed_risk"),
        Real(0.50, 0.70, name="edge_min_winrate"),
        Real(0.10, 0.30, name="edge_min_expectancy"),
        Integer(5, 20, name="edge_min_trade_number"),
    ]


def get_multi_symbol_search_space() -> List:
    """
    Multi-symbol configuration search space.

    Parameters optimized:
    - Position limits
    - Worker count

    Returns:
        List of skopt Dimension objects
    """
    return [
        Integer(5, 20, name="max_total_positions"),
        Integer(1, 5, name="max_positions_per_symbol"),
        Integer(2, 8, name="multi_symbol_max_workers"),
    ]


def get_combined_search_space(
    include_rl: bool = True,
    include_indicators: bool = False,
    include_risk: bool = False,
    include_edge: bool = False,
    include_multi_symbol: bool = False,
) -> List:
    """
    Get combined search space with selected components.

    Args:
        include_rl: Include RL hyperparameters
        include_indicators: Include indicator parameters
        include_risk: Include risk management parameters
        include_edge: Include Edge positioning parameters
        include_multi_symbol: Include multi-symbol parameters

    Returns:
        Combined list of search dimensions
    """
    space = []

    if include_rl:
        space.extend(get_rl_search_space())

    if include_indicators:
        space.extend(get_indicator_search_space())

    if include_risk:
        space.extend(get_risk_search_space())

    if include_edge:
        space.extend(get_edge_search_space())

    if include_multi_symbol:
        space.extend(get_multi_symbol_search_space())

    return space


def get_parameter_names(search_space: List) -> List[str]:
    """Extract parameter names from search space"""
    return [dim.name for dim in search_space]


def validate_parameters(params: dict, search_space: List) -> bool:
    """
    Validate that parameters are within search space bounds.

    Args:
        params: Parameter dictionary
        search_space: Search space definition

    Returns:
        True if valid, False otherwise
    """
    for dim in search_space:
        if dim.name not in params:
            return False

        value = params[dim.name]

        # Check bounds for Real/Integer
        if isinstance(dim, (Real, Integer)):
            if value < dim.bounds[0] or value > dim.bounds[1]:
                return False

        # Check categories for Categorical
        elif isinstance(dim, Categorical):
            if value not in dim.categories:
                return False

    return True


# Demo/Testing
if __name__ == "__main__":
    print("🔍 Hyperopt Search Spaces - Demo\n")

    # Show RL search space
    rl_space = get_rl_search_space()
    print("RL Hyperparameter Search Space:")
    for dim in rl_space:
        if isinstance(dim, Real):
            print(f"  {dim.name}: Real({dim.bounds[0]}, {dim.bounds[1]})")
        elif isinstance(dim, Integer):
            print(f"  {dim.name}: Integer({dim.bounds[0]}, {dim.bounds[1]})")
        elif isinstance(dim, Categorical):
            print(f"  {dim.name}: Categorical({dim.categories})")

    print(f"\nTotal RL parameters: {len(rl_space)}")

    # Show combined space
    print("\n" + "=" * 50)
    print("\nCombined Search Space (RL + Risk):")
    combined = get_combined_search_space(include_rl=True, include_risk=True)
    print(f"Total parameters: {len(combined)}")
    print(f"Parameter names: {get_parameter_names(combined)}")

    # Test parameter validation
    print("\n" + "=" * 50)
    print("\nParameter Validation Test:")
    test_params = {
        "learning_rate": 0.001,
        "gamma": 0.99,
        "batch_size": 128,
        "buffer_size": 1024,
        "tau": 0.01,
        "n_steps": 512,
        "max_position_pct": 0.02,
        "stoploss_pct": 0.05,
        "takeprofit_pct": 0.10,
        "risk_reward_ratio": 2.0,
        "max_daily_loss_pct": 0.03,
        "risk_percent_per_trade": 0.01,
    }

    is_valid = validate_parameters(test_params, combined)
    print(f"Test parameters valid: {is_valid}")

    print("\n✅ Demo complete!")
