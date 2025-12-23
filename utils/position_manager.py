#!/usr/bin/env python3
"""
Position Management System

Implements breakeven, trailing stops, and auto-close profit features
for improved profit protection and risk management.

Features:
- Breakeven: Move SL to entry after X pips profit
- Trailing Stop: Move SL as price moves favorably
- Auto-Close: Close position at target profit
- Step-based trailing: Move SL in discrete steps

Author: Forex Bot Team
Created: 2025-12-18
"""

import logging
from typing import Dict, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class PositionManager:
    """
    Manages open positions with breakeven, trailing stops, and auto-close.

    Improves profit protection and reduces risk of giving back gains.
    """

    def __init__(
        self,
        enable_breakeven: bool = True,
        breakeven_pips: float = 20.0,
        breakeven_offset: float = 5.0,
        enable_trailing: bool = True,
        trailing_start_pips: float = 30.0,
        trailing_step_pips: float = 10.0,
        trailing_distance_pips: float = 15.0,
        enable_auto_close: bool = False,
        auto_close_profit_usd: float = 100.0,
    ):
        """
        Initialize Position Manager.

        Args:
            enable_breakeven: Enable breakeven system
            breakeven_pips: Pips of profit before moving to breakeven
            breakeven_offset: Pips of profit to lock in at breakeven
            enable_trailing: Enable trailing stop
            trailing_start_pips: Pips of profit before trailing starts
            trailing_step_pips: Move SL in steps of X pips
            trailing_distance_pips: Distance to maintain behind price
            enable_auto_close: Enable auto-close at target profit
            auto_close_profit_usd: USD profit target for auto-close
        """
        self.enable_breakeven = enable_breakeven
        self.breakeven_pips = breakeven_pips
        self.breakeven_offset = breakeven_offset

        self.enable_trailing = enable_trailing
        self.trailing_start_pips = trailing_start_pips
        self.trailing_step_pips = trailing_step_pips
        self.trailing_distance_pips = trailing_distance_pips

        self.enable_auto_close = enable_auto_close
        self.auto_close_profit_usd = auto_close_profit_usd

        # Track position states
        self.position_states: Dict[str, Dict] = {}

        logger.info(
            f"PositionManager initialized: "
            f"BE={enable_breakeven}, Trail={enable_trailing}, "
            f"AutoClose={enable_auto_close}"
        )

    def manage_position(
        self,
        position_id: str,
        symbol: str,
        direction: str,
        entry_price: float,
        current_price: float,
        current_sl: float,
        current_profit_usd: float,
    ) -> Dict:
        """
        Manage a single position (check BE, trailing, auto-close).

        Args:
            position_id: Unique position identifier
            symbol: Trading pair
            direction: 'BUY' or 'SELL'
            entry_price: Entry price
            current_price: Current market price
            current_sl: Current stop loss
            current_profit_usd: Current profit in USD

        Returns:
            Dict with management actions:
            {
                'action': 'modify_sl' | 'close' | 'none',
                'new_sl': float (if action='modify_sl'),
                'reason': str
            }
        """
        # Initialize position state if new
        if position_id not in self.position_states:
            self.position_states[position_id] = {
                "max_favorable_price": current_price,
                "breakeven_applied": False,
                "trailing_applied": False,
                "last_trail_level": 0,
            }

        state = self.position_states[position_id]
        pip_size = self._get_pip_size(symbol, entry_price)

        # Calculate pips of profit
        if direction.upper() == "BUY":
            pips_profit = (current_price - entry_price) / pip_size
            # Update max favorable price
            if current_price > state["max_favorable_price"]:
                state["max_favorable_price"] = current_price
        else:  # SELL
            pips_profit = (entry_price - current_price) / pip_size
            # Update max favorable price
            if current_price < state["max_favorable_price"]:
                state["max_favorable_price"] = current_price

        # 1. Check Auto-Close first (highest priority)
        if self.enable_auto_close:
            if current_profit_usd >= self.auto_close_profit_usd:
                logger.info(
                    f"Auto-close triggered for {position_id}: "
                    f"Profit ${current_profit_usd:.2f} >= ${self.auto_close_profit_usd:.2f}"
                )
                return {
                    "action": "close",
                    "reason": f"Auto-close at ${current_profit_usd:.2f} profit",
                }

        # 2. Check Breakeven
        if self.enable_breakeven and not state["breakeven_applied"]:
            if pips_profit >= self.breakeven_pips:
                # Move SL to entry + offset
                if direction.upper() == "BUY":
                    new_sl = entry_price + (self.breakeven_offset * pip_size)
                else:
                    new_sl = entry_price - (self.breakeven_offset * pip_size)

                state["breakeven_applied"] = True
                logger.info(
                    f"Breakeven applied for {position_id}: "
                    f"{pips_profit:.1f} pips profit, SL -> {new_sl:.5f}"
                )

                return {
                    "action": "modify_sl",
                    "new_sl": new_sl,
                    "reason": f"Breakeven at +{pips_profit:.1f} pips",
                }

        # 3. Check Trailing Stop
        if self.enable_trailing:
            if pips_profit >= self.trailing_start_pips:
                new_sl = self._calculate_trailing_sl(
                    direction, state["max_favorable_price"], current_sl, pip_size, state
                )

                if new_sl is not None and new_sl != current_sl:
                    # Only move SL in favorable direction
                    should_update = False
                    if direction.upper() == "BUY" and new_sl > current_sl:
                        should_update = True
                    elif direction.upper() == "SELL" and new_sl < current_sl:
                        should_update = True

                    if should_update:
                        state["trailing_applied"] = True
                        logger.info(
                            f"Trailing stop for {position_id}: "
                            f"SL {current_sl:.5f} -> {new_sl:.5f}"
                        )

                        return {
                            "action": "modify_sl",
                            "new_sl": new_sl,
                            "reason": f"Trailing stop at +{pips_profit:.1f} pips",
                        }

        # No action needed
        return {"action": "none", "reason": "No management action required"}

    def _calculate_trailing_sl(
        self,
        direction: str,
        max_favorable_price: float,
        current_sl: float,
        pip_size: float,
        state: Dict,
    ) -> Optional[float]:
        """Calculate new trailing stop loss"""

        # Calculate new SL based on max favorable price
        if direction.upper() == "BUY":
            new_sl = max_favorable_price - (self.trailing_distance_pips * pip_size)
        else:  # SELL
            new_sl = max_favorable_price + (self.trailing_distance_pips * pip_size)

        # Apply step-based trailing (move in discrete steps)
        if direction.upper() == "BUY":
            pips_moved = (new_sl - current_sl) / pip_size
        else:
            pips_moved = (current_sl - new_sl) / pip_size

        # Only update if we've moved at least one step
        if pips_moved >= self.trailing_step_pips:
            # Round to nearest step
            steps = int(pips_moved / self.trailing_step_pips)

            if direction.upper() == "BUY":
                new_sl = current_sl + (steps * self.trailing_step_pips * pip_size)
            else:
                new_sl = current_sl - (steps * self.trailing_step_pips * pip_size)

            return new_sl

        return None

    def _get_pip_size(self, symbol: str, price: float) -> float:
        """Get pip size for a symbol"""
        if "JPY" in symbol.upper():
            return 0.01
        return 0.0001

    def remove_position(self, position_id: str):
        """Remove position from tracking"""
        if position_id in self.position_states:
            del self.position_states[position_id]

    def get_position_status(self, position_id: str) -> Dict:
        """Get current status of a position"""
        if position_id not in self.position_states:
            return {"exists": False}

        state = self.position_states[position_id]
        return {
            "exists": True,
            "breakeven_applied": state["breakeven_applied"],
            "trailing_applied": state["trailing_applied"],
            "max_favorable_price": state["max_favorable_price"],
        }


# Demo/Testing
if __name__ == "__main__":
    print("📈 Position Manager - Demo\n")

    # Create manager
    manager = PositionManager(
        enable_breakeven=True,
        breakeven_pips=20.0,
        breakeven_offset=5.0,
        enable_trailing=True,
        trailing_start_pips=30.0,
        trailing_step_pips=10.0,
        trailing_distance_pips=15.0,
        enable_auto_close=True,
        auto_close_profit_usd=100.0,
    )

    print("Configuration:")
    print(
        f"  Breakeven: {manager.breakeven_pips} pips (lock +{manager.breakeven_offset} pips)"
    )
    print(f"  Trailing: Start at {manager.trailing_start_pips} pips")
    print(
        f"  Trailing: {manager.trailing_distance_pips} pips distance, {manager.trailing_step_pips} pip steps"
    )
    print(f"  Auto-close: ${manager.auto_close_profit_usd}\n")

    # Simulate a BUY position
    position_id = "TEST_001"
    symbol = "EURUSD"
    direction = "BUY"
    entry_price = 1.0800
    initial_sl = 1.0770  # 30 pips SL

    print(f"Testing BUY position: {symbol}")
    print(f"Entry: {entry_price:.4f}, SL: {initial_sl:.4f}\n")

    # Simulate price movements
    test_scenarios = [
        (1.0810, 50, initial_sl, "Small profit"),
        (1.0825, 25, initial_sl, "Breakeven threshold"),
        (1.0840, 40, 1.0805, "After breakeven"),
        (1.0855, 55, 1.0805, "Trailing start"),
        (1.0870, 70, 1.0820, "Trailing active"),
        (1.0885, 85, 1.0835, "Trailing continues"),
    ]

    current_sl = initial_sl

    for i, (current_price, profit_usd, expected_sl, scenario) in enumerate(
        test_scenarios, 1
    ):
        print(f"Scenario {i}: {scenario}")
        print(f"  Price: {current_price:.4f}, Profit: ${profit_usd}")

        result = manager.manage_position(
            position_id=position_id,
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            current_price=current_price,
            current_sl=current_sl,
            current_profit_usd=profit_usd,
        )

        print(f"  Action: {result['action']}")
        print(f"  Reason: {result['reason']}")

        if result["action"] == "modify_sl":
            current_sl = result["new_sl"]
            print(f"  New SL: {current_sl:.4f}")
        elif result["action"] == "close":
            print(f"  Position closed!")
            break

        print()

    # Check final status
    status = manager.get_position_status(position_id)
    print("Final Position Status:")
    print(f"  Breakeven Applied: {status['breakeven_applied']}")
    print(f"  Trailing Applied: {status['trailing_applied']}")
    print(f"  Max Price: {status['max_favorable_price']:.4f}")

    print("\n✅ Demo complete!")
