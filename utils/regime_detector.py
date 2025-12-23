#!/usr/bin/env python3
"""
Market Regime Detection Module.

Detects whether the market is in a bull, bear, or sideways regime
using various technical indicators and statistical measures.

Regimes:
- BULL: Strong uptrend, buy-and-hold works well
- BEAR: Downtrend, defensive strategies needed
- SIDEWAYS: Range-bound, mean reversion strategies
- VOLATILE: High uncertainty, reduce position sizes
"""

import numpy as np
import pandas as pd
from typing import Tuple, Dict
from enum import Enum


class MarketRegime(Enum):
    """Market regime classification."""

    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"
    VOLATILE = "volatile"


class RegimeDetector:
    """
    Detects market regimes using multiple indicators.

    Combines trend analysis, volatility measures, and momentum
    to classify the current market environment.
    """

    def __init__(
        self,
        sma_short: int = 50,
        sma_long: int = 200,
        volatility_window: int = 20,
        volatility_threshold_high: float = 0.25,
        volatility_threshold_low: float = 0.12,
        trend_threshold: float = 0.02,
        leverage_factor: float = 1.0,  # Set to 3.0 for 3x leveraged ETFs like TQQQ
    ):
        """
        Initialize the regime detector.

        Args:
            sma_short: Short-term moving average period
            sma_long: Long-term moving average period
            volatility_window: Window for volatility calculation
            volatility_threshold_high: Annualized vol above this = volatile
            volatility_threshold_low: Annualized vol below this = calm
            trend_threshold: Minimum trend strength to call bull/bear
            leverage_factor: Multiplier for leveraged ETFs (e.g., 3.0 for TQQQ)
        """
        self.sma_short = sma_short
        self.sma_long = sma_long
        self.volatility_window = volatility_window
        # Scale volatility thresholds for leveraged products
        self.volatility_threshold_high = volatility_threshold_high * leverage_factor
        self.volatility_threshold_low = volatility_threshold_low * leverage_factor
        self.trend_threshold = trend_threshold
        self.leverage_factor = leverage_factor

    def calculate_trend_strength(self, prices: pd.Series) -> float:
        """
        Calculate trend strength using moving average crossover.

        Returns:
            Trend strength: positive = bullish, negative = bearish
        """
        if len(prices) < self.sma_long:
            return 0.0

        sma_short = prices.rolling(self.sma_short).mean()
        sma_long = prices.rolling(self.sma_long).mean()

        # Trend strength as percentage difference between SMAs
        current_short = sma_short.iloc[-1]
        current_long = sma_long.iloc[-1]

        if current_long == 0:
            return 0.0

        trend_strength = (current_short - current_long) / current_long
        return trend_strength

    def calculate_volatility(self, prices: pd.Series) -> float:
        """
        Calculate annualized volatility.

        Returns:
            Annualized volatility as a decimal (e.g., 0.20 = 20%)
        """
        if len(prices) < self.volatility_window + 1:
            return 0.15  # Default moderate volatility

        returns = prices.pct_change().dropna()
        recent_returns = returns.tail(self.volatility_window)

        daily_vol = recent_returns.std()
        annualized_vol = daily_vol * np.sqrt(252)

        return annualized_vol

    def calculate_momentum(self, prices: pd.Series, window: int = 20) -> float:
        """
        Calculate price momentum.

        Returns:
            Momentum as percentage change over window
        """
        if len(prices) < window:
            return 0.0

        current = prices.iloc[-1]
        past = prices.iloc[-window]

        if past == 0:
            return 0.0

        return (current - past) / past

    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
        """Calculate RSI indicator."""
        if len(prices) < period + 1:
            return 50.0

        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain.iloc[-1] / (loss.iloc[-1] + 1e-10)
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def detect_regime(self, prices: pd.Series) -> Tuple[MarketRegime, Dict]:
        """
        Detect the current market regime.

        Args:
            prices: Series of closing prices

        Returns:
            Tuple of (regime, details_dict)
        """
        # Calculate indicators
        trend = self.calculate_trend_strength(prices)
        volatility = self.calculate_volatility(prices)
        momentum = self.calculate_momentum(prices)
        rsi = self.calculate_rsi(prices)

        details = {
            "trend_strength": trend,
            "volatility": volatility,
            "momentum": momentum,
            "rsi": rsi,
        }

        # High volatility overrides other signals
        if volatility > self.volatility_threshold_high:
            return MarketRegime.VOLATILE, details

        # Determine regime based on trend
        if trend > self.trend_threshold:
            # Bullish: price above long-term average with positive momentum
            if momentum > 0 and rsi < 75:
                return MarketRegime.BULL, details
            elif rsi >= 75:
                # Overbought in uptrend - might be topping
                return MarketRegime.VOLATILE, details
            else:
                return MarketRegime.SIDEWAYS, details

        elif trend < -self.trend_threshold:
            # Bearish: price below long-term average
            if momentum < 0 and rsi > 25:
                return MarketRegime.BEAR, details
            elif rsi <= 25:
                # Oversold in downtrend - might be bottoming
                return MarketRegime.VOLATILE, details
            else:
                return MarketRegime.SIDEWAYS, details

        else:
            # No clear trend
            if volatility < self.volatility_threshold_low:
                return MarketRegime.SIDEWAYS, details
            else:
                return MarketRegime.SIDEWAYS, details

    def get_regime_adjustments(self, regime: MarketRegime) -> Dict:
        """
        Get trading parameter adjustments for the current regime.

        Returns:
            Dictionary of suggested parameter adjustments
        """
        adjustments = {
            MarketRegime.BULL: {
                "position_size_multiplier": 1.2,  # Slightly larger positions
                "stop_loss_pct": 0.08,  # Wider stops
                "take_profit_pct": 0.15,  # Let winners run
                "trade_frequency": "normal",
                "bias": "long",
                "description": "Uptrend - favor buying dips, wider stops",
            },
            MarketRegime.BEAR: {
                "position_size_multiplier": 0.5,  # Smaller positions
                "stop_loss_pct": 0.05,  # Tighter stops
                "take_profit_pct": 0.08,  # Take profits quickly
                "trade_frequency": "reduced",
                "bias": "short_or_cash",
                "description": "Downtrend - defensive, quick exits",
            },
            MarketRegime.SIDEWAYS: {
                "position_size_multiplier": 0.8,  # Moderate positions
                "stop_loss_pct": 0.06,  # Standard stops
                "take_profit_pct": 0.10,  # Mean reversion targets
                "trade_frequency": "normal",
                "bias": "neutral",
                "description": "Range-bound - mean reversion strategies",
            },
            MarketRegime.VOLATILE: {
                "position_size_multiplier": 0.3,  # Small positions
                "stop_loss_pct": 0.10,  # Wide stops for volatility
                "take_profit_pct": 0.12,  # Capture big moves
                "trade_frequency": "reduced",
                "bias": "cautious",
                "description": "High volatility - reduce size, be patient",
            },
        }

        return adjustments.get(regime, adjustments[MarketRegime.SIDEWAYS])


def detect_regime_from_df(
    df: pd.DataFrame, price_col: str = "Close"
) -> Tuple[MarketRegime, Dict]:
    """
    Convenience function to detect regime from a DataFrame.

    Args:
        df: DataFrame with price data
        price_col: Name of the price column

    Returns:
        Tuple of (regime, details)
    """
    detector = RegimeDetector()
    prices = df[price_col]
    return detector.detect_regime(prices)


if __name__ == "__main__":
    # Example usage
    import yfinance as yf

    print("📊 Market Regime Detection Demo\n")

    symbols = ["QQQ", "SPY", "AAPL"]
    detector = RegimeDetector()

    for symbol in symbols:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="2y")

        regime, details = detector.detect_regime(df["Close"])
        adjustments = detector.get_regime_adjustments(regime)

        print(f"{'=' * 50}")
        print(f"📈 {symbol}")
        print(f"{'=' * 50}")
        print(f"   Regime: {regime.value.upper()}")
        print(f"   Trend Strength: {details['trend_strength']:.2%}")
        print(f"   Volatility: {details['volatility']:.1%}")
        print(f"   RSI: {details['rsi']:.1f}")
        print(f"   Recommendation: {adjustments['description']}")
        print(f"   Position Size: {adjustments['position_size_multiplier']:.1f}x")
        print()
