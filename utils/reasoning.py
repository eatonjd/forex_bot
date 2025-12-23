from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
import numpy as np


@dataclass
class Decision:
    action: int
    reasoning: str


class DecisionReasoner:
    """
    Analyzes market data, model votes, and indicators to generate a human-readable
    explanation for the trading decision.
    """

    def __init__(self, api_key: Optional[str] = None):
        # We rely on rule-based logic for speed and reliability
        pass

    def analyze_and_decide(
        self,
        model_votes: Dict[str, Any],
        regime: str,
        sentiment: float,
        indicators: Dict[str, float],
        price: float,
        portfolio_value: float,
        current_position: float,
    ) -> Decision:
        reasons = []

        # 1. Analyze Market Context
        rsi = indicators.get("rsi", 50)
        macd = indicators.get("macd", 0)
        sma_20 = indicators.get("sma_20", price)
        obv_slope = indicators.get("obv_slope", 0)
        cmf = indicators.get("cmf", 0)

        context_str = f"Market is in '{regime}' regime."
        if rsi > 70:
            context_str += f" RSI is Overbought ({rsi:.1f})."
        elif rsi < 30:
            context_str += f" RSI is Oversold ({rsi:.1f})."

        if price > sma_20:
            context_str += " Price > SMA20 (Trend Up)."
        else:
            context_str += " Price < SMA20 (Trend Down)."

        reasons.append(context_str)

        # 2. Analyze Volume/Microstructure (Volume Expert validation)
        vol_reason = []
        if obv_slope > 0.1:
            vol_reason.append("Strong Buying Pressure (OBV rising).")
        elif obv_slope < -0.1:
            vol_reason.append("Significant Selling Pressure (OBV falling).")

        if cmf > 0.1:
            vol_reason.append("Money Flow Positive.")
        elif cmf < -0.1:
            vol_reason.append("Money Flow Negative.")

        if vol_reason:
            reasons.append("Volume: " + " ".join(vol_reason))
        else:
            reasons.append("Volume: No significant anomaly.")

        # 3. Analyze Model Consensus
        actions = {"HOLD": 0, "BUY": 0, "SELL": 0}
        model_details = []

        for name, vote in model_votes.items():
            # vote is typically (action_int, probabilities)
            if isinstance(vote, (tuple, list)):
                action_idx = vote[0]
            else:
                action_idx = vote

            act_str = ["HOLD", "BUY", "SELL"][action_idx]
            actions[act_str] += 1

            # Highlight special experts
            if "Volume" in name:
                model_details.append(f"{name} votes {act_str}.")
            elif "Sharpe" in name and action_idx != 0:
                model_details.append(f"{name} votes {act_str}.")

        consensus = max(actions, key=actions.get)
        reasons.append(
            f"Model Consensus: {consensus} ({actions['BUY']} Buy, {actions['SELL']} Sell, {actions['HOLD']} Hold)."
        )

        if model_details:
            reasons.append("Key Votes: " + ", ".join(model_details))

        # 4. Final Conclusion
        final_reasoning = "\n".join(reasons)

        # We don't override the ensemble action here, we just explain it.
        # But we must return a Decision object. We assume the ensemble logic upstream determines the final action.
        # The upstream code expects this method to return a Decision, but doesn't USE the action from it?
        # Actually `alpaca_ensemble.py` calls `self.execute_trade(action, ...)` where `action` comes from `self.ensemble.ensemble_predict`.
        # The `decision` variable is only used for `print(decision.reasoning)`.
        # So the action here doesn't matter much, but let's be consistent.

        return Decision(action=0, reasoning=f"\n🧠 REASONING:\n{final_reasoning}")
