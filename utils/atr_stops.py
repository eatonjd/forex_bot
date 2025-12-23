#!/usr/bin/env python3
"""
ATR-Based Stop Loss and Take Profit Calculator

Implements volatility-adaptive stops using Average True Range (ATR).
Based on Bot-ForexMT5's dynamic stop/TP system.

Benefits:
- Adapts to market volatility automatically
- Wider stops in volatile markets (reduce whipsaws)
- Tighter stops in calm markets (protect profits)
- Dynamic risk/reward ratios

Formulas:
- ATR = Average of True Range over N periods
- True Range = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
- Stop Loss = Entry ± (ATR × Multiplier)
- Take Profit = Entry ± (ATR × RR_Ratio × Multiplier)

Author: Forex Bot Team
Created: 2025-12-18
"""

import numpy as np
import pandas as pd
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class ATRStopCalculator:
    """
    Calculate dynamic stop loss and take profit using ATR.

    ATR (Average True Range) measures volatility, allowing stops
    to adapt to market conditions automatically.
    """

    def __init__(
        self,
        atr_period: int = 14,
        sl_multiplier: float = 2.0,
        tp_multiplier: float = 3.0,
        min_sl_pips: float = 10.0,
        max_sl_pips: float = 100.0,
    ):
        """
        Initialize ATR Stop Calculator.

        Args:
            atr_period: Period for ATR calculation (default: 14)
            sl_multiplier: ATR multiplier for stop loss (default: 2.0)
            tp_multiplier: ATR multiplier for take profit (default: 3.0)
            min_sl_pips: Minimum stop loss in pips (default: 10)
            max_sl_pips: Maximum stop loss in pips (default: 100)
        """
        self.atr_period = atr_period
        self.sl_multiplier = sl_multiplier
        self.tp_multiplier = tp_multiplier
        self.min_sl_pips = min_sl_pips
        self.max_sl_pips = max_sl_pips

        logger.info(
            f"ATRStopCalculator initialized: period={atr_period}, "
            f"sl_mult={sl_multiplier}, tp_mult={tp_multiplier}"
        )

    def calculate_atr(
        self, high: np.ndarray, low: np.ndarray, close: np.ndarray
    ) -> np.ndarray:
        """
        Calculate Average True Range (ATR).

        Args:
            high: Array of high prices
            low: Array of low prices
            close: Array of close prices

        Returns:
            Array of ATR values
        """
        # Calculate True Range components
        tr1 = high - low  # High - Low
        tr2 = np.abs(high - np.roll(close, 1))  # |High - PrevClose|
        tr3 = np.abs(low - np.roll(close, 1))  # |Low - PrevClose|

        # True Range = max of the three
        tr = np.maximum(tr1, np.maximum(tr2, tr3))

        # First TR is invalid (no previous close)
        tr[0] = tr1[0]

        # Calculate ATR using exponential moving average
        atr = self._ema(tr, self.atr_period)

        return atr

    def calculate_stops(
        self,
        entry_price: float,
        atr_value: float,
        direction: str,
        symbol: str = "EURUSD",
    ) -> Tuple[float, float]:
        """
        Calculate stop loss and take profit using ATR.

        Args:
            entry_price: Entry price for the trade
            atr_value: Current ATR value
            direction: 'BUY' or 'SELL'
            symbol: Trading symbol (for pip calculation)

        Returns:
            Tuple of (stop_loss_price, take_profit_price)
        """
        # Calculate pip size
        pip_size = self._get_pip_size(symbol, entry_price)

        # Calculate ATR in pips
        atr_pips = atr_value / pip_size

        # Calculate stop distance in pips
        sl_pips = atr_pips * self.sl_multiplier

        # Apply min/max limits
        sl_pips = max(self.min_sl_pips, min(sl_pips, self.max_sl_pips))

        # Calculate TP distance (risk/reward ratio)
        tp_pips = sl_pips * (self.tp_multiplier / self.sl_multiplier)

        # Convert back to price
        sl_distance = sl_pips * pip_size
        tp_distance = tp_pips * pip_size

        if direction.upper() == "BUY":
            stop_loss = entry_price - sl_distance
            take_profit = entry_price + tp_distance
        elif direction.upper() == "SELL":
            stop_loss = entry_price + sl_distance
            take_profit = entry_price - tp_distance
        else:
            raise ValueError(f"Invalid direction: {direction}")

        logger.debug(
            f"{direction} {symbol}: Entry={entry_price:.5f}, "
            f"SL={stop_loss:.5f} ({sl_pips:.1f} pips), "
            f"TP={take_profit:.5f} ({tp_pips:.1f} pips), "
            f"ATR={atr_value:.5f}"
        )

        return stop_loss, take_profit

    def calculate_stops_from_data(
        self,
        entry_price: float,
        direction: str,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        symbol: str = "EURUSD",
    ) -> Tuple[float, float, float]:
        """
        Calculate stops from OHLC data.

        Args:
            entry_price: Entry price
            direction: 'BUY' or 'SELL'
            high: High prices
            low: Low prices
            close: Close prices
            symbol: Trading symbol

        Returns:
            Tuple of (stop_loss, take_profit, atr_value)
        """
        # Calculate ATR
        atr = self.calculate_atr(high, low, close)
        current_atr = atr[-1]  # Most recent ATR

        # Calculate stops
        sl, tp = self.calculate_stops(entry_price, current_atr, direction, symbol)

        return sl, tp, current_atr

    def calculate_position_size_with_atr(
        self,
        balance: float,
        risk_percent: float,
        entry_price: float,
        atr_value: float,
        direction: str,
        symbol: str = "EURUSD",
    ) -> Tuple[float, float, float]:
        """
        Calculate position size considering ATR-based stop loss.

        Args:
            balance: Account balance
            risk_percent: Risk percentage (e.g., 1.0 for 1%)
            entry_price: Entry price
            atr_value: Current ATR
            direction: 'BUY' or 'SELL'
            symbol: Trading symbol

        Returns:
            Tuple of (lot_size, stop_loss, take_profit)
        """
        # Calculate stops
        sl, tp = self.calculate_stops(entry_price, atr_value, direction, symbol)

        # Calculate stop distance
        sl_distance = abs(entry_price - sl)

        # Calculate risk amount
        risk_amount = balance * (risk_percent / 100)

        # Calculate pip size
        pip_size = self._get_pip_size(symbol, entry_price)

        # Calculate pips at risk
        pips_at_risk = sl_distance / pip_size

        # Standard lot value per pip (for forex)
        pip_value = 10.0  # $10 per pip for standard lot

        # Calculate lot size
        # lot_size = risk_amount / (pips_at_risk * pip_value)
        lot_size = (
            risk_amount / (pips_at_risk * pip_value) if pips_at_risk > 0 else 0.01
        )

        # Apply lot size limits
        lot_size = max(0.01, min(lot_size, 10.0))  # 0.01 to 10 lots

        return lot_size, sl, tp

    def _ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """Calculate Exponential Moving Average"""
        alpha = 2 / (period + 1)
        ema = np.zeros_like(data)
        ema[0] = data[0]

        for i in range(1, len(data)):
            ema[i] = alpha * data[i] + (1 - alpha) * ema[i - 1]

        return ema

    def _get_pip_size(self, symbol: str, price: float) -> float:
        """
        Get pip size for a symbol.

        Args:
            symbol: Trading symbol
            price: Current price (for JPY pair detection)

        Returns:
            Pip size
        """
        # JPY pairs: 1 pip = 0.01
        if "JPY" in symbol.upper():
            return 0.01

        # Most forex pairs: 1 pip = 0.0001
        return 0.0001

    def get_atr_summary(
        self, high: np.ndarray, low: np.ndarray, close: np.ndarray
    ) -> dict:
        """
        Get ATR analysis summary.

        Args:
            high: High prices
            low: Low prices
            close: Close prices

        Returns:
            Dict with ATR statistics
        """
        atr = self.calculate_atr(high, low, close)

        return {
            "current_atr": atr[-1],
            "avg_atr": np.mean(atr[-20:]),  # Last 20 periods
            "min_atr": np.min(atr[-20:]),
            "max_atr": np.max(atr[-20:]),
            "atr_trend": "increasing" if atr[-1] > atr[-5] else "decreasing",
            "volatility_level": self._classify_volatility(atr[-1], atr),
        }

    def _classify_volatility(self, current_atr: float, atr_history: np.ndarray) -> str:
        """Classify current volatility level"""
        avg_atr = np.mean(atr_history[-50:])  # 50-period average

        if current_atr > avg_atr * 1.5:
            return "very_high"
        elif current_atr > avg_atr * 1.2:
            return "high"
        elif current_atr < avg_atr * 0.8:
            return "low"
        elif current_atr < avg_atr * 0.5:
            return "very_low"
        else:
            return "normal"


# Demo/Testing
if __name__ == "__main__":
    print("📊 ATR-Based Stop Loss/Take Profit - Demo\n")

    # Generate sample price data
    np.random.seed(42)
    n_candles = 100

    # Simulate EUR/USD price around 1.10
    base_price = 1.1000
    volatility = 0.0020

    # Random walk with volatility
    returns = np.random.normal(0, volatility, n_candles)
    close = base_price + np.cumsum(returns)
    high = close + np.random.uniform(0, volatility, n_candles)
    low = close - np.random.uniform(0, volatility, n_candles)

    # Initialize calculator
    atr_calc = ATRStopCalculator(
        atr_period=14,
        sl_multiplier=2.0,
        tp_multiplier=3.0,
        min_sl_pips=10,
        max_sl_pips=100,
    )

    print("Configuration:")
    print(f"  ATR Period: {atr_calc.atr_period}")
    print(f"  SL Multiplier: {atr_calc.sl_multiplier}x ATR")
    print(f"  TP Multiplier: {atr_calc.tp_multiplier}x ATR")
    print(f"  Min/Max SL: {atr_calc.min_sl_pips}-{atr_calc.max_sl_pips} pips\n")

    # Calculate ATR
    atr = atr_calc.calculate_atr(high, low, close)
    current_atr = atr[-1]
    current_price = close[-1]

    print(f"Current Market:")
    print(f"  Price: {current_price:.5f}")
    print(f"  ATR: {current_atr:.5f}\n")

    # Test BUY trade
    print("Test 1: BUY Trade")
    sl_buy, tp_buy = atr_calc.calculate_stops(
        entry_price=current_price,
        atr_value=current_atr,
        direction="BUY",
        symbol="EURUSD",
    )

    pip_size = 0.0001
    sl_pips = abs(current_price - sl_buy) / pip_size
    tp_pips = abs(tp_buy - current_price) / pip_size
    rr_ratio = tp_pips / sl_pips if sl_pips > 0 else 0

    print(f"  Entry: {current_price:.5f}")
    print(f"  Stop Loss: {sl_buy:.5f} ({sl_pips:.1f} pips below)")
    print(f"  Take Profit: {tp_buy:.5f} ({tp_pips:.1f} pips above)")
    print(f"  Risk/Reward: 1:{rr_ratio:.2f}\n")

    # Test SELL trade
    print("Test 2: SELL Trade")
    sl_sell, tp_sell = atr_calc.calculate_stops(
        entry_price=current_price,
        atr_value=current_atr,
        direction="SELL",
        symbol="EURUSD",
    )

    sl_pips = abs(sl_sell - current_price) / pip_size
    tp_pips = abs(current_price - tp_sell) / pip_size
    rr_ratio = tp_pips / sl_pips if sl_pips > 0 else 0

    print(f"  Entry: {current_price:.5f}")
    print(f"  Stop Loss: {sl_sell:.5f} ({sl_pips:.1f} pips above)")
    print(f"  Take Profit: {tp_sell:.5f} ({tp_pips:.1f} pips below)")
    print(f"  Risk/Reward: 1:{rr_ratio:.2f}\n")

    # Test position sizing
    print("Test 3: Position Sizing with ATR")
    balance = 10000
    risk_pct = 1.0

    lot_size, sl, tp = atr_calc.calculate_position_size_with_atr(
        balance=balance,
        risk_percent=risk_pct,
        entry_price=current_price,
        atr_value=current_atr,
        direction="BUY",
        symbol="EURUSD",
    )

    print(f"  Balance: ${balance:,.2f}")
    print(f"  Risk: {risk_pct}% = ${balance * risk_pct / 100:.2f}")
    print(f"  Calculated Lot Size: {lot_size:.2f}")
    print(f"  Stop Loss: {sl:.5f}")
    print(f"  Take Profit: {tp:.5f}\n")

    # ATR Summary
    print("Test 4: ATR Analysis Summary")
    summary = atr_calc.get_atr_summary(high, low, close)

    print(f"  Current ATR: {summary['current_atr']:.5f}")
    print(f"  Average ATR (20): {summary['avg_atr']:.5f}")
    print(f"  Min/Max ATR: {summary['min_atr']:.5f} / {summary['max_atr']:.5f}")
    print(f"  Trend: {summary['atr_trend']}")
    print(f"  Volatility: {summary['volatility_level']}")

    print("\n✅ Demo complete!")
