#!/usr/bin/env python3
"""
Volatility Breakout Trading Strategy

For trending/volatile markets (geopolitical events, news-driven moves).
Uses Donchian Channels, ATR expansion, and ADX for breakout confirmation.

Complements the Mean Reversion strategy:
  - Mean Reversion profits in CALM markets
  - Volatility Breakout profits in CHAOTIC markets

Author: Trading Bot Team
Created: 2026-04-18
"""

import numpy as np
import pandas as pd
from typing import Dict


class VolatilityBreakoutStrategy:
    """
    Volatility breakout strategy using Donchian Channels + ATR + ADX.

    BUY when:  Price breaks above Donchian high + ATR expanding + ADX > 25
    SELL when: Price breaks below Donchian low  + ATR expanding + ADX > 25
    """

    def __init__(
        self,
        donchian_period: int = 20,
        atr_period: int = 14,
        atr_expansion_factor: float = 1.5,
        adx_period: int = 14,
        adx_threshold: float = 25.0,
        volume_factor: float = 1.2,
    ):
        self.donchian_period = donchian_period
        self.atr_period = atr_period
        self.atr_expansion_factor = atr_expansion_factor
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.volume_factor = volume_factor

    def calculate_donchian(self, df: pd.DataFrame, idx: int) -> tuple:
        """
        Calculate Donchian Channel (highest high & lowest low over N periods).

        Returns: (lower, mid, upper)
        """
        if idx < self.donchian_period:
            return 0, 0, 0

        highs = df["High"].values[idx - self.donchian_period : idx]
        lows = df["Low"].values[idx - self.donchian_period : idx]

        upper = np.max(highs)
        lower = np.min(lows)
        mid = (upper + lower) / 2

        return lower, mid, upper

    def calculate_atr(self, df: pd.DataFrame, idx: int, period: int = None) -> float:
        """Calculate Average True Range."""
        period = period or self.atr_period
        if idx < period + 1:
            return 0

        true_ranges = []
        for i in range(idx - period, idx):
            high = df["High"].values[i]
            low = df["Low"].values[i]
            prev_close = df["Close"].values[i - 1]

            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close),
            )
            true_ranges.append(tr)

        return np.mean(true_ranges)

    def is_atr_expanding(self, df: pd.DataFrame, idx: int) -> tuple:
        """
        Check if ATR is expanding (volatility increasing).

        Returns: (is_expanding: bool, current_atr: float, avg_atr: float, ratio: float)
        """
        current_atr = self.calculate_atr(df, idx)
        if current_atr == 0:
            return False, 0, 0, 0

        # Calculate average ATR over longer lookback (2x period)
        lookback = self.atr_period * 2
        if idx < lookback + 1:
            return False, current_atr, current_atr, 1.0

        atr_values = []
        for i in range(idx - lookback, idx):
            atr_val = self.calculate_atr(df, i)
            if atr_val > 0:
                atr_values.append(atr_val)

        if not atr_values:
            return False, current_atr, current_atr, 1.0

        avg_atr = np.mean(atr_values)
        ratio = current_atr / avg_atr if avg_atr > 0 else 1.0

        return ratio >= self.atr_expansion_factor, current_atr, avg_atr, ratio

    def calculate_adx(self, df: pd.DataFrame, idx: int) -> float:
        """
        Calculate Average Directional Index (ADX) for trend strength.

        ADX > 25 = strong trend, ADX < 20 = weak/no trend
        """
        period = self.adx_period
        if idx < period * 2 + 1:
            return 0

        # Calculate +DM and -DM
        plus_dm_list = []
        minus_dm_list = []
        tr_list = []

        for i in range(idx - period * 2, idx):
            high = df["High"].values[i]
            low = df["Low"].values[i]
            prev_high = df["High"].values[i - 1]
            prev_low = df["Low"].values[i - 1]
            prev_close = df["Close"].values[i - 1]

            # True Range
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_list.append(tr)

            # Directional Movement
            up_move = high - prev_high
            down_move = prev_low - low

            plus_dm = up_move if up_move > down_move and up_move > 0 else 0
            minus_dm = down_move if down_move > up_move and down_move > 0 else 0

            plus_dm_list.append(plus_dm)
            minus_dm_list.append(minus_dm)

        # Smooth with EMA-like (Wilder's smoothing)
        def wilders_smooth(values, period):
            smoothed = [np.mean(values[:period])]
            for v in values[period:]:
                smoothed.append(smoothed[-1] - smoothed[-1] / period + v)
            return smoothed

        sm_tr = wilders_smooth(tr_list, period)
        sm_plus_dm = wilders_smooth(plus_dm_list, period)
        sm_minus_dm = wilders_smooth(minus_dm_list, period)

        # Calculate +DI and -DI
        dx_list = []
        for i in range(len(sm_tr)):
            if sm_tr[i] == 0:
                continue
            plus_di = 100 * sm_plus_dm[i] / sm_tr[i]
            minus_di = 100 * sm_minus_dm[i] / sm_tr[i]
            di_sum = plus_di + minus_di
            if di_sum > 0:
                dx = 100 * abs(plus_di - minus_di) / di_sum
                dx_list.append(dx)

        if not dx_list:
            return 0

        # ADX = smoothed DX
        adx = np.mean(dx_list[-period:]) if len(dx_list) >= period else np.mean(dx_list)
        return adx

    def get_volume_confirmation(self, df: pd.DataFrame, idx: int) -> tuple:
        """
        Check if current candle has above-average volume.

        Returns: (is_confirmed: bool, volume_ratio: float)
        """
        if "Volume" not in df.columns or idx < 20:
            return True, 1.0  # Skip check if no volume data

        current_vol = df["Volume"].values[idx]
        avg_vol = np.mean(df["Volume"].values[max(0, idx - 20) : idx])

        if avg_vol == 0:
            return True, 1.0

        ratio = current_vol / avg_vol
        return ratio >= self.volume_factor, ratio

    def get_signal(self, df: pd.DataFrame, idx: int) -> Dict:
        """
        Generate volatility breakout trading signal.

        Returns dict with signal, confidence, reason, and indicator values.
        """
        warmup = max(self.donchian_period, self.atr_period * 2, self.adx_period * 2) + 2
        if idx < warmup:
            return {"signal": "HOLD", "confidence": 0, "reason": "Warmup period"}

        current_price = df["Close"].values[idx]
        current_high = df["High"].values[idx]
        current_low = df["Low"].values[idx]

        # 1. Donchian Channel
        dc_lower, dc_mid, dc_upper = self.calculate_donchian(df, idx)
        if dc_upper == 0:
            return {"signal": "HOLD", "confidence": 0, "reason": "No Donchian data"}

        # 2. ATR Expansion
        atr_expanding, current_atr, avg_atr, atr_ratio = self.is_atr_expanding(df, idx)

        # 3. ADX Trend Strength
        adx = self.calculate_adx(df, idx)

        # 4. Volume confirmation
        vol_confirmed, vol_ratio = self.get_volume_confirmation(df, idx)

        # Check for breakout above Donchian high
        breakout_up = current_price > dc_upper
        # Check for breakdown below Donchian low
        breakout_down = current_price < dc_lower

        # Build signal data dict for logging
        signal_data = {
            "donchian_upper": round(dc_upper, 3),
            "donchian_lower": round(dc_lower, 3),
            "donchian_mid": round(dc_mid, 3),
            "current_atr": round(current_atr, 5),
            "avg_atr": round(avg_atr, 5),
            "atr_ratio": round(atr_ratio, 2),
            "atr_expanding": atr_expanding,
            "adx": round(adx, 1),
            "vol_ratio": round(vol_ratio, 2),
            "vol_confirmed": vol_confirmed,
        }

        # --- BUY BREAKOUT ---
        if breakout_up:
            reasons = []
            score = 0

            # Must-have: ATR expansion
            if atr_expanding:
                score += 35
                reasons.append(f"ATR expanding ({atr_ratio:.1f}×)")
            else:
                return {
                    "signal": "HOLD",
                    "confidence": 0,
                    "reason": f"Breakout UP but ATR not expanding ({atr_ratio:.1f}×)",
                    **signal_data,
                }

            # Must-have: ADX confirmation
            if adx >= self.adx_threshold:
                score += 35
                reasons.append(f"ADX={adx:.0f} (strong trend)")
            else:
                return {
                    "signal": "HOLD",
                    "confidence": 0,
                    "reason": f"Breakout UP but weak trend (ADX={adx:.0f})",
                    **signal_data,
                }

            # Bonus: Volume confirmation
            if vol_confirmed:
                score += 15
                reasons.append(f"Vol {vol_ratio:.1f}× avg")

            # Bonus: How far above channel (momentum strength)
            channel_range = dc_upper - dc_lower
            if channel_range > 0:
                breakout_strength = (current_price - dc_upper) / channel_range
                if breakout_strength > 0.1:
                    score += 15
                    reasons.append(f"Strong breakout ({breakout_strength:.1%} above channel)")

            return {
                "signal": "BUY",
                "confidence": min(100, score),
                "reason": f"BREAKOUT UP: {', '.join(reasons)}",
                **signal_data,
            }

        # --- SELL BREAKDOWN ---
        elif breakout_down:
            reasons = []
            score = 0

            # Must-have: ATR expansion
            if atr_expanding:
                score += 35
                reasons.append(f"ATR expanding ({atr_ratio:.1f}×)")
            else:
                return {
                    "signal": "HOLD",
                    "confidence": 0,
                    "reason": f"Breakdown but ATR not expanding ({atr_ratio:.1f}×)",
                    **signal_data,
                }

            # Must-have: ADX confirmation
            if adx >= self.adx_threshold:
                score += 35
                reasons.append(f"ADX={adx:.0f} (strong trend)")
            else:
                return {
                    "signal": "HOLD",
                    "confidence": 0,
                    "reason": f"Breakdown but weak trend (ADX={adx:.0f})",
                    **signal_data,
                }

            # Bonus: Volume confirmation
            if vol_confirmed:
                score += 15
                reasons.append(f"Vol {vol_ratio:.1f}× avg")

            # Bonus: Breakdown strength
            channel_range = dc_upper - dc_lower
            if channel_range > 0:
                breakdown_strength = (dc_lower - current_price) / channel_range
                if breakdown_strength > 0.1:
                    score += 15
                    reasons.append(f"Strong breakdown ({breakdown_strength:.1%} below channel)")

            return {
                "signal": "SELL",
                "confidence": min(100, score),
                "reason": f"BREAKDOWN: {', '.join(reasons)}",
                **signal_data,
            }

        # --- NO BREAKOUT ---
        return {
            "signal": "HOLD",
            "confidence": 0,
            "reason": f"Inside channel (price={current_price:.3f}, upper={dc_upper:.3f}, lower={dc_lower:.3f})",
            **signal_data,
        }

    def calculate_dynamic_stop(self, df: pd.DataFrame, idx: int, multiplier: float = 1.5) -> float:
        """
        Calculate dynamic stop loss distance based on ATR.

        Returns stop distance in price units (not pips).
        """
        current_atr = self.calculate_atr(df, idx)
        return current_atr * multiplier

    def calculate_trailing_distance(self, df: pd.DataFrame, idx: int, multiplier: float = 2.0) -> float:
        """
        Calculate trailing stop distance based on ATR.

        Returns trailing distance in price units.
        """
        current_atr = self.calculate_atr(df, idx)
        return current_atr * multiplier


def backtest_volatility_breakout(
    df: pd.DataFrame, initial_balance: float = 5000
) -> Dict:
    """Backtest volatility breakout strategy."""
    strategy = VolatilityBreakoutStrategy()

    balance = initial_balance
    position = 0  # -1=short, 0=flat, 1=long
    entry_price = 0
    stop_loss = 0
    trailing_stop = 0
    peak_price = 0
    trades = []

    warmup = max(strategy.donchian_period, strategy.atr_period * 2, strategy.adx_period * 2) + 2

    for i in range(warmup, len(df)):
        signal_data = strategy.get_signal(df, i)
        signal = signal_data["signal"]
        confidence = signal_data["confidence"]
        price = df.iloc[i]["Close"]
        high = df.iloc[i]["High"]
        low = df.iloc[i]["Low"]

        # Check stop loss / trailing stop for open positions
        if position == 1:  # Long
            # Update trailing stop
            if high > peak_price:
                peak_price = high
                trail_dist = strategy.calculate_trailing_distance(df, i)
                trailing_stop = max(trailing_stop, peak_price - trail_dist)

            # Check if stopped out
            if low <= stop_loss or low <= trailing_stop:
                exit_price = max(stop_loss, trailing_stop)
                pnl_pips = (exit_price - entry_price) / 0.01
                pnl_usd = pnl_pips * 6.45 * 0.1  # Approximate
                balance += pnl_usd
                trades.append({"pnl": pnl_usd, "type": "long_stop", "pips": pnl_pips})
                position = 0

        elif position == -1:  # Short
            if low < peak_price:
                peak_price = low
                trail_dist = strategy.calculate_trailing_distance(df, i)
                trailing_stop = min(trailing_stop, peak_price + trail_dist)

            if high >= stop_loss or high >= trailing_stop:
                exit_price = min(stop_loss, trailing_stop)
                pnl_pips = (entry_price - exit_price) / 0.01
                pnl_usd = pnl_pips * 6.45 * 0.1
                balance += pnl_usd
                trades.append({"pnl": pnl_usd, "type": "short_stop", "pips": pnl_pips})
                position = 0

        # Entry signals (only when flat)
        if position == 0 and confidence >= 60:
            stop_dist = strategy.calculate_dynamic_stop(df, i)

            if signal == "BUY":
                position = 1
                entry_price = price
                stop_loss = price - stop_dist
                peak_price = price
                trailing_stop = stop_loss

            elif signal == "SELL":
                position = -1
                entry_price = price
                stop_loss = price + stop_dist
                peak_price = price
                trailing_stop = stop_loss

    # Close final position
    if position != 0:
        price = df.iloc[-1]["Close"]
        if position == 1:
            pnl_pips = (price - entry_price) / 0.01
        else:
            pnl_pips = (entry_price - price) / 0.01
        pnl_usd = pnl_pips * 6.45 * 0.1
        balance += pnl_usd
        trades.append({"pnl": pnl_usd, "type": "final", "pips": pnl_pips})

    wins = sum(1 for t in trades if t["pnl"] > 0)

    return {
        "strategy": "Volatility Breakout",
        "return_pct": (balance - initial_balance) / initial_balance * 100,
        "total_trades": len(trades),
        "wins": wins,
        "win_rate": wins / max(1, len(trades)),
        "final_balance": balance,
    }


if __name__ == "__main__":
    print("📊 Testing Volatility Breakout Strategy")
    print("=" * 50)
    print("Run backtest with: python -m utils.volatility_breakout")
