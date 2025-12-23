#!/usr/bin/env python3
"""
Decision Reasoning System for Forex Trading Bot.

Generates human-readable explanations for each trading decision,
adapted from trading_bot for forex markets.

Usage:
    from utils.forex_decision_reasoning import ForexDecisionReasoner

    reasoner = ForexDecisionReasoner()
    decision = reasoner.analyze_and_decide(
        rl_action=1,  # 0=HOLD, 1=BUY, 2=SELL
        price=1.17234,
        indicators={"rsi": 55, "macd": 0.0023, ...},
        position_manager_state=None
    )
    print(decision["reasoning"])  # Beautiful human-readable explanation
"""

from dataclasses import dataclass
from typing import Dict, Optional
from datetime import datetime
from enum import Enum


class TradingAction(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class MarketAnalysis:
    """Technical analysis of forex pair."""

    trend: str  # bullish, bearish, neutral
    strength: str  # strong, moderate, weak
    rsi_signal: str  # oversold, overbought, neutral
    macd_signal: str  # bullish, bearish, neutral
    sma_signal: str  # above, below, crossing
    volatility: str  # low, normal, high
    summary: str


@dataclass
class RiskAssessment:
    """Risk evaluation for forex trade."""

    position_ok: bool
    spread_ok: bool
    volatility_ok: bool
    warnings: list
    approved: bool
    summary: str


class ForexMarketAnalyst:
    """Analyzes forex technical indicators."""

    def analyze(self, indicators: Dict[str, float], price: float) -> MarketAnalysis:
        """
        Analyze forex market conditions.

        Args:
            indicators: Technical indicators (RSI, MACD, SMAs, etc.)
            price: Current price

        Returns:
            MarketAnalysis with trend assessment
        """
        rsi = indicators.get("rsi", 50)
        macd = indicators.get("macd", 0)
        sma_20 = indicators.get("sma_20", 0)
        sma_50 = indicators.get("sma_50", 0)
        atr = indicators.get("atr", 0)

        # RSI Analysis
        if rsi < 30:
            rsi_signal = "oversold"
            rsi_text = f"RSI {rsi:.1f} oversold - potential bounce"
        elif rsi > 70:
            rsi_signal = "overbought"
            rsi_text = f"RSI {rsi:.1f} overbought - potential reversal"
        else:
            rsi_signal = "neutral"
            rsi_text = f"RSI {rsi:.1f} neutral"

        # MACD Analysis (forex-adjusted thresholds)
        if macd > 0.0005:
            macd_signal = "bullish"
            macd_text = f"MACD +{macd:.5f} bullish momentum"
        elif macd < -0.0005:
            macd_signal = "bearish"
            macd_text = f"MACD {macd:.5f} bearish momentum"
        else:
            macd_signal = "neutral"
            macd_text = f"MACD {macd:.5f} indecisive"

        # SMA Analysis
        if sma_20 > 0 and sma_50 > 0:
            if price > sma_20 > sma_50:
                sma_signal = "above"
                sma_text = "Price above SMAs - uptrend"
            elif price < sma_20 < sma_50:
                sma_signal = "below"
                sma_text = "Price below SMAs - downtrend"
            else:
                sma_signal = "crossing"
                sma_text = "SMAs crossing - trend change"
        else:
            sma_signal = "neutral"
            sma_text = "SMA data loading..."

        # Overall Trend
        bullish_signals = sum(
            [rsi_signal == "oversold", macd_signal == "bullish", sma_signal == "above"]
        )

        bearish_signals = sum(
            [
                rsi_signal == "overbought",
                macd_signal == "bearish",
                sma_signal == "below",
            ]
        )

        if bullish_signals > bearish_signals + 1:
            trend = "bullish"
            strength = "strong" if bullish_signals >= 2 else "moderate"
        elif bearish_signals > bullish_signals + 1:
            trend = "bearish"
            strength = "strong" if bearish_signals >= 2 else "moderate"
        else:
            trend = "neutral"
            strength = "weak"

        # Volatility (based on ATR)
        if atr > 0:
            atr_pct = (atr / price) * 100
            if atr_pct > 1.0:
                volatility = "high"
            elif atr_pct > 0.5:
                volatility = "normal"
            else:
                volatility = "low"
        else:
            volatility = "normal"

        summary = (
            f"📊 MARKET ANALYSIS\n"
            f"   Trend: {trend.upper()} ({strength})\n"
            f"   • {rsi_text}\n"
            f"   • {macd_text}\n"
            f"   • {sma_text}\n"
            f"   Volatility: {volatility}"
        )

        return MarketAnalysis(
            trend=trend,
            strength=strength,
            rsi_signal=rsi_signal,
            macd_signal=macd_signal,
            sma_signal=sma_signal,
            volatility=volatility,
            summary=summary,
        )


class ForexRiskManager:
    """Evaluates risk for forex trades."""

    def __init__(self, max_spread_pips: float = 3.0):
        self.max_spread_pips = max_spread_pips

    def assess(
        self,
        action: TradingAction,
        price: float,
        spread: Optional[float] = None,
        volatility: str = "normal",
        position_manager_active: bool = False,
    ) -> RiskAssessment:
        """
        Assess risk of proposed forex trade.

        Returns:
            RiskAssessment with approval status
        """
        warnings = []

        # Spread check
        if spread:
            spread_pips = spread / 0.0001
            spread_ok = spread_pips <= self.max_spread_pips
            if not spread_ok:
                warnings.append(
                    f"Wide spread ({spread_pips:.1f} pips > {self.max_spread_pips})"
                )
        else:
            spread_ok = True

        # Volatility check
        volatility_ok = True
        if action == TradingAction.BUY and volatility == "high":
            warnings.append("High volatility - wider stops recommended")
            volatility_ok = False

        # Position Manager integration
        position_ok = True
        if position_manager_active:
            warnings.append("Position Manager active - exits optimized")

        # Final approval
        approved = spread_ok and (volatility_ok or position_manager_active)

        status = "✅ APPROVED" if approved else "⚠️ CAUTION"

        summary = (
            f"🛡️ RISK ASSESSMENT: {status}\n"
            f"   Spread: {'✓' if spread_ok else '✗'}\n"
            f"   Volatility: {volatility}\n"
            f"   Position Mgr: {'✓' if position_manager_active else '○'}"
        )

        if warnings:
            summary += "\n   Notes:\n" + "\n".join([f"   • {w}" for w in warnings])

        return RiskAssessment(
            position_ok=position_ok,
            spread_ok=spread_ok,
            volatility_ok=volatility_ok,
            warnings=warnings,
            approved=approved,
            summary=summary,
        )


class ForexDecisionReasoner:
    """
    Main decision reasoning system for forex trading.
    Generates human-readable explanations for each trade.
    """

    def __init__(self):
        self.market_analyst = ForexMarketAnalyst()
        self.risk_manager = ForexRiskManager()

    def analyze_and_decide(
        self,
        symbol: str,
        rl_action: int,  # 0=HOLD, 1=BUY, 2=SELL
        price: float,
        indicators: Dict[str, float],
        spread: Optional[float] = None,
        position_manager_state: Optional[Dict] = None,
    ) -> Dict:
        """
        Analyze all inputs and generate decision with full reasoning.

        Args:
            symbol: Forex pair (e.g., "EUR_USD")
            rl_action: RL model action (0=HOLD, 1=BUY, 2=SELL)
            price: Current price
            indicators: Technical indicators dict
            spread: Bid-ask spread (optional)
            position_manager_state: PM state if active

        Returns:
            Dict with action, reasoning, confidence
        """
        # Convert action
        if rl_action == 1:
            action = TradingAction.BUY
        elif rl_action == 2:
            action = TradingAction.SELL
        else:
            action = TradingAction.HOLD

        # Market Analysis
        market_analysis = self.market_analyst.analyze(indicators, price)

        # Risk Assessment
        pm_active = position_manager_state is not None
        risk_assessment = self.risk_manager.assess(
            action=action,
            price=price,
            spread=spread,
            volatility=market_analysis.volatility,
            position_manager_active=pm_active,
        )

        # Calculate confidence
        confidence = 0.7  # Base RL confidence

        if action == TradingAction.BUY:
            if market_analysis.trend == "bullish":
                confidence += 0.15
            elif market_analysis.trend == "bearish":
                confidence -= 0.2

            if market_analysis.rsi_signal == "oversold":
                confidence += 0.1
            elif market_analysis.rsi_signal == "overbought":
                confidence -= 0.15

        confidence = max(0.0, min(1.0, confidence))

        # Generate reasoning
        action_emoji = {
            TradingAction.BUY: "🟢",
            TradingAction.SELL: "🔴",
            TradingAction.HOLD: "⏸️",
        }

        reasoning = f"""{action_emoji[action]} FOREX TRADING DECISION: {action.value}
{symbol} | Confidence: {confidence:.0%} | Price: {price:.5f} | {datetime.now().strftime("%H:%M:%S")}

🤖 RL MODEL ANALYSIS
   Action: {action.value}
   Model: PPO (100K timesteps, improved reward)
   Strategy: Breakeven + Trailing Stops

{market_analysis.summary}

{risk_assessment.summary}

📋 DECISION RATIONALE"""

        if action == TradingAction.BUY:
            reasoning += f"""
   ✅ EXECUTING BUY because:
   • RL model signals entry opportunity
   • Market trend: {market_analysis.trend} ({market_analysis.strength})
   • Technical setup: {market_analysis.rsi_signal} RSI, {market_analysis.macd_signal} MACD
   • Risk check: {"PASSED" if risk_assessment.approved else "MONITORING"}
   • Position Manager: {"ACTIVE (exits optimized)" if pm_active else "READY"}"""
        elif action == TradingAction.SELL:
            reasoning += f"""
   🔴 EXECUTING SELL because:
   • RL model signals exit/short
   • Technical breakdown: {market_analysis.trend} trend
   • Exit optimization: Position Manager active"""
        else:
            # Enhanced HOLD reasoning - explain WHY we didn't enter
            hold_reasons = []

            # Check confidence threshold
            if confidence < 0.7:
                hold_reasons.append(f"Confidence too low ({confidence:.0%} < 70%)")

            # Check market conditions
            if market_analysis.trend == "neutral":
                hold_reasons.append("No clear trend direction")
            elif market_analysis.strength == "weak":
                hold_reasons.append(f"Weak {market_analysis.trend} signal")

            # Check technical indicators
            if market_analysis.rsi_signal == "overbought":
                hold_reasons.append("RSI overbought - waiting for pullback")
            elif (
                market_analysis.rsi_signal == "neutral"
                and market_analysis.macd_signal == "neutral"
            ):
                hold_reasons.append("Technical indicators indecisive")

            # Check risk factors
            if not risk_assessment.approved:
                hold_reasons.append("Risk check failed")
                if not risk_assessment.spread_ok:
                    hold_reasons.append("  └─ Spread too wide")
                if not risk_assessment.volatility_ok:
                    hold_reasons.append("  └─ Volatility too high")

            # If no specific reasons, general monitoring
            if not hold_reasons:
                hold_reasons.append("RL model recommends patience")
                hold_reasons.append("Monitoring for stronger setup")

            reasons_text = "\n   • ".join(hold_reasons)

            reasoning += f"""
   ⏸️ HOLDING - No Entry because:
   • {reasons_text}
   
   📌 Watching for:
   • Stronger trend confirmation ({market_analysis.trend} → bullish/bearish)
   • Higher confidence signal (need ≥70%)
   • Better technical alignment (RSI + MACD + SMA)"""

        return {
            "action": action.value,
            "confidence": confidence,
            "reasoning": reasoning,
            "market_analysis": market_analysis,
            "risk_assessment": risk_assessment,
            "timestamp": datetime.now().isoformat(),
        }


if __name__ == "__main__":
    # Demo
    print("🧠 Forex Decision Reasoning Demo\n")

    reasoner = ForexDecisionReasoner()

    decision = reasoner.analyze_and_decide(
        symbol="EUR_USD",
        rl_action=1,  # BUY
        price=1.17234,
        indicators={
            "rsi": 45.2,
            "macd": 0.00234,
            "sma_20": 1.17100,
            "sma_50": 1.16900,
            "atr": 0.00089,
        },
        spread=0.00015,
        position_manager_state={"active": True},
    )

    print(decision["reasoning"])
