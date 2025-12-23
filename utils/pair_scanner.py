"""
Forex Pair Scanner

Scans multiple forex pairs to identify best trading opportunities.
Ranks pairs by spread, volatility, trend strength, and model confidence.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
import numpy as np


@dataclass
class PairScore:
    """Scoring for a forex pair"""

    symbol: str
    total_score: float
    spread_score: float
    volatility_score: float
    trend_score: float
    technical_score: float
    confidence_score: float
    details: Dict


class ForexPairScanner:
    """
    Scan and rank forex pairs for trading opportunities
    """

    # Major forex pairs to scan
    MAJOR_PAIRS = [
        "EUR_USD",
        "GBP_USD",
        "USD_JPY",
        "AUD_USD",
        "NZD_USD",
        "EUR_GBP",
        "EUR_JPY",
        "USD_CAD",
        "USD_CHF",
    ]

    def __init__(self, oanda_connector, rl_model, reasoner):
        """
        Initialize scanner

        Args:
            oanda_connector: OANDAConnector instance
            rl_model: Loaded RL model for predictions
            reasoner: ForexDecisionReasoner instance
        """
        self.oanda = oanda_connector
        self.model = rl_model
        self.reasoner = reasoner

    def score_pair(
        self, symbol: str, price_data: Dict, indicators: Dict, signal: int
    ) -> Optional[PairScore]:
        """
        Score a single pair across multiple criteria

        Returns:
            PairScore or None if pair cannot be scored
        """
        try:
            # 1. Spread score (lower is better)
            spread_raw = price_data.get("spread", 0.001)
            # Convert to pips: JPY pairs use 0.01, others use 0.0001
            pip_size = 0.01 if "JPY" in symbol else 0.0001
            spread_pips = spread_raw / pip_size

            if spread_pips <= 1.5:
                spread_score = 10.0
            elif spread_pips <= 2.5:
                spread_score = 8.0
            elif spread_pips <= 3.0:
                spread_score = 6.0
            else:
                spread_score = max(
                    0, 10 - (spread_pips - 3) * 2
                )  # Penalize wide spreads

            # 2. Volatility score (moderate is best)
            atr = indicators.get("atr", 0)
            if 0.0010 <= atr <= 0.0030:  # Ideal range
                volatility_score = 10.0
            elif atr < 0.0005:  # Too low
                volatility_score = 4.0
            elif atr > 0.0050:  # Too high
                volatility_score = 5.0
            else:
                volatility_score = 7.0

            # 3. Trend score (strong trend is better)
            sma_20 = indicators.get("sma_20", 0)
            sma_50 = indicators.get("sma_50", 0)
            current_price = price_data.get("bid", 0)

            if sma_20 > sma_50 and current_price > sma_20:
                trend_score = 10.0  # Strong uptrend
            elif sma_20 < sma_50 and current_price < sma_20:
                trend_score = 10.0  # Strong downtrend
            elif abs(sma_20 - sma_50) / sma_50 < 0.001:
                trend_score = 3.0  # Very weak/neutral
            else:
                trend_score = 6.0  # Moderate trend

            # 4. Technical score (RSI + MACD alignment)
            rsi = indicators.get("rsi", 50)
            macd = indicators.get("macd", 0)
            macd_signal = indicators.get("macd_signal", 0)

            technical_score = 5.0  # Base score

            # RSI not overbought/oversold
            if 40 <= rsi <= 60:
                technical_score += 2.0
            elif 30 <= rsi <= 70:
                technical_score += 1.0

            # MACD momentum
            if macd > macd_signal and macd > 0:
                technical_score += 3.0  # Bullish momentum
            elif macd < macd_signal and macd < 0:
                technical_score += 3.0  # Bearish momentum
            else:
                technical_score += 1.0

            # 5. Model confidence score
            # Simple trend detection based on SMAs
            if sma_20 > sma_50 and current_price > sma_20:
                trend = "bullish"
                strength = (
                    "strong" if abs(sma_20 - sma_50) / sma_50 > 0.002 else "moderate"
                )
            elif sma_20 < sma_50 and current_price < sma_20:
                trend = "bearish"
                strength = (
                    "strong" if abs(sma_20 - sma_50) / sma_50 > 0.002 else "moderate"
                )
            else:
                trend = "neutral"
                strength = "weak"

            if signal == 1:  # BUY signal
                confidence_score = (
                    10.0 if trend == "bullish" and strength == "strong" else 7.0
                )
            elif signal == 2:  # SELL signal
                confidence_score = (
                    10.0 if trend == "bearish" and strength == "strong" else 7.0
                )
            else:  # HOLD
                confidence_score = 3.0

            # Calculate total score (weighted average)
            weights = {
                "spread": 0.25,
                "volatility": 0.15,
                "trend": 0.25,
                "technical": 0.20,
                "confidence": 0.15,
            }

            total_score = (
                spread_score * weights["spread"]
                + volatility_score * weights["volatility"]
                + trend_score * weights["trend"]
                + technical_score * weights["technical"]
                + confidence_score * weights["confidence"]
            )

            return PairScore(
                symbol=symbol,
                total_score=round(total_score, 2),
                spread_score=round(spread_score, 1),
                volatility_score=round(volatility_score, 1),
                trend_score=round(trend_score, 1),
                technical_score=round(technical_score, 1),
                confidence_score=round(confidence_score, 1),
                details={
                    "spread_pips": round(spread_pips, 1),
                    "atr": round(atr, 5),
                    "trend": trend,
                    "rsi": round(rsi, 1),
                    "macd": round(macd, 5),
                },
            )

        except Exception as e:
            print(f"⚠️  Error scoring {symbol}: {e}")
            return None

    def scan_pairs(
        self, current_symbols: List[str] = None, top_n: int = 2
    ) -> List[PairScore]:
        """
        Scan all major pairs and return top ranked pairs

        Args:
            current_symbols: Currently trading symbols (to potentially keep)
            top_n: Number of top pairs to return

        Returns:
            List of top PairScore objects
        """
        print(f"\n🔍 Scanning {len(self.MAJOR_PAIRS)} major forex pairs...")

        scores = []

        for symbol in self.MAJOR_PAIRS:
            try:
                # Get price data
                price_data = self.oanda.get_current_price(symbol)
                if not price_data:
                    continue

                # Get candles for indicators
                candles = self.oanda.get_candles(symbol, granularity="H1", count=100)
                if not candles:
                    continue

                # Calculate indicators (simplified - use your feature engineering)
                from utils.feature_engineering import add_all_features
                import pandas as pd

                df = pd.DataFrame(candles)

                # Rename columns to match feature engineering expectations
                df = df.rename(
                    columns={
                        "time": "time",
                        "open": "Open",
                        "high": "High",
                        "low": "Low",
                        "close": "Close",
                        "volume": "Volume",
                    }
                )

                df = add_all_features(df)

                if df.empty:
                    continue

                latest = df.iloc[-1]
                indicators = {
                    "rsi": latest.get("rsi", 50),
                    "macd": latest.get("macd", 0),
                    "macd_signal": latest.get("macd_signal", 0),
                    "sma_20": latest.get("sma_20", 0),
                    "sma_50": latest.get("sma_50", 0),
                    "atr": latest.get("atr", 0),
                }

                # Get model prediction - match bot's feature preparation
                # Drop OHLCV columns
                feature_cols = [
                    c
                    for c in df.columns
                    if c not in ["time", "Open", "High", "Low", "Close", "Volume"]
                ]
                features = df[feature_cols].iloc[-1].values.astype(np.float32)

                # Add account features (simplified - same as bot)
                account_features = np.array([1.0, 0.0, 1.0, 0.0], dtype=np.float32)
                obs = np.concatenate([features, account_features])

                # Predict
                signal, _ = self.model.predict(obs, deterministic=True)
                signal = int(signal)

                # Score the pair
                score = self.score_pair(symbol, price_data, indicators, signal)
                if score:
                    scores.append(score)

            except Exception as e:
                print(f"⚠️  Error scanning {symbol}: {e}")
                continue

        # Sort by total score
        scores.sort(key=lambda x: x.total_score, reverse=True)

        return scores[:top_n]

    def should_switch_pairs(
        self, iterations_without_buy: int, threshold: int = 24
    ) -> bool:
        """
        Determine if pairs should be switched

        Args:
            iterations_without_buy: Number of iterations since last buy signal
            threshold: Threshold to trigger switch (default 24 = 2 hours)

        Returns:
            True if should switch pairs
        """
        return iterations_without_buy >= threshold

    def print_scan_results(self, scores: List[PairScore]):
        """Print formatted scan results"""
        print(f"\n📊 Top Ranked Pairs:")
        print("=" * 60)

        for i, score in enumerate(scores, 1):
            print(f"\n{i}. {score.symbol} - Score: {score.total_score}/10")
            print(
                f"   • Spread: {score.details['spread_pips']} pips (score: {score.spread_score}/10)"
            )
            print(
                f"   • Trend: {score.details['trend']} (score: {score.trend_score}/10)"
            )
            print(
                f"   • Volatility: {score.details['atr']:.5f} (score: {score.volatility_score}/10)"
            )
            print(
                f"   • Technical: RSI {score.details['rsi']}, MACD {score.details['macd']:.5f} (score: {score.technical_score}/10)"
            )

        print("=" * 60)
