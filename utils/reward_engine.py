#!/usr/bin/env python3
"""
Risk-Adjusted AI Reward & Incentive Engine for Forex Trading.
Calculates volatility-normalized, asymmetric drawdown-adjusted reward scores (R_t)
and tracks rolling portfolio Sortino & Efficiency metrics.
"""

import math
import json
from pathlib import Path
from datetime import datetime

class ForexRewardEngine:
    """Computes trade-level risk-adjusted reward scores and rolling performance metrics."""

    def __init__(self, log_dir: Path = None):
        self.log_dir = log_dir or Path("trade_logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = self.log_dir / "reward_history.json"
        self._load_history()

    def _load_history(self):
        """Load historical trade reward scores."""
        self.history = []
        if self.history_file.exists():
            try:
                with open(self.history_file, "r") as f:
                    self.history = json.load(f)
            except Exception:
                pass

    def _save_history(self):
        """Persist trade reward scores to JSON."""
        try:
            with open(self.history_file, "w") as f:
                json.dump(self.history, f, indent=2)
        except Exception as e:
            print(f"⚠️ Failed to save reward history: {e}")

    def calculate_trade_reward(
        self,
        pnl: float,
        duration_hrs: float,
        atr: float = None,
        units: float = 10000.0,
        regime: str = "MEAN_REVERSION"
    ) -> dict:
        """
        Calculate risk-adjusted Reward Score (R_t) for a closed forex trade.
        
        Args:
            pnl: Realized PnL ($)
            duration_hrs: Hold time in hours
            atr: ATR volatility snapshot at entry
            units: Position size
            regime: Entry market regime
            
        Returns:
            Dictionary containing raw reward, components, and efficiency metrics.
        """
        # 1. Volatility-Normalized PnL Incentive
        base_unit = units / 10000.0 if units > 0 else 1.0
        normalized_pnl = pnl / base_unit
        
        if atr and atr > 0:
            vol_normalized_pnl = (normalized_pnl / (atr * 10000.0)) * 10.0
        else:
            vol_normalized_pnl = normalized_pnl / 10.0

        # 2. Asymmetric Loss Penalty (Losses penalize 1.5x heavier than gains reward)
        loss_penalty = 0.0
        if pnl < 0:
            loss_penalty = abs(vol_normalized_pnl) * 0.5  # Add 50% extra penalty for losses

        # 3. Stale Trade Time Decay (Penalizes holding >8 hours)
        time_decay = 0.0
        if duration_hrs > 8.0:
            time_decay = (duration_hrs - 8.0) * 0.25

        # 4. Regime Violation Penalty (Losses during EXTREME_VOLATILITY or counter-trend)
        regime_penalty = 0.0
        if regime == "EXTREME_VOLATILITY" and pnl < 0:
            regime_penalty = 2.0

        # Total Reward Score R_t
        total_reward = vol_normalized_pnl - loss_penalty - time_decay - regime_penalty

        # Efficiency Score: Reward per hour held
        eff_hrs = max(duration_hrs, 0.1)
        efficiency_score = total_reward / eff_hrs

        record = {
            "timestamp": datetime.now().isoformat(),
            "pnl": pnl,
            "duration_hrs": duration_hrs,
            "atr": atr,
            "regime": regime,
            "vol_normalized_pnl": round(vol_normalized_pnl, 4),
            "loss_penalty": round(loss_penalty, 4),
            "time_decay": round(time_decay, 4),
            "regime_penalty": round(regime_penalty, 4),
            "reward_score": round(total_reward, 4),
            "efficiency_score": round(efficiency_score, 4)
        }

        self.history.append(record)
        self._save_history()

        return record

    def calculate_rolling_sortino(self, window: int = 30) -> float:
        """Calculate rolling Sortino Ratio across recent trade rewards."""
        if not self.history:
            return 0.0
            
        recent = self.history[-window:]
        rewards = [r["reward_score"] for r in recent]
        
        mean_reward = sum(rewards) / len(rewards)
        downside_diffs = [min(0.0, r)**2 for r in rewards]
        downside_dev = math.sqrt(sum(downside_diffs) / len(rewards)) if rewards else 0.0
        
        if downside_dev == 0.0:
            return round(mean_reward * 2.0, 2) if mean_reward > 0 else 0.0
            
        return round(mean_reward / downside_dev, 2)

if __name__ == "__main__":
    engine = ForexRewardEngine()
    test_res = engine.calculate_trade_reward(pnl=45.50, duration_hrs=2.5, atr=0.0015, units=10000, regime="MEAN_REVERSION")
    print("Test Reward Calculation:", test_res)
    print("Rolling Sortino:", engine.calculate_rolling_sortino())
