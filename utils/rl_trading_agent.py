#!/usr/bin/env python3
"""
RL Trading Agent with Position Manager Integration

Combines RL agent decisions with Position Manager for:
- RL: Entry decision (BUY/SELL/HOLD)
- PM: Exit optimization (Breakeven, Trailing, Auto-close)

Author: Forex Bot Team
Created: 2025-12-19
"""

from stable_baselines3 import PPO
from utils.position_manager import PositionManager
from typing import Dict, Optional
import numpy as np


class RLTradingAgent:
    """
    RL Agent + Position Manager wrapper.

    The RL agent decides WHEN to enter trades.
    The Position Manager decides HOW to exit for maximum profit.
    """

    def __init__(
        self,
        model_path: str,
        use_position_manager: bool = True,
        pm_config: Optional[Dict] = None,
    ):
        """
        Initialize RL Trading Agent.

        Args:
            model_path: Path to trained PPO model (without .zip)
            use_position_manager: Enable Position Manager
            pm_config: Position Manager configuration
        """
        # Load RL model
        self.model = PPO.load(model_path)
        print(f"✅ Loaded RL model: {model_path}")

        # Position Manager
        self.use_pm = use_position_manager
        if self.use_pm:
            pm_config = pm_config or {}
            self.pm = PositionManager(
                enable_breakeven=pm_config.get("enable_breakeven", True),
                breakeven_pips=pm_config.get("breakeven_pips", 20.0),
                breakeven_offset=pm_config.get("breakeven_offset", 5.0),
                enable_trailing=pm_config.get("enable_trailing", True),
                trailing_start_pips=pm_config.get("trailing_start_pips", 30.0),
                trailing_step_pips=pm_config.get("trailing_step_pips", 10.0),
                trailing_distance_pips=pm_config.get("trailing_distance_pips", 15.0),
                enable_auto_close=pm_config.get("enable_auto_close", False),
                auto_close_profit_usd=pm_config.get("auto_close_profit_usd", 100.0),
            )
            print("✅ Position Manager enabled")
        else:
            self.pm = None
            print("⚠️  Position Manager disabled")

        # Track current position
        self.position = None  # {id, symbol, direction, entry_price, current_sl}

    def predict(
        self, observation: np.ndarray, current_price: float, deterministic: bool = True
    ) -> int:
        """
        Get trading action from RL agent + Position Manager.

        Args:
            observation: Environment observation
            current_price: Current market price
            deterministic: Use deterministic policy

        Returns:
            action: 0=HOLD, 1=BUY, 2=SELL
        """
        # Get RL agent's action
        rl_action, _states = self.model.predict(
            observation, deterministic=deterministic
        )

        # If we have a position, check Position Manager first
        if self.position and self.use_pm:
            pm_action = self._check_position_manager(current_price)
            if pm_action is not None:
                return pm_action

        return int(rl_action)

    def _check_position_manager(self, current_price: float) -> Optional[int]:
        """
        Check if Position Manager wants to close position.

        Returns:
            2 (SELL) if PM says close, None otherwise
        """
        if not self.position:
            return None

        # Calculate current profit
        if self.position["direction"] == "BUY":
            pips_profit = (current_price - self.position["entry_price"]) / 0.0001
            profit_usd = pips_profit * 10  # Simplified
        else:
            pips_profit = (self.position["entry_price"] - current_price) / 0.0001
            profit_usd = pips_profit * 10

        # Ask Position Manager
        pm_result = self.pm.manage_position(
            position_id=self.position["id"],
            symbol=self.position["symbol"],
            direction=self.position["direction"],
            entry_price=self.position["entry_price"],
            current_price=current_price,
            current_sl=self.position["current_sl"],
            current_profit_usd=profit_usd,
        )

        # Update SL if modified
        if pm_result["action"] == "modify_sl":
            self.position["current_sl"] = pm_result["new_sl"]
            return None

        # Close if PM says so
        if pm_result["action"] == "close":
            self._close_position()
            return 2  # SELL action

        return None

    def open_position(
        self,
        position_id: str,
        symbol: str,
        direction: str,
        entry_price: float,
        initial_sl: float,
    ):
        """Register new position with Position Manager"""
        self.position = {
            "id": position_id,
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry_price,
            "current_sl": initial_sl,
        }

    def _close_position(self):
        """Close current position"""
        if self.position and self.use_pm:
            self.pm.remove_position(self.position["id"])
        self.position = None

    def get_position_status(self) -> Dict:
        """Get current position and PM status"""
        if not self.position:
            return {"has_position": False}

        status = {"has_position": True, "position": self.position}

        if self.use_pm:
            pm_status = self.pm.get_position_status(self.position["id"])
            status["pm_status"] = pm_status

        return status


# Demo
if __name__ == "__main__":
    print("=" * 60)
    print("RL Trading Agent + Position Manager Demo")
    print("=" * 60)
    print()

    # Load agent
    try:
        agent = RLTradingAgent(
            model_path="models/ppo_forex_minimal", use_position_manager=True
        )

        print("\n📊 Agent Configuration:")
        print("   RL Model: PPO")
        print("   Position Manager: Enabled")
        print("   Breakeven: 20 pips")
        print("   Trailing: Starts at 30 pips")

        print("\n✅ Agent ready for backtesting!")
        print("\nNext: Run backtest_rl.py to test performance")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure you've trained the model first:")
        print("   python train_rl_minimal.py")
