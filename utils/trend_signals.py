"""
Trend-Following Sell Signals Module.

Generates explicit sell signals based on technical analysis to
counteract the BUY-biased models.
"""

import pandas as pd
import numpy as np
from typing import Tuple, Dict, List


class TrendSignals:
    """
    Generates trend-following sell signals.

    Signals:
    - Death Cross: 50-day SMA crosses below 200-day SMA
    - Golden Cross: 50-day SMA crosses above 200-day SMA
    - Momentum Reversal: 20-day momentum turns negative
    - Support Breakdown: Price breaks below key support
    """

    def __init__(
        self,
        sma_short: int = 50,
        sma_long: int = 200,
        momentum_window: int = 20,
        momentum_threshold: float = -0.05,  # -5%
        breakdown_threshold: float = -0.03,  # -3% below support
    ):
        self.sma_short = sma_short
        self.sma_long = sma_long
        self.momentum_window = momentum_window
        self.momentum_threshold = momentum_threshold
        self.breakdown_threshold = breakdown_threshold

    def calculate_sma(self, prices: pd.Series, window: int) -> pd.Series:
        """Calculate simple moving average."""
        return prices.rolling(window=window, min_periods=1).mean()

    def get_death_cross(self, df: pd.DataFrame) -> Tuple[bool, Dict]:
        """
        Detect death cross (50-day crosses below 200-day).

        Returns:
            Tuple of (is_death_cross, details)
        """
        if len(df) < self.sma_long:
            return (False, {"reason": "Insufficient data"})

        prices = df["Close"]
        sma_short = self.calculate_sma(prices, self.sma_short)
        sma_long = self.calculate_sma(prices, self.sma_long)

        current_short = sma_short.iloc[-1]
        current_long = sma_long.iloc[-1]

        # Check if we just crossed (was above, now below)
        prev_short = sma_short.iloc[-2] if len(sma_short) > 1 else current_short
        prev_long = sma_long.iloc[-2] if len(sma_long) > 1 else current_long

        just_crossed = (prev_short >= prev_long) and (current_short < current_long)
        is_below = current_short < current_long

        details = {
            "sma_short": current_short,
            "sma_long": current_long,
            "spread_pct": (current_short - current_long) / current_long * 100,
            "just_crossed": just_crossed,
        }

        # Death cross if just crossed OR significantly below (bearish confirmation)
        is_death_cross = just_crossed or (is_below and details["spread_pct"] < -2)

        return (is_death_cross, details)

    def get_golden_cross(self, df: pd.DataFrame) -> Tuple[bool, Dict]:
        """
        Detect golden cross (50-day crosses above 200-day).

        Returns:
            Tuple of (is_golden_cross, details)
        """
        if len(df) < self.sma_long:
            return (False, {"reason": "Insufficient data"})

        prices = df["Close"]
        sma_short = self.calculate_sma(prices, self.sma_short)
        sma_long = self.calculate_sma(prices, self.sma_long)

        current_short = sma_short.iloc[-1]
        current_long = sma_long.iloc[-1]

        prev_short = sma_short.iloc[-2] if len(sma_short) > 1 else current_short
        prev_long = sma_long.iloc[-2] if len(sma_long) > 1 else current_long

        just_crossed = (prev_short <= prev_long) and (current_short > current_long)

        details = {
            "sma_short": current_short,
            "sma_long": current_long,
            "spread_pct": (current_short - current_long) / current_long * 100,
        }

        return (just_crossed, details)

    def get_momentum_reversal(self, df: pd.DataFrame) -> Tuple[bool, Dict]:
        """
        Detect momentum reversal (momentum turns negative).

        Returns:
            Tuple of (is_reversal, details)
        """
        if len(df) < self.momentum_window + 5:
            return (False, {"reason": "Insufficient data"})

        prices = df["Close"]
        current_price = prices.iloc[-1]
        past_price = prices.iloc[-self.momentum_window]

        momentum = (current_price - past_price) / past_price

        # Check if momentum was positive recently but is now negative
        prev_momentum = (
            prices.iloc[-2] - prices.iloc[-self.momentum_window - 1]
        ) / prices.iloc[-self.momentum_window - 1]

        just_turned_negative = (prev_momentum >= 0) and (momentum < 0)
        is_strongly_negative = momentum < self.momentum_threshold

        details = {
            "momentum": momentum,
            "prev_momentum": prev_momentum,
            "threshold": self.momentum_threshold,
        }

        # Signal if just turned negative OR strongly negative
        is_reversal = just_turned_negative or is_strongly_negative

        return (is_reversal, details)

    def get_breakdown(self, df: pd.DataFrame, window: int = 20) -> Tuple[bool, Dict]:
        """
        Detect support breakdown (price breaks below recent low).

        Returns:
            Tuple of (is_breakdown, details)
        """
        if len(df) < window + 5:
            return (False, {"reason": "Insufficient data"})

        prices = df["Close"]
        current_price = prices.iloc[-1]

        # Support = lowest low in lookback period (excluding last 3 candles)
        lookback = df["Low"].iloc[-window - 3 : -3]
        support = lookback.min()

        # Breakdown = current price below support by threshold
        breakdown_level = support * (1 + self.breakdown_threshold)
        is_breakdown = current_price < breakdown_level

        details = {
            "current_price": current_price,
            "support": support,
            "breakdown_level": breakdown_level,
            "below_support_pct": (current_price - support) / support * 100,
        }

        return (is_breakdown, details)

    def should_force_sell(
        self, df: pd.DataFrame, current_position: bool = True
    ) -> Tuple[bool, str, Dict]:
        """
        Check all sell signals and determine if forced sell is needed.
        Only triggers on STRONG signals to avoid over-trading.

        Args:
            df: DataFrame with OHLCV data
            current_position: Whether we currently have a position

        Returns:
            Tuple of (should_sell, reason, details)
        """
        if not current_position:
            return (False, "No position", {})

        all_details = {}

        # Check death cross - ONLY if significantly below (5%+ spread)
        is_death, death_details = self.get_death_cross(df)
        all_details["death_cross"] = death_details
        if is_death and death_details.get("spread_pct", 0) < -5:
            return (True, "Strong death cross (5%+ below)", all_details)

        # Check momentum reversal - ONLY if strongly negative (-10%)
        is_reversal, mom_details = self.get_momentum_reversal(df)
        all_details["momentum"] = mom_details
        if mom_details.get("momentum", 0) < -0.10:  # -10% momentum
            return (True, "Strong momentum reversal (-10%)", all_details)

        # Skip breakdown check - too noisy for daily data
        # is_breakdown, break_details = self.get_breakdown(df)

        return (False, "No strong sell signal", all_details)

    def should_force_buy(self, df: pd.DataFrame) -> Tuple[bool, str, Dict]:
        """
        Check for strong buy signals (golden cross, momentum positive).

        Returns:
            Tuple of (should_buy, reason, details)
        """
        all_details = {}

        # Check golden cross
        is_golden, golden_details = self.get_golden_cross(df)
        all_details["golden_cross"] = golden_details
        if is_golden:
            return (True, "Golden cross detected", all_details)

        return (False, "No strong buy signal", all_details)


# Convenience function
def get_trend_signals(
    sma_short: int = 50,
    sma_long: int = 200,
) -> TrendSignals:
    """Factory function to create TrendSignals instance."""
    return TrendSignals(sma_short=sma_short, sma_long=sma_long)


if __name__ == "__main__":
    import yfinance as yf

    print("📊 Trend Signals Demo\n")

    # Get data
    ticker = yf.Ticker("QQQ")
    df = ticker.history(period="2y")

    signals = TrendSignals()

    # Check signals
    death, death_d = signals.get_death_cross(df)
    print(f"Death Cross: {death}")
    print(f"  SMA 50: ${death_d.get('sma_short', 0):.2f}")
    print(f"  SMA 200: ${death_d.get('sma_long', 0):.2f}")
    print(f"  Spread: {death_d.get('spread_pct', 0):.2f}%")

    print()

    mom, mom_d = signals.get_momentum_reversal(df)
    print(f"Momentum Reversal: {mom}")
    print(f"  Momentum: {mom_d.get('momentum', 0):.2%}")

    print()

    should_sell, reason, details = signals.should_force_sell(df)
    print(f"Force Sell: {should_sell}")
    print(f"  Reason: {reason}")
