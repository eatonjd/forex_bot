#!/usr/bin/env python3
"""
Risk Management Module.

Provides position sizing, stop-loss management, and portfolio constraints
for safer trading operations.

Features:
- Kelly Criterion position sizing
- Fixed fractional position sizing
- Stop-loss and take-profit orders
- Maximum position limits
- Daily loss limits
- Correlation-based portfolio constraints
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

# Import dynamic lot calculator for forex position sizing
try:
    from utils.position_sizing import DynamicLotCalculator

    DYNAMIC_LOT_AVAILABLE = True
except ImportError:
    DYNAMIC_LOT_AVAILABLE = False


class PositionSizeMethod(Enum):
    """Position sizing methods."""

    FIXED_FRACTION = "fixed_fraction"
    KELLY = "kelly"
    VOLATILITY_ADJUSTED = "volatility_adjusted"
    RISK_BASED = "risk_based"


@dataclass
class StopLoss:
    """Represents a stop-loss order."""

    entry_price: float
    stop_price: float
    stop_pct: float
    shares: float
    symbol: str
    order_type: str = "STOP"  # STOP, TRAILING

    @property
    def risk_amount(self) -> float:
        """Calculate the risk amount per share."""
        return self.entry_price - self.stop_price

    @property
    def total_risk(self) -> float:
        """Calculate total risk for the position."""
        return self.risk_amount * self.shares


@dataclass
class TakeProfit:
    """Represents a take-profit order."""

    entry_price: float
    target_price: float
    target_pct: float
    shares: float
    symbol: str

    @property
    def reward_amount(self) -> float:
        """Calculate the reward amount per share."""
        return self.target_price - self.entry_price

    @property
    def total_reward(self) -> float:
        """Calculate total potential reward."""
        return self.reward_amount * self.shares


class RiskManager:
    """
    Manages trading risk through position sizing and stop-losses.

    Implements various risk management rules to protect capital
    and ensure consistent position sizing.
    """

    def __init__(
        self,
        max_position_pct: float = 0.25,  # Max 25% in single position
        max_portfolio_risk_pct: float = 0.02,  # Max 2% portfolio risk per trade
        default_stop_pct: float = 0.05,  # 5% stop-loss
        default_target_pct: float = 0.10,  # 10% take-profit
        max_daily_loss_pct: float = 0.05,  # 5% max daily loss
        min_risk_reward_ratio: float = 1.5,  # Minimum 1.5:1 risk/reward
        max_open_positions: int = 10,  # Maximum concurrent positions
    ):
        """
        Initialize the risk manager.

        Args:
            max_position_pct: Maximum position size as % of portfolio
            max_portfolio_risk_pct: Maximum risk per trade as % of portfolio
            default_stop_pct: Default stop-loss percentage
            default_target_pct: Default take-profit percentage
            max_daily_loss_pct: Maximum allowed daily loss
            min_risk_reward_ratio: Minimum risk/reward ratio for trades
            max_open_positions: Maximum number of concurrent positions
        """
        self.max_position_pct = max_position_pct
        self.max_portfolio_risk_pct = max_portfolio_risk_pct
        self.default_stop_pct = default_stop_pct
        self.default_target_pct = default_target_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.min_risk_reward_ratio = min_risk_reward_ratio
        self.max_open_positions = max_open_positions

        # Track daily P&L
        self.daily_pnl = 0.0
        self.daily_start_value = 0.0

        # Active stops and targets
        self.active_stops: Dict[str, StopLoss] = {}
        self.active_targets: Dict[str, TakeProfit] = {}

        # Initialize DynamicLotCalculator for forex trading
        if DYNAMIC_LOT_AVAILABLE:
            self.lot_calculator = DynamicLotCalculator(
                min_lot_size=0.01,
                max_lot_size=10.0,
                default_risk_percent=max_portfolio_risk_pct
                * 100,  # Convert to percentage
            )
        else:
            self.lot_calculator = None

    def calculate_dynamic_stop_loss(
        self,
        entry_price: float,
        atr: float,
        volatility_state: str = "normal",  # normal, high, low
    ) -> float:
        """
        Calculate dynamic stop loss based on ATR and volatility state.

        Args:
            entry_price: Entry price
            atr: Average True Range
            volatility_state: 'high' or 'normal'

        Returns:
            Stop price
        """
        # Adaptive multipliers: 2.8x for high vol (give room), 1.9x for normal
        multiplier = 2.8 if volatility_state == "high" else 1.9
        stop_dist = atr * multiplier
        return entry_price - stop_dist

    def calculate_position_size(
        self,
        portfolio_value: float,
        entry_price: float,
        stop_price: Optional[float] = None,
        method: PositionSizeMethod = PositionSizeMethod.FIXED_FRACTION,
        volatility: Optional[float] = None,
    ) -> Tuple[int, float]:
        """
        Calculate appropriate position size.

        Args:
            portfolio_value: Total portfolio value
            entry_price: Entry price per share
            stop_price: Stop-loss price (optional)
            method: Position sizing method
            volatility: Asset volatility for vol-adjusted sizing

        Returns:
            Tuple of (shares, position_value)
        """
        if stop_price is None:
            stop_price = entry_price * (1 - self.default_stop_pct)

        risk_per_share = entry_price - stop_price

        if method == PositionSizeMethod.FIXED_FRACTION:
            # Fixed fraction: max_position_pct * portfolio
            max_position_value = portfolio_value * self.max_position_pct

        elif method == PositionSizeMethod.KELLY:
            # Kelly Criterion (simplified)
            # Assumes 50% win rate and 2:1 reward/risk as default
            win_rate = 0.5
            reward_risk = 2.0
            kelly_fraction = (win_rate * reward_risk - (1 - win_rate)) / reward_risk
            kelly_fraction = max(0, min(kelly_fraction, 0.25))  # Cap at 25%
            max_position_value = portfolio_value * kelly_fraction

        elif method == PositionSizeMethod.VOLATILITY_ADJUSTED:
            # Adjust position size based on volatility
            if volatility is None:
                volatility = 0.20  # Assume 20% annualized vol

            # Target 1% daily portfolio movement from this position
            target_contribution = 0.01
            daily_vol = volatility / np.sqrt(252)

            # Position size = target / daily_vol
            position_pct = target_contribution / daily_vol
            position_pct = min(position_pct, self.max_position_pct)
            max_position_value = portfolio_value * position_pct

        elif method == PositionSizeMethod.RISK_BASED:
            # Pure risk-based sizing
            # Max risk allowed per trade = Portfolio * Risk% (e.g., 2%)
            # Max shares = Max Risk Amount / Risk Per Share
            # This is handled primarily by the 'max_risk_amount' check below,
            # but we set the baseline max_position based on just cap.
            max_position_value = portfolio_value * self.max_position_pct

        else:  # EQUAL_WEIGHT
            max_position_value = portfolio_value / self.max_open_positions

        # Apply risk limit (Risk-Based Sizing Constraint)
        # This ensures we never risk more than max_portfolio_risk_pct of EQUITY
        max_risk_amount = portfolio_value * self.max_portfolio_risk_pct
        if risk_per_share > 0:
            max_shares_by_risk = int(max_risk_amount / risk_per_share)
        else:
            max_shares_by_risk = int(max_position_value / entry_price)

        # Calculate shares
        max_shares_by_position = int(max_position_value / entry_price)
        shares = min(max_shares_by_position, max_shares_by_risk)
        shares = max(1, shares)  # At least 1 share

        position_value = shares * entry_price

        return shares, position_value

    def calculate_forex_lot_size(
        self,
        balance: float,
        entry_price: float,
        stop_loss_price: float,
        risk_percent: Optional[float] = None,
        pip_value: float = 10.0,
    ) -> float:
        """
        Calculate forex lot size using dynamic risk-based sizing.

        This method uses the DynamicLotCalculator for precise forex
        position sizing based on account risk percentage.

        Args:
            balance: Current account balance
            entry_price: Entry price for the trade
            stop_loss_price: Stop loss price
            risk_percent: Risk percentage (uses default if None)
            pip_value: Value of 1 pip (default 10 for standard forex pairs)

        Returns:
            Lot size (e.g., 0.20 for 0.20 standard lots)

        Example:
            >>> rm = RiskManager(max_portfolio_risk_pct=0.01)  # 1% risk
            >>> lot = rm.calculate_forex_lot_size(
            ...     balance=10000,
            ...     entry_price=1.1000,
            ...     stop_loss_price=1.0950
            ... )
            >>> print(f"Lot size: {lot}")
            Lot size: 0.20
        """
        if self.lot_calculator is None:
            # Fallback to simple calculation if lot calculator not available
            risk_amount = (
                balance * (risk_percent or (self.max_portfolio_risk_pct * 100)) / 100
            )
            sl_distance = abs(entry_price - stop_loss_price)
            pip_size = 0.0001 if entry_price < 100 else 0.01
            pips = sl_distance / pip_size
            lot_size = risk_amount / (pips * pip_value) if pips > 0 else 0.01
            return max(0.01, min(lot_size, 10.0))

        # Use DynamicLotCalculator for precise sizing
        return self.lot_calculator.calculate_lot_size(
            balance=balance,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            risk_percent=risk_percent,
            pip_value=pip_value,
        )

    def create_stop_loss(
        self,
        symbol: str,
        entry_price: float,
        shares: float,
        stop_pct: Optional[float] = None,
        trailing: bool = False,
    ) -> StopLoss:
        """
        Create a stop-loss order.

        Args:
            symbol: Stock symbol
            entry_price: Entry price
            shares: Number of shares
            stop_pct: Stop-loss percentage (uses default if None)
            trailing: Whether to use trailing stop

        Returns:
            StopLoss object
        """
        if stop_pct is None:
            stop_pct = self.default_stop_pct

        stop_price = entry_price * (1 - stop_pct)

        stop = StopLoss(
            entry_price=entry_price,
            stop_price=stop_price,
            stop_pct=stop_pct,
            shares=shares,
            symbol=symbol,
            order_type="TRAILING" if trailing else "STOP",
        )

        self.active_stops[symbol] = stop
        return stop

    def create_take_profit(
        self,
        symbol: str,
        entry_price: float,
        shares: float,
        target_pct: Optional[float] = None,
    ) -> TakeProfit:
        """
        Create a take-profit order.

        Args:
            symbol: Stock symbol
            entry_price: Entry price
            shares: Number of shares
            target_pct: Target percentage (uses default if None)

        Returns:
            TakeProfit object
        """
        if target_pct is None:
            target_pct = self.default_target_pct

        target_price = entry_price * (1 + target_pct)

        target = TakeProfit(
            entry_price=entry_price,
            target_price=target_price,
            target_pct=target_pct,
            shares=shares,
            symbol=symbol,
        )

        self.active_targets[symbol] = target
        return target

    def check_stop_loss(self, symbol: str, current_price: float) -> bool:
        """
        Check if stop-loss should be triggered.

        Args:
            symbol: Stock symbol
            current_price: Current market price

        Returns:
            True if stop-loss triggered
        """
        if symbol not in self.active_stops:
            return False

        stop = self.active_stops[symbol]

        # Update trailing stop if applicable
        if stop.order_type == "TRAILING":
            new_stop = current_price * (1 - stop.stop_pct)
            if new_stop > stop.stop_price:
                stop.stop_price = new_stop

        return current_price <= stop.stop_price

    def check_take_profit(self, symbol: str, current_price: float) -> bool:
        """
        Check if take-profit should be triggered.

        Args:
            symbol: Stock symbol
            current_price: Current market price

        Returns:
            True if take-profit triggered
        """
        if symbol not in self.active_targets:
            return False

        target = self.active_targets[symbol]
        return current_price >= target.target_price

    def update_daily_pnl(self, current_value: float):
        """Update daily P&L tracking."""
        if self.daily_start_value == 0:
            self.daily_start_value = current_value

        self.daily_pnl = (
            current_value - self.daily_start_value
        ) / self.daily_start_value

    def check_daily_loss_limit(self) -> bool:
        """
        Check if daily loss limit has been reached.

        Returns:
            True if trading should stop for the day
        """
        return self.daily_pnl <= -self.max_daily_loss_pct

    def reset_daily_tracking(self, portfolio_value: float):
        """Reset daily tracking (call at market open)."""
        self.daily_start_value = portfolio_value
        self.daily_pnl = 0.0

    def validate_trade(
        self,
        symbol: str,
        entry_price: float,
        stop_price: float,
        target_price: float,
        current_positions: int,
    ) -> Tuple[bool, str]:
        """
        Validate a proposed trade against risk rules.

        Args:
            symbol: Stock symbol
            entry_price: Proposed entry price
            stop_price: Proposed stop-loss price
            target_price: Proposed take-profit price
            current_positions: Current number of open positions

        Returns:
            Tuple of (is_valid, reason)
        """
        # Check position limit
        if current_positions >= self.max_open_positions:
            return False, f"Maximum {self.max_open_positions} positions reached"

        # Check daily loss limit
        if self.check_daily_loss_limit():
            return False, "Daily loss limit reached - no new trades"

        # Check risk/reward ratio
        risk = entry_price - stop_price
        reward = target_price - entry_price

        if risk <= 0:
            return False, "Invalid stop-loss (must be below entry)"

        rr_ratio = reward / risk
        if rr_ratio < self.min_risk_reward_ratio:
            return (
                False,
                f"Risk/reward {rr_ratio:.2f} below minimum {self.min_risk_reward_ratio}",
            )

        return True, "Trade validated"

    def get_position_summary(self, symbol: str) -> Dict:
        """Get summary of position risk parameters."""
        summary = {
            "symbol": symbol,
            "has_stop_loss": symbol in self.active_stops,
            "has_take_profit": symbol in self.active_targets,
        }

        if symbol in self.active_stops:
            stop = self.active_stops[symbol]
            summary["stop_price"] = stop.stop_price
            summary["stop_pct"] = stop.stop_pct
            summary["stop_type"] = stop.order_type

        if symbol in self.active_targets:
            target = self.active_targets[symbol]
            summary["target_price"] = target.target_price
            summary["target_pct"] = target.target_pct

        return summary


def create_risk_adjusted_trade(
    symbol: str,
    portfolio_value: float,
    entry_price: float,
    volatility: float = 0.20,
    regime: str = "normal",
) -> Dict:
    """
    Create a risk-adjusted trade recommendation.

    Args:
        symbol: Stock symbol
        portfolio_value: Total portfolio value
        entry_price: Entry price
        volatility: Asset volatility
        regime: Market regime (bull, bear, volatile, normal)

    Returns:
        Trade recommendation dictionary
    """
    # Adjust parameters based on regime
    regime_adjustments = {
        "bull": {"stop_pct": 0.08, "target_pct": 0.15, "size_mult": 1.2},
        "bear": {"stop_pct": 0.05, "target_pct": 0.08, "size_mult": 0.5},
        "volatile": {"stop_pct": 0.10, "target_pct": 0.12, "size_mult": 0.3},
        "normal": {"stop_pct": 0.06, "target_pct": 0.10, "size_mult": 1.0},
    }

    adj = regime_adjustments.get(regime, regime_adjustments["normal"])

    # Create risk manager with adjusted params
    rm = RiskManager(
        default_stop_pct=adj["stop_pct"],
        default_target_pct=adj["target_pct"],
    )

    # Calculate position size
    stop_price = entry_price * (1 - adj["stop_pct"])
    shares, position_value = rm.calculate_position_size(
        portfolio_value,
        entry_price,
        stop_price,
        method=PositionSizeMethod.VOLATILITY_ADJUSTED,
        volatility=volatility,
    )

    # Apply regime multiplier
    shares = int(shares * adj["size_mult"])
    shares = max(1, shares)

    return {
        "symbol": symbol,
        "shares": shares,
        "entry_price": entry_price,
        "position_value": shares * entry_price,
        "position_pct": (shares * entry_price) / portfolio_value,
        "stop_price": stop_price,
        "stop_pct": adj["stop_pct"],
        "target_price": entry_price * (1 + adj["target_pct"]),
        "target_pct": adj["target_pct"],
        "risk_amount": shares * (entry_price - stop_price),
        "risk_pct": shares * (entry_price - stop_price) / portfolio_value,
        "regime": regime,
    }


if __name__ == "__main__":
    # Demo
    print("🛡️ Risk Management Demo\n")

    portfolio = 100000
    entry = 500.00

    rm = RiskManager()

    # Calculate position size
    shares, value = rm.calculate_position_size(
        portfolio, entry, method=PositionSizeMethod.VOLATILITY_ADJUSTED, volatility=0.25
    )

    print(f"Portfolio: ${portfolio:,}")
    print(f"Entry Price: ${entry}")
    print(f"Position Size: {shares} shares (${value:,.2f})")
    print(f"Position %: {value / portfolio:.1%}")

    # Create stops
    stop = rm.create_stop_loss("QQQ", entry, shares)
    target = rm.create_take_profit("QQQ", entry, shares)

    print(f"\nStop Loss: ${stop.stop_price:.2f} ({stop.stop_pct:.1%})")
    print(f"Take Profit: ${target.target_price:.2f} ({target.target_pct:.1%})")
    print(f"Risk Amount: ${stop.total_risk:,.2f}")
    print(f"Reward Amount: ${target.total_reward:,.2f}")
    print(f"Risk/Reward: {target.total_reward / stop.total_risk:.2f}")
