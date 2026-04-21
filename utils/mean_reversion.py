#!/usr/bin/env python3
"""
Mean Reversion Trading Strategy

For range-bound markets like EUR/USD.
Uses Bollinger Bands and RSI for overbought/oversold signals.

Author: Trading Bot Team
Created: 2025-12-28
"""

import numpy as np
import pandas as pd
from typing import Dict


class MeanReversionStrategy:
    """
    Mean reversion strategy using Bollinger Bands and RSI.

    Buy when: Price touches lower band + RSI < 30
    Sell when: Price touches upper band + RSI > 70
    """

    def __init__(
        self,
        bb_period: int = 20,
        bb_std: float = 2.0,
        rsi_period: int = 14,
        rsi_oversold: float = 30,
        rsi_overbought: float = 70,
    ):
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought

    def calculate_rsi(self, prices: np.ndarray) -> float:
        """Calculate RSI."""
        if len(prices) < self.rsi_period + 1:
            return 50

        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains[-self.rsi_period :])
        avg_loss = np.mean(losses[-self.rsi_period :])

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def calculate_bollinger(self, prices: np.ndarray) -> tuple:
        """Calculate Bollinger Bands."""
        if len(prices) < self.bb_period:
            return 0, 0, 0

        sma = np.mean(prices[-self.bb_period :])
        std = np.std(prices[-self.bb_period :])

        upper = sma + (self.bb_std * std)
        lower = sma - (self.bb_std * std)

        return lower, sma, upper

    def get_signal(self, df: pd.DataFrame, idx: int) -> Dict:
        """Generate trading signal."""
        if idx < max(self.bb_period, self.rsi_period) + 1:
            return {"signal": "HOLD", "confidence": 0, "reason": "Warmup"}

        closes = df["Close"].values[: idx + 1]
        current_price = closes[-1]

        # Calculate indicators
        rsi = self.calculate_rsi(closes)
        bb_lower, bb_mid, bb_upper = self.calculate_bollinger(closes)

        # Calculate distance from bands
        band_range = bb_upper - bb_lower
        if band_range == 0:
            return {"signal": "HOLD", "confidence": 0, "reason": "No range"}

        position_in_band = (current_price - bb_lower) / band_range

        # Generate signals
        if rsi < self.rsi_oversold and current_price <= bb_lower:
            confidence = min(100, int((self.rsi_oversold - rsi) * 2 + 50))
            return {
                "signal": "BUY",
                "confidence": confidence,
                "reason": f"Oversold (RSI={rsi:.1f}, at lower BB)",
                "rsi": rsi,
                "bb_position": position_in_band,
            }

        elif rsi > self.rsi_overbought and current_price >= bb_upper:
            confidence = min(100, int((rsi - self.rsi_overbought) * 2 + 50))
            return {
                "signal": "SELL",
                "confidence": confidence,
                "reason": f"Overbought (RSI={rsi:.1f}, at upper BB)",
                "rsi": rsi,
                "bb_position": position_in_band,
            }

        return {
            "signal": "HOLD",
            "confidence": 0,
            "reason": "No signal",
            "rsi": rsi,
            "bb_position": position_in_band,
        }

    def get_trend_signal(self, df: pd.DataFrame, idx: int, regime: str) -> Dict:
        """
        Generate trend-following signal for trending markets.

        In TRENDING_DOWN: Look for pullback bounces to short (RSI > 45)
        In TRENDING_UP: Look for pullback dips to buy (RSI < 55)
        """
        if idx < max(self.bb_period, self.rsi_period) + 1:
            return {"signal": "HOLD", "confidence": 0, "reason": "Warmup"}

        closes = df["Close"].values[: idx + 1]
        current_price = closes[-1]
        rsi = self.calculate_rsi(closes)
        bb_lower, bb_mid, bb_upper = self.calculate_bollinger(closes)

        band_range = bb_upper - bb_lower
        position_in_band = (
            (current_price - bb_lower) / band_range if band_range > 0 else 0.5
        )

        # Trend-following: Short pullback bounces in downtrend
        if regime == "TRENDING_DOWN":
            # PHASE 7.3: Narrowed from RSI 40-70 to 50-65
            # Requires genuine pullback bounce (RSI > 50) before shorting
            if rsi > 50 and rsi < 65:
                # Higher RSI = better short opportunity (more of a bounce)
                confidence = min(100, int(40 + (rsi - 50) * 4.0))
                return {
                    "signal": "SELL",
                    "confidence": confidence,
                    "reason": f"Trend SHORT: RSI={rsi:.1f} pullback in downtrend",
                    "rsi": rsi,
                    "bb_position": position_in_band,
                }

        # Trend-following: Buy dips in uptrend
        elif regime == "TRENDING_UP":
            # PHASE 7.3: Narrowed from RSI 30-60 to 35-55
            # Requires actual dip (RSI < 55) before buying
            if rsi > 35 and rsi < 55:
                # Lower RSI = better buy opportunity (more of a dip)
                confidence = min(100, int(50 + (55 - rsi)))
                return {
                    "signal": "BUY",
                    "confidence": confidence,
                    "reason": f"Trend LONG: RSI={rsi:.1f} dip in uptrend",
                    "rsi": rsi,
                    "bb_position": position_in_band,
                }

        return {
            "signal": "HOLD",
            "confidence": 0,
            "reason": "No trend signal",
            "rsi": rsi,
            "bb_position": position_in_band,
        }


def backtest_mean_reversion(df: pd.DataFrame, initial_balance: float = 5000) -> Dict:
    """Backtest mean reversion strategy."""
    strategy = MeanReversionStrategy()

    balance = initial_balance
    position = 0
    entry_price = 0
    trades = []
    pip_value = 10
    lot_size = 0.1
    spread = 1.0

    for i in range(30, len(df)):
        signal_data = strategy.get_signal(df, i)
        signal = signal_data["signal"]
        confidence = signal_data["confidence"]
        price = df.iloc[i]["Close"]

        if signal == "BUY" and confidence >= 50:
            if position == 0:
                position = 1
                entry_price = price
            elif position == -1:
                pnl = ((entry_price - price) * 10000 - spread) * pip_value * lot_size
                balance += pnl
                trades.append({"pnl": pnl, "type": "short_close"})
                position = 1
                entry_price = price

        elif signal == "SELL" and confidence >= 50:
            if position == 0:
                position = -1
                entry_price = price
            elif position == 1:
                pnl = ((price - entry_price) * 10000 - spread) * pip_value * lot_size
                balance += pnl
                trades.append({"pnl": pnl, "type": "long_close"})
                position = -1
                entry_price = price

    # Close final position
    if position != 0:
        price = df.iloc[-1]["Close"]
        if position == 1:
            pnl = ((price - entry_price) * 10000 - spread) * pip_value * lot_size
        else:
            pnl = ((entry_price - price) * 10000 - spread) * pip_value * lot_size
        balance += pnl
        trades.append({"pnl": pnl, "type": "final"})

    wins = sum(1 for t in trades if t["pnl"] > 0)

    return {
        "strategy": "Mean Reversion",
        "return_pct": (balance - initial_balance) / initial_balance * 100,
        "total_trades": len(trades),
        "wins": wins,
        "win_rate": wins / max(1, len(trades)),
        "final_balance": balance,
    }


if __name__ == "__main__":
    import yfinance as yf

    print("📊 Testing Mean Reversion Strategy")
    print("=" * 50)

    # Test on EUR/USD (range-bound)
    df = yf.download("EURUSD=X", period="6mo", interval="1h", progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    df = df.reset_index()

    results = backtest_mean_reversion(df)

    print(f"\nEUR/USD Results:")
    print(f"   Return: {results['return_pct']:+.2f}%")
    print(f"   Trades: {results['total_trades']}")
    print(f"   Win Rate: {results['win_rate']:.1%}")
