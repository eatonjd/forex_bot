#!/usr/bin/env python3
"""
Dynamic Position Sizing Module

Implements risk-based position sizing adapted from Bot-ForexMT5.
Calculates lot sizes based on account balance and risk percentage per trade.

Author: Forex Bot Team
Created: 2025-12-18
"""

from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)


class DynamicLotCalculator:
    """
    Calculate position size based on risk percentage of account balance.

    Ensures consistent risk across all trades by dynamically adjusting
    lot size based on stop loss distance and account equity.

    Formula:
        lot_size = (balance * risk_percent) / (sl_distance_usd)

    Where:
        - balance: Current account balance/equity
        - risk_percent: Percentage of balance to risk (e.g., 1.0 = 1%)
        - sl_distance_usd: Distance to stop loss in USD
    """

    def __init__(
        self,
        min_lot_size: float = 0.01,
        max_lot_size: float = 10.0,
        default_risk_percent: float = 1.0,
    ):
        """
        Initialize the dynamic lot calculator.

        Args:
            min_lot_size: Minimum allowed lot size
            max_lot_size: Maximum allowed lot size
            default_risk_percent: Default risk percentage per trade
        """
        self.min_lot = min_lot_size
        self.max_lot = max_lot_size
        self.default_risk = default_risk_percent

        logger.info(
            f"DynamicLotCalculator initialized: "
            f"min={min_lot_size}, max={max_lot_size}, "
            f"default_risk={default_risk_percent}%"
        )

    def calculate_lot_size(
        self,
        balance: float,
        entry_price: float,
        stop_loss_price: float,
        pip_value: float = 10.0,  # Standard for forex pairs
        risk_percent: Optional[float] = None,
        contract_size: float = 100000,  # Standard lot size
    ) -> float:
        """
        Calculate appropriate lot size based on risk parameters.

        Args:
            balance: Current account balance in USD
            entry_price: Proposed entry price
            stop_loss_price: Stop loss price
            pip_value: Value of 1 pip in USD (typically 10 for forex)
            risk_percent: Risk percentage (uses default if None)
            contract_size: Contract size (100,000 for standard lot)

        Returns:
            Calculated lot size, clamped to min/max limits

        Example:
            >>> calc = DynamicLotCalculator()
            >>> lot = calc.calculate_lot_size(
            ...     balance=10000,
            ...     entry_price=1.1000,
            ...     stop_loss_price=1.0950,
            ...     risk_percent=1.0
            ... )
            >>> print(f"Lot size: {lot}")
            Lot size: 0.20
        """
        if balance <= 0:
            logger.error(f"Invalid balance: {balance}")
            return self.min_lot

        if entry_price <= 0 or stop_loss_price <= 0:
            logger.error(f"Invalid prices: entry={entry_price}, sl={stop_loss_price}")
            return self.min_lot

        # Use default risk if not specified
        risk_pct = risk_percent if risk_percent is not None else self.default_risk

        # Calculate risk amount in USD
        risk_amount = balance * (risk_pct / 100)

        # Calculate stop loss distance in pips
        sl_distance_pips = abs(entry_price - stop_loss_price)

        # Calculate stop loss distance in USD for 1 standard lot
        # For forex: sl_distance_usd = sl_distance_pips * pip_value * lot_size
        # Rearranging: lot_size = risk_amount / (sl_distance_pips * pip_value)

        if sl_distance_pips == 0:
            logger.warning("Stop loss distance is zero, using minimum lot")
            return self.min_lot

        # Convert pip distance to actual price distance
        # For most forex pairs, 1 pip = 0.0001
        pip_size = 0.0001 if entry_price < 100 else 0.01  # Adjust for JPY pairs
        pips = sl_distance_pips / pip_size

        # Calculate lot size
        lot_size = risk_amount / (pips * pip_value)

        # Clamp to min/max limits
        lot_size = max(self.min_lot, min(lot_size, self.max_lot))

        # Round to 2 decimal places (standard lot precision)
        lot_size = round(lot_size, 2)

        logger.debug(
            f"Position sizing: balance=${balance:.2f}, "
            f"risk={risk_pct}%, entry={entry_price:.5f}, "
            f"sl={stop_loss_price:.5f}, pips={pips:.1f}, "
            f"lot_size={lot_size:.2f}"
        )

        return lot_size

    def calculate_position_value(
        self, lot_size: float, current_price: float, contract_size: float = 100000
    ) -> float:
        """
        Calculate the total value of a position.

        Args:
            lot_size: Number of lots
            current_price: Current market price
            contract_size: Size of one standard lot

        Returns:
            Position value in USD
        """
        return lot_size * contract_size * current_price

    def calculate_risk_reward_ratio(
        self, entry_price: float, stop_loss_price: float, take_profit_price: float
    ) -> float:
        """
        Calculate the risk/reward ratio for a trade.

        Args:
            entry_price: Entry price
            stop_loss_price: Stop loss price
            take_profit_price: Take profit price

        Returns:
            Risk/reward ratio (e.g., 2.0 means 2:1 reward to risk)
        """
        risk = abs(entry_price - stop_loss_price)
        reward = abs(take_profit_price - entry_price)

        if risk == 0:
            return 0.0

        return reward / risk

    def validate_position_size(
        self, lot_size: float, balance: float, max_risk_percent: float = 5.0
    ) -> Dict[str, any]:
        """
        Validate if the position size is within acceptable risk limits.

        Args:
            lot_size: Proposed lot size
            balance: Account balance
            max_risk_percent: Maximum acceptable risk percentage

        Returns:
            Dict with validation results
        """
        is_valid = True
        warnings = []

        # Check lot size limits
        if lot_size < self.min_lot:
            is_valid = False
            warnings.append(f"Lot size {lot_size} below minimum {self.min_lot}")

        if lot_size > self.max_lot:
            is_valid = False
            warnings.append(f"Lot size {lot_size} exceeds maximum {self.max_lot}")

        # Check if position is too large relative to balance
        # Rough estimate: 1 standard lot ~ $100,000 notional
        notional_value = lot_size * 100000
        if notional_value > balance * 20:  # 20x leverage check
            warnings.append(
                f"High leverage: notional ${notional_value:.0f} "
                f"vs balance ${balance:.2f}"
            )

        return {
            "is_valid": is_valid,
            "lot_size": lot_size,
            "warnings": warnings,
            "notional_value": notional_value,
        }


# Convenience function for quick calculations
def calculate_lot_size(
    balance: float,
    entry_price: float,
    stop_loss_price: float,
    risk_percent: float = 1.0,
    **kwargs,
) -> float:
    """
    Quick function to calculate lot size without instantiating class.

    Args:
        balance: Account balance
        entry_price: Entry price
        stop_loss_price: Stop loss price
        risk_percent: Risk percentage
        **kwargs: Additional arguments for DynamicLotCalculator

    Returns:
        Calculated lot size
    """
    calculator = DynamicLotCalculator()
    return calculator.calculate_lot_size(
        balance=balance,
        entry_price=entry_price,
        stop_loss_price=stop_loss_price,
        risk_percent=risk_percent,
        **kwargs,
    )


if __name__ == "__main__":
    # Example usage and testing
    print("🧮 Dynamic Lot Calculator Demo\n")

    calc = DynamicLotCalculator(
        min_lot_size=0.01, max_lot_size=10.0, default_risk_percent=1.0
    )

    # Test case 1: Standard forex trade
    print("Test 1: EUR/USD trade")
    balance = 10000
    entry = 1.1000
    sl = 1.0950  # 50 pips stop
    tp = 1.1100  # 100 pips target

    lot = calc.calculate_lot_size(
        balance=balance, entry_price=entry, stop_loss_price=sl, risk_percent=1.0
    )

    rr = calc.calculate_risk_reward_ratio(entry, sl, tp)

    print(f"  Balance: ${balance:,.2f}")
    print(f"  Entry: {entry:.5f}")
    print(f"  Stop Loss: {sl:.5f} ({abs(entry - sl) * 10000:.0f} pips)")
    print(f"  Take Profit: {tp:.5f} ({abs(tp - entry) * 10000:.0f} pips)")
    print(f"  Calculated Lot Size: {lot:.2f}")
    print(f"  Risk/Reward Ratio: {rr:.2f}:1")

    validation = calc.validate_position_size(lot, balance)
    print(f"  Valid: {validation['is_valid']}")
    if validation["warnings"]:
        for warning in validation["warnings"]:
            print(f"  ⚠️  {warning}")

    # Test case 2: Higher risk
    print("\nTest 2: Higher risk (2%)")
    lot2 = calc.calculate_lot_size(
        balance=balance, entry_price=entry, stop_loss_price=sl, risk_percent=2.0
    )
    print(f"  Lot Size at 2% risk: {lot2:.2f}")

    # Test case 3: Tighter stop
    print("\nTest 3: Tighter stop (20 pips)")
    sl_tight = 1.0980
    lot3 = calc.calculate_lot_size(
        balance=balance, entry_price=entry, stop_loss_price=sl_tight, risk_percent=1.0
    )
    print(f"  Lot Size with 20 pip stop: {lot3:.2f}")

    print("\n✅ Demo complete!")
