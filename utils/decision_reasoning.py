#!/usr/bin/env python3
"""
Decision Reasoning System for Trading Bot.

Generates human-readable explanations for each trading decision,
mimicking an LLM-style analysis without API costs.

Inspired by the TradingAgents multi-agent framework.

Usage:
    from utils.decision_reasoning import DecisionReasoner

    reasoner = DecisionReasoner()
    decision = reasoner.analyze_and_decide(
        model_votes={"QQQ_Bull": 1, "QQQ_Bear": 0, ...},
        regime="bull",
        sentiment=0.3,
        indicators={"rsi": 55, "macd": 2.5, ...},
        price=520.50,
        portfolio_value=5000,
        current_position=0
    )
    print(decision["reasoning"])  # Human-readable explanation
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class TradingAction(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class MarketAnalysis:
    """Analysis from the Market Analyst agent."""

    trend: str  # bullish, bearish, neutral
    strength: str  # strong, moderate, weak
    rsi_signal: str  # oversold, overbought, neutral
    macd_signal: str  # bullish, bearish, neutral
    sma_signal: str  # above, below, crossing
    volatility: str  # low, normal, high
    summary: str


@dataclass
class SentimentAnalysis:
    """Analysis from the News/Sentiment Analyst agent."""

    score: float  # -1 to 1
    interpretation: str  # very_negative, negative, neutral, positive, very_positive
    summary: str


@dataclass
class RiskAssessment:
    """Assessment from the Risk Manager agent."""

    position_size_ok: bool
    max_loss_ok: bool
    regime_appropriate: bool
    warnings: List[str]
    approved: bool
    summary: str


@dataclass
class TradingDecision:
    """Final decision with full reasoning."""

    action: TradingAction
    confidence: float
    reasoning: str
    market_analysis: MarketAnalysis
    sentiment_analysis: SentimentAnalysis
    risk_assessment: RiskAssessment
    model_consensus: str
    timestamp: str


class MarketAnalystAgent:
    """Analyzes technical indicators and market conditions."""

    def analyze(self, indicators: Dict[str, float], regime: str) -> MarketAnalysis:
        """
        Analyze market conditions from indicators.

        Args:
            indicators: Dict with rsi, macd, sma_20, sma_50, etc.
            regime: Current market regime (bull/bear/sideways/volatile)

        Returns:
            MarketAnalysis with trend assessment
        """
        rsi = indicators.get("rsi", 50)
        macd = indicators.get("macd", 0)
        sma_20 = indicators.get("sma_20", 0)
        sma_50 = indicators.get("sma_50", 0)
        price = indicators.get("price", sma_20)

        # RSI Analysis
        if rsi < 30:
            rsi_signal = "oversold"
            rsi_text = (
                f"RSI at {rsi:.1f} indicates oversold conditions (potential bounce)"
            )
        elif rsi > 70:
            rsi_signal = "overbought"
            rsi_text = (
                f"RSI at {rsi:.1f} indicates overbought conditions (potential pullback)"
            )
        else:
            rsi_signal = "neutral"
            rsi_text = f"RSI at {rsi:.1f} is in neutral territory"

        # MACD Analysis
        if macd > 0.5:
            macd_signal = "bullish"
            macd_text = f"MACD positive ({macd:.2f}) showing bullish momentum"
        elif macd < -0.5:
            macd_signal = "bearish"
            macd_text = f"MACD negative ({macd:.2f}) showing bearish momentum"
        else:
            macd_signal = "neutral"
            macd_text = f"MACD near zero ({macd:.2f}) showing indecision"

        # SMA Analysis
        if sma_20 > 0 and sma_50 > 0:
            if price > sma_20 > sma_50:
                sma_signal = "above"
                sma_text = "Price above both SMAs - uptrend confirmed"
            elif price < sma_20 < sma_50:
                sma_signal = "below"
                sma_text = "Price below both SMAs - downtrend confirmed"
            else:
                sma_signal = "crossing"
                sma_text = "SMAs crossing - potential trend change"
        else:
            sma_signal = "neutral"
            sma_text = "SMA data unavailable"

        # Overall Trend
        bullish_signals = sum(
            [
                rsi_signal == "oversold",
                macd_signal == "bullish",
                sma_signal == "above",
                regime in ["bull", "sideways"],
            ]
        )

        bearish_signals = sum(
            [
                rsi_signal == "overbought",
                macd_signal == "bearish",
                sma_signal == "below",
                regime in ["bear", "volatile"],
            ]
        )

        if bullish_signals > bearish_signals + 1:
            trend = "bullish"
            strength = "strong" if bullish_signals >= 3 else "moderate"
        elif bearish_signals > bullish_signals + 1:
            trend = "bearish"
            strength = "strong" if bearish_signals >= 3 else "moderate"
        else:
            trend = "neutral"
            strength = "weak"

        # Volatility (based on regime)
        volatility = (
            "high"
            if regime == "volatile"
            else "normal"
            if regime == "sideways"
            else "low"
        )

        summary = (
            f"📊 MARKET ANALYSIS\n"
            f"   Regime: {regime.upper()}\n"
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


class SentimentAnalystAgent:
    """Analyzes news sentiment and market mood."""

    def analyze(self, sentiment_score: float) -> SentimentAnalysis:
        """
        Interpret sentiment score.

        Args:
            sentiment_score: Score from -1 (very negative) to 1 (very positive)

        Returns:
            SentimentAnalysis with interpretation
        """
        if sentiment_score >= 0.5:
            interpretation = "very_positive"
            text = "Strong bullish sentiment in news/social media"
        elif sentiment_score >= 0.2:
            interpretation = "positive"
            text = "Moderately positive market sentiment"
        elif sentiment_score >= -0.2:
            interpretation = "neutral"
            text = "Neutral market sentiment"
        elif sentiment_score >= -0.5:
            interpretation = "negative"
            text = "Moderately negative market sentiment"
        else:
            interpretation = "very_negative"
            text = "Strong bearish sentiment in news/social media"

        emoji = (
            "📰"
            if interpretation in ["positive", "very_positive"]
            else "📉"
            if interpretation in ["negative", "very_negative"]
            else "📄"
        )

        summary = (
            f"{emoji} SENTIMENT ANALYSIS\n"
            f"   Score: {sentiment_score:+.2f}\n"
            f"   Interpretation: {interpretation.replace('_', ' ').upper()}\n"
            f"   • {text}"
        )

        return SentimentAnalysis(
            score=sentiment_score,
            interpretation=interpretation,
            summary=summary,
        )


class RiskManagerAgent:
    """Evaluates risk and approves/vetoes trades."""

    def __init__(
        self,
        max_position_pct: float = 0.25,
        max_daily_loss_pct: float = 0.03,
    ):
        self.max_position_pct = max_position_pct
        self.max_daily_loss_pct = max_daily_loss_pct

    def assess(
        self,
        proposed_action: TradingAction,
        price: float,
        portfolio_value: float,
        current_position: float,
        regime: str,
        confidence: float,
    ) -> RiskAssessment:
        """
        Assess risk of a proposed trade.

        Returns:
            RiskAssessment with approval status
        """
        warnings = []

        # Position size check
        if proposed_action == TradingAction.BUY:
            new_position = current_position + (portfolio_value * 0.1)  # Assume 10% size
            position_pct = new_position / portfolio_value if portfolio_value > 0 else 0
            position_size_ok = position_pct <= self.max_position_pct
            if not position_size_ok:
                warnings.append(
                    f"Position would exceed {self.max_position_pct:.0%} limit"
                )
        else:
            position_size_ok = True

        # Max loss check (simplified)
        max_loss_ok = True
        if regime == "volatile" and proposed_action == TradingAction.BUY:
            warnings.append("Volatile regime - consider reduced position size")

        # Regime appropriateness
        if proposed_action == TradingAction.BUY and regime == "bear":
            regime_appropriate = False
            warnings.append("Buying in bear market - higher risk")
        elif proposed_action == TradingAction.SELL and regime == "bull":
            regime_appropriate = True  # Taking profits in bull is fine
        else:
            regime_appropriate = True

        # Confidence check
        if confidence < 0.5:
            warnings.append(f"Low confidence ({confidence:.0%}) - consider holding")

        # Final approval
        critical_issues = not position_size_ok
        approved = not critical_issues

        status = "✅ APPROVED" if approved else "❌ BLOCKED"

        summary = (
            f"🛡️ RISK ASSESSMENT: {status}\n"
            f"   Position limit: {'✓' if position_size_ok else '✗'}\n"
            f"   Regime appropriate: {'✓' if regime_appropriate else '⚠️'}\n"
            f"   Confidence: {confidence:.0%}"
        )

        if warnings:
            summary += "\n   Warnings:\n" + "\n".join([f"   • {w}" for w in warnings])

        return RiskAssessment(
            position_size_ok=position_size_ok,
            max_loss_ok=max_loss_ok,
            regime_appropriate=regime_appropriate,
            warnings=warnings,
            approved=approved,
            summary=summary,
        )


class StrategyAgent:
    """CIO-like agent that synthesizes all inputs and makes final decision."""

    def decide(
        self,
        model_votes: Dict[str, int],
        market_analysis: MarketAnalysis,
        sentiment_analysis: SentimentAnalysis,
    ) -> tuple[TradingAction, float, str]:
        """
        Make a trading decision based on all inputs.

        Args:
            model_votes: Dict of model_name -> vote (0=hold, 1=buy, 2=sell)
            market_analysis: From MarketAnalystAgent
            sentiment_analysis: From SentimentAnalystAgent

        Returns:
            (action, confidence, model_consensus_summary)
        """
        if not model_votes:
            return TradingAction.HOLD, 0.0, "No model votes available"

        # Count votes
        buy_votes = sum(1 for v in model_votes.values() if v == 1)
        sell_votes = sum(1 for v in model_votes.values() if v == 2)
        hold_votes = sum(1 for v in model_votes.values() if v == 0)
        total_models = len(model_votes)

        # Determine majority
        if buy_votes > sell_votes and buy_votes > hold_votes:
            raw_action = TradingAction.BUY
            vote_ratio = buy_votes / total_models
        elif sell_votes > buy_votes and sell_votes > hold_votes:
            raw_action = TradingAction.SELL
            vote_ratio = sell_votes / total_models
        else:
            raw_action = TradingAction.HOLD
            vote_ratio = hold_votes / total_models

        # Adjust based on market analysis
        confidence = vote_ratio

        if raw_action == TradingAction.BUY:
            if market_analysis.trend == "bullish":
                confidence += 0.1
            elif market_analysis.trend == "bearish":
                confidence -= 0.15

            if sentiment_analysis.interpretation in ["positive", "very_positive"]:
                confidence += 0.05
            elif sentiment_analysis.interpretation in ["negative", "very_negative"]:
                confidence -= 0.1

            # RSI override
            if market_analysis.rsi_signal == "overbought":
                confidence -= 0.15
            elif market_analysis.rsi_signal == "oversold":
                confidence += 0.1

        elif raw_action == TradingAction.SELL:
            if market_analysis.trend == "bearish":
                confidence += 0.1
            elif market_analysis.trend == "bullish":
                confidence -= 0.1

        confidence = max(0.0, min(1.0, confidence))

        # Create consensus summary
        voters_buy = [m for m, v in model_votes.items() if v == 1]
        voters_sell = [m for m, v in model_votes.items() if v == 2]
        voters_hold = [m for m, v in model_votes.items() if v == 0]

        consensus = (
            f"🤖 MODEL CONSENSUS\n"
            f"   BUY: {buy_votes}/{total_models} ({buy_votes / total_models:.0%})"
        )
        if voters_buy:
            consensus += f"\n      → {', '.join(voters_buy[:3])}"

        consensus += (
            f"\n   SELL: {sell_votes}/{total_models} ({sell_votes / total_models:.0%})"
        )
        if voters_sell:
            consensus += f"\n      → {', '.join(voters_sell[:3])}"

        consensus += (
            f"\n   HOLD: {hold_votes}/{total_models} ({hold_votes / total_models:.0%})"
        )

        return raw_action, confidence, consensus


class DecisionReasoner:
    """
    Main decision-making system that coordinates all agents.
    Generates human-readable reasoning for each trading decision.
    """

    def __init__(
        self,
        max_position_pct: float = 0.25,
        min_confidence: float = 0.5,
    ):
        self.market_analyst = MarketAnalystAgent()
        self.sentiment_analyst = SentimentAnalystAgent()
        self.risk_manager = RiskManagerAgent(max_position_pct=max_position_pct)
        self.strategy = StrategyAgent()
        self.min_confidence = min_confidence

    def analyze_and_decide(
        self,
        model_votes: Dict[str, int],
        regime: str,
        sentiment: float,
        indicators: Dict[str, float],
        price: float,
        portfolio_value: float,
        current_position: float = 0,
    ) -> TradingDecision:
        """
        Analyze all inputs and generate a decision with full reasoning.

        Args:
            model_votes: Dict of model_name -> vote (0=hold, 1=buy, 2=sell)
            regime: Market regime (bull/bear/sideways/volatile)
            sentiment: Sentiment score (-1 to 1)
            indicators: Dict with rsi, macd, sma_20, sma_50, etc.
            price: Current price
            portfolio_value: Current portfolio value
            current_position: Current position value

        Returns:
            TradingDecision with full reasoning
        """
        # Add price to indicators if not present
        indicators["price"] = price

        # 1. Market Analyst
        market_analysis = self.market_analyst.analyze(indicators, regime)

        # 2. Sentiment Analyst
        sentiment_analysis = self.sentiment_analyst.analyze(sentiment)

        # 3. Strategy Decision
        action, confidence, model_consensus = self.strategy.decide(
            model_votes, market_analysis, sentiment_analysis
        )

        # 4. Risk Assessment
        risk_assessment = self.risk_manager.assess(
            proposed_action=action,
            price=price,
            portfolio_value=portfolio_value,
            current_position=current_position,
            regime=regime,
            confidence=confidence,
        )

        # 5. Final Decision (may be overridden by risk)
        final_action = action
        if not risk_assessment.approved and action != TradingAction.HOLD:
            final_action = TradingAction.HOLD
            confidence *= 0.5  # Reduce confidence since we're overriding

        if confidence < self.min_confidence and action == TradingAction.BUY:
            final_action = TradingAction.HOLD

        # 6. Generate Full Reasoning
        action_emoji = (
            "🟢"
            if final_action == TradingAction.BUY
            else "🔴"
            if final_action == TradingAction.SELL
            else "⏸️"
        )

        # Enhanced Reasoning Construction
        reasoning = f"""{action_emoji} TRADING DECISION: {final_action.value}
Confidence: {confidence:.0%} | Price: ${price:,.2f} | Time: {datetime.now().strftime("%H:%M:%S")}

{model_consensus}

{market_analysis.summary}

{sentiment_analysis.summary}

{risk_assessment.summary}

📋 DECISION RATIONALE"""

        # Add decision-specific rationale
        if final_action == TradingAction.BUY:
            reasoning += f"""
   ✅ Proceeding with BUY because:
   • Model consensus: {sum(1 for v in model_votes.values() if v == 1)}/{len(model_votes)} bullish
   • Market trend: {market_analysis.trend} ({market_analysis.strength})
   • Risk check: {"PASSED" if risk_assessment.approved else "OVERRIDDEN"}"""
        elif final_action == TradingAction.SELL:
            reasoning += f"""
   🔴 Proceeding with SELL because:
   • Model consensus: {sum(1 for v in model_votes.values() if v == 2)}/{len(model_votes)} bearish
   • Technical breakdown: {market_analysis.trend} trend
   • Risk check: PASSED"""
        else:
            reasons = []
            if confidence < self.min_confidence:
                reasons.append(
                    f"Low confidence ({confidence:.0%} < {self.min_confidence:.0%})"
                )
            if not risk_assessment.approved:
                reasons.append("Risk manager blocked trade")

            reasoning += f"""
   ⏸️ HOLDING because:
   {chr(10).join(["• " + r for r in reasons]) if reasons else "• Waiting for high-confidence setup"}"""

        return TradingDecision(
            action=final_action,
            confidence=confidence,
            reasoning=reasoning,
            market_analysis=market_analysis,
            sentiment_analysis=sentiment_analysis,
            risk_assessment=risk_assessment,
            model_consensus=model_consensus,
            timestamp=datetime.now().isoformat(),
        )


def demo():
    """Demonstrate the decision reasoning system."""
    print("🧠 Decision Reasoning System Demo\n")

    reasoner = DecisionReasoner(max_position_pct=0.25, min_confidence=0.5)

    # Simulate a bullish scenario
    decision = reasoner.analyze_and_decide(
        model_votes={
            "QQQ_Bull": 1,
            "QQQ_Bear": 1,
            "SPY_General": 1,
            "OEF_Conservative": 0,
            "AAPL_Tuned": 1,
            "QQQ_10yr_Sharpe": 1,
            "Multi_Symbol": 1,
        },
        regime="bull",
        sentiment=0.35,
        indicators={
            "rsi": 55,
            "macd": 2.5,
            "sma_20": 515.0,
            "sma_50": 500.0,
        },
        price=520.50,
        portfolio_value=5000.0,
        current_position=0,
    )

    print(decision.reasoning)

    print("\n\n--- BEARISH SCENARIO ---\n")

    # Simulate a bearish scenario
    decision2 = reasoner.analyze_and_decide(
        model_votes={
            "QQQ_Bull": 2,
            "QQQ_Bear": 2,
            "SPY_General": 0,
            "OEF_Conservative": 2,
            "AAPL_Tuned": 2,
            "QQQ_10yr_Sharpe": 0,
            "Multi_Symbol": 2,
        },
        regime="bear",
        sentiment=-0.4,
        indicators={
            "rsi": 72,
            "macd": -1.5,
            "sma_20": 510.0,
            "sma_50": 520.0,
        },
        price=505.00,
        portfolio_value=5000.0,
        current_position=1040.0,
    )

    print(decision2.reasoning)


if __name__ == "__main__":
    demo()
