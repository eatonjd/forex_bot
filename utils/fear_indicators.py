"""
Fear Indicators Module for Backtesting.

Provides historical VIX data and sentiment signals to improve
bear market performance in backtests.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Tuple, Dict, Optional


class FearIndicators:
    """
    Tracks market fear indicators for defensive trading.

    VIX Levels:
    - < 15: Low fear (complacent)
    - 15-25: Normal
    - 25-35: Elevated fear
    - > 35: Extreme fear (panic)

    VIX Term Structure:
    - Contango (VIX < VIX3M): Normal, complacent
    - Backwardation (VIX > VIX3M): Fear, hedging demand
    """

    # VIX thresholds - MORE AGGRESSIVE for bear market protection
    VIX_LOW = 15
    VIX_ELEVATED = 20  # Base threshold - scaled by leverage_factor
    VIX_EXTREME = 30  # Base threshold - scaled by leverage_factor

    def __init__(
        self, start_date: str, end_date: str = None, leverage_factor: float = 1.0
    ):
        """
        Initialize and download VIX data.

        Args:
            start_date: Start date for VIX data
            end_date: End date (defaults to today)
            leverage_factor: Multiplier for leveraged ETFs (e.g., 3.0 for TQQQ)
                           Higher leverage = higher VIX thresholds (less defensive)
        """
        self.start_date = start_date
        self.end_date = end_date or datetime.now().strftime("%Y-%m-%d")
        self.leverage_factor = leverage_factor

        # Scale VIX thresholds for leveraged products (1.0 to 1.5x)
        # 3x ETF uses 1.25x multiplier: VIX 20 -> 25, VIX 30 -> 37.5
        threshold_multiplier = 1.0 + (leverage_factor - 1.0) * 0.10
        self.vix_elevated = self.VIX_ELEVATED * threshold_multiplier
        self.vix_extreme = self.VIX_EXTREME * threshold_multiplier

        # Download VIX data
        self.vix_data = self._download_vix()
        self.vix3m_data = self._download_vix3m()

    def _download_vix(self) -> pd.DataFrame:
        """Download historical VIX data."""
        try:
            vix = yf.Ticker("^VIX")
            df = vix.history(start=self.start_date, end=self.end_date)
            if df.empty:
                print("⚠️ VIX data unavailable, using default values")
                return pd.DataFrame()

            # Handle timezone
            if hasattr(df.index, "tz") and df.index.tz is not None:
                df.index = df.index.tz_localize(None)

            return df
        except Exception as e:
            print(f"⚠️ Error downloading VIX: {e}")
            return pd.DataFrame()

    def _download_vix3m(self) -> pd.DataFrame:
        """Download 3-month VIX data for term structure."""
        try:
            vix3m = yf.Ticker("^VIX3M")
            df = vix3m.history(start=self.start_date, end=self.end_date)
            if hasattr(df.index, "tz") and df.index.tz is not None:
                df.index = df.index.tz_localize(None)
            return df
        except Exception as e:
            print(f"⚠️ VIX3M unavailable: {e}")
            return pd.DataFrame()

    def get_vix_level(self, date: datetime) -> float:
        """
        Get VIX level for a specific date.

        Args:
            date: Date to look up

        Returns:
            VIX close value, or 20.0 (normal) if unavailable
        """
        if self.vix_data.empty:
            return 20.0  # Default normal VIX

        # Normalize date
        if hasattr(date, "date"):
            date = date.date()

        # Find closest date
        try:
            # Try exact match first
            if date in self.vix_data.index:
                return float(self.vix_data.loc[date, "Close"])

            # Find closest prior date
            prior_dates = self.vix_data.index[self.vix_data.index <= pd.Timestamp(date)]
            if len(prior_dates) > 0:
                closest = prior_dates[-1]
                return float(self.vix_data.loc[closest, "Close"])
        except:
            pass

        return 20.0  # Default

    def get_vix_regime(self, vix: float) -> str:
        """
        Classify VIX level into regime.

        Args:
            vix: VIX value

        Returns:
            "low", "normal", "elevated", or "extreme"
        """
        if vix < self.VIX_LOW:
            return "low"
        elif vix < self.VIX_ELEVATED:
            return "normal"
        elif vix < self.VIX_EXTREME:
            return "elevated"
        else:
            return "extreme"

    def get_term_structure(self, date: datetime) -> Tuple[float, str]:
        """
        Get VIX term structure (VIX vs VIX3M).

        Returns:
            Tuple of (ratio, structure_type)
            - ratio: VIX / VIX3M
            - structure_type: "contango" or "backwardation"
        """
        if self.vix_data.empty or self.vix3m_data.empty:
            return (1.0, "contango")  # Default to normal

        try:
            vix = self.get_vix_level(date)

            # Get VIX3M
            if hasattr(date, "date"):
                date = date.date()

            prior_dates = self.vix3m_data.index[
                self.vix3m_data.index <= pd.Timestamp(date)
            ]
            if len(prior_dates) > 0:
                vix3m = float(self.vix3m_data.loc[prior_dates[-1], "Close"])
            else:
                vix3m = vix * 1.1  # Default assumption

            ratio = vix / vix3m if vix3m > 0 else 1.0
            structure = "backwardation" if ratio > 1.0 else "contango"

            return (ratio, structure)
        except:
            return (1.0, "contango")

    def get_sentiment_signal(self, date: datetime) -> float:
        """
        Get composite sentiment signal.

        Returns:
            Float from -1 (extreme fear) to +1 (complacent)
        """
        vix = self.get_vix_level(date)
        ratio, structure = self.get_term_structure(date)

        # VIX component (-1 to +1)
        if vix < 15:
            vix_signal = 0.5  # Complacent
        elif vix < 20:
            vix_signal = 0.25
        elif vix < 25:
            vix_signal = 0.0
        elif vix < 35:
            vix_signal = -0.5
        else:
            vix_signal = -1.0  # Extreme fear

        # Term structure component
        if structure == "backwardation":
            structure_signal = -0.3  # Fear
        else:
            structure_signal = 0.1  # Normal

        # Composite
        return max(-1.0, min(1.0, vix_signal + structure_signal))

    def should_be_defensive(self, date: datetime) -> Tuple[bool, str]:
        """
        Determine if defensive mode should be active.
        Uses leverage-adjusted thresholds.

        Returns:
            Tuple of (is_defensive, reason)
        """
        vix = self.get_vix_level(date)
        ratio, structure = self.get_term_structure(date)

        # Use instance-level scaled thresholds
        if vix >= self.vix_extreme:
            return (True, f"VIX extreme ({vix:.1f} >= {self.vix_extreme:.0f})")

        if vix >= self.vix_elevated:
            return (True, f"VIX elevated ({vix:.1f} >= {self.vix_elevated:.0f})")

        if structure == "backwardation" and ratio > 1.1:
            return (True, f"Term structure inverted ({ratio:.2f})")

        return (False, "Normal conditions")


def get_fear_indicators(start_date: str, end_date: str = None) -> FearIndicators:
    """Factory function to create FearIndicators instance."""
    return FearIndicators(start_date, end_date)


if __name__ == "__main__":
    # Demo
    print("📊 Fear Indicators Demo\n")

    fi = FearIndicators("2022-01-01", "2023-01-01")

    test_dates = [
        datetime(2022, 1, 15),  # Normal
        datetime(2022, 3, 7),  # Ukraine war spike
        datetime(2022, 6, 15),  # Bear market
        datetime(2022, 10, 15),  # Peak fear
    ]

    for date in test_dates:
        vix = fi.get_vix_level(date)
        regime = fi.get_vix_regime(vix)
        sentiment = fi.get_sentiment_signal(date)
        defensive, reason = fi.should_be_defensive(date)

        print(
            f"{date.date()}: VIX={vix:.1f} ({regime}) Sentiment={sentiment:.2f} Defensive={defensive}"
        )
