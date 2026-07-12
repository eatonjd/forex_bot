#!/usr/bin/env python3
"""
Range Trading Strategy

For consolidating/ranging markets (low volatility, neutral trend).
Identifies horizontal support/resistance boundaries and trades bounces off them.

Author: Trading Bot Team
Created: 2026-07-08
"""

import numpy as np
import pandas as pd
from typing import Dict


class RangeTradingStrategy:
    """
    Range trading strategy using local support/resistance boundaries + ADX.

    BUY when:  Price is near support boundary + ADX < 20 (ranging market)
    SELL when: Price is near resistance boundary + ADX < 20 (ranging market)
    """

    def __init__(
        self,
        range_period: int = 20,
        adx_period: int = 14,
        adx_max: float = 20.0,
        buffer_pips: float = 3.0,
        stop_loss_pips: float = 15.0,
    ):
        self.range_period = range_period
        self.adx_period = adx_period
        self.adx_max = adx_max
        self.buffer_pips = buffer_pips
        self.stop_loss_pips = stop_loss_pips

    def calculate_adx(self, df: pd.DataFrame, idx: int) -> float:
        """
        Calculate Average Directional Index (ADX) for trend strength.
        ADX < 20 indicates a weak/no trend (ideal for range trading).
        """
        period = self.adx_period
        if idx < period * 2 + 1:
            return 50  # Assume trend if warm-up is insufficient

        plus_dm_list = []
        minus_dm_list = []
        tr_list = []

        for i in range(idx - period * 2, idx + 1):
            high = df["High"].values[i]
            low = df["Low"].values[i]
            prev_high = df["High"].values[i - 1]
            prev_low = df["Low"].values[i - 1]
            prev_close = df["Close"].values[i - 1]

            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_list.append(tr)

            up_move = high - prev_high
            down_move = prev_low - low

            plus_dm = up_move if up_move > down_move and up_move > 0 else 0
            minus_dm = down_move if down_move > up_move and down_move > 0 else 0

            plus_dm_list.append(plus_dm)
            minus_dm_list.append(minus_dm)

        def wilders_smooth(values, period):
            smoothed = [np.mean(values[:period])]
            for v in values[period:]:
                smoothed.append(smoothed[-1] - smoothed[-1] / period + v)
            return smoothed

        sm_tr = wilders_smooth(tr_list, period)
        sm_plus_dm = wilders_smooth(plus_dm_list, period)
        sm_minus_dm = wilders_smooth(minus_dm_list, period)

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
            return 50

        adx = np.mean(dx_list[-period:]) if len(dx_list) >= period else np.mean(dx_list)
        return adx

    def get_signal(self, df: pd.DataFrame, idx: int, pip_size: float = 0.0001) -> Dict:
        """
        Generate range trading signal based on proximity to support/resistance.
        """
        if idx < max(self.range_period, self.adx_period * 2) + 2:
            return {"signal": "HOLD", "confidence": 0, "reason": "Warmup"}

        closes = df["Close"].values[: idx + 1]
        highs = df["High"].values[idx - self.range_period : idx]
        lows = df["Low"].values[idx - self.range_period : idx]
        
        current_price = closes[-1]
        
        # Define range boundaries (support and resistance)
        resistance = np.max(highs)
        support = np.min(lows)
        range_width = (resistance - support) / pip_size
        
        # Calculate ADX to filter trending markets
        adx = self.calculate_adx(df, idx)
        if adx > self.adx_max:
            return {
                "signal": "HOLD", 
                "confidence": 0, 
                "reason": f"Market trending (ADX={adx:.1f} > {self.adx_max:.1f})"
            }

        # Check if the range is wide enough to trade (at least 2x stop loss)
        if range_width < self.stop_loss_pips * 2:
            return {
                "signal": "HOLD",
                "confidence": 0,
                "reason": f"Range too narrow ({range_width:.1f} pips)"
            }

        buffer_dist = self.buffer_pips * pip_size
        stop_dist_limit = self.stop_loss_pips * pip_size

        # Check for bounce at support (BUY)
        if current_price <= support + buffer_dist and current_price > support - stop_dist_limit:
            # Entry SL is set 5 pips below support level to handle breakouts
            stop_loss = support - (5 * pip_size)
            stop_dist = current_price - stop_loss
            take_profit_dist = (resistance - current_price) * 0.9  # Target 90% of opposite boundary
            
            # Confidence increases the closer we are to the support line
            dist_to_support = max(0, (current_price - support) / pip_size)
            confidence = int(max(60, min(100, 100 - dist_to_support * 10)))
            
            return {
                "signal": "BUY",
                "confidence": confidence,
                "reason": f"Range support bounce (price near support level {support:.5f})",
                "stop_dist": stop_dist,
                "take_profit_dist": take_profit_dist,
                "support": support,
                "resistance": resistance
            }

        # Check for bounce at resistance (SELL)
        elif current_price >= resistance - buffer_dist and current_price < resistance + stop_dist_limit:
            # Entry SL is set 5 pips above resistance level to handle breakouts
            stop_loss = resistance + (5 * pip_size)
            stop_dist = stop_loss - current_price
            take_profit_dist = (current_price - support) * 0.9  # Target 90% of opposite boundary
            
            dist_to_resistance = max(0, (resistance - current_price) / pip_size)
            confidence = int(max(60, min(100, 100 - dist_to_resistance * 10)))
            
            return {
                "signal": "SELL",
                "confidence": confidence,
                "reason": f"Range resistance bounce (price near resistance level {resistance:.5f})",
                "stop_dist": stop_dist,
                "take_profit_dist": take_profit_dist,
                "support": support,
                "resistance": resistance
            }

        return {
            "signal": "HOLD",
            "confidence": 0,
            "reason": f"Price inside channel (price={current_price:.5f}, support={support:.5f}, resistance={resistance:.5f})"
        }
