#!/usr/bin/env python3
"""
Market Regime Detector

Classifies market conditions into:
  MEAN_REVERSION  — calm, range-bound (low ADX, low ATR)
  BREAKOUT        — volatile, trending (high ADX, expanding ATR)
  TRANSITIONAL    — mixed signals (no new entries, manage existing)

Uses ATR expansion ratio + ADX trend strength + SMA cross direction.

Author: Trading Bot Team
Created: 2026-04-19
"""

import numpy as np
import pandas as pd
from typing import Dict
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RegimeState:
    """Current market regime classification."""
    regime: str  # MEAN_REVERSION, BREAKOUT, TRANSITIONAL
    confidence: int  # 0-100
    atr_ratio: float  # current ATR vs average (>1.5 = expanding)
    adx: float  # trend strength (>25 = strong trend)
    sma_direction: str  # BULLISH, BEARISH, NEUTRAL
    reason: str  # Human-readable explanation
    confirmed: bool  # Has regime been stable for confirmation period?
    candles_in_regime: int  # How many candles current regime has held


class RegimeDetector:
    """
    Detects market regime using ATR + ADX consensus.

    Regime rules:
      - ATR ratio < 1.2 AND ADX < 20  → MEAN_REVERSION (calm market)
      - ATR ratio >= 1.5 AND ADX >= 25 → BREAKOUT (volatile/trending)
      - Otherwise                      → TRANSITIONAL (mixed signals)

    Confirmation: regime must hold for `confirm_candles` consecutive
    readings before it's considered stable. This prevents flickering.
    """

    # Thresholds for regime classification
    ATR_CALM_THRESHOLD = 1.2     # Below this = calm (mean reversion territory)
    ATR_VOLATILE_THRESHOLD = 1.5  # Above this = volatile (breakout territory)
    ADX_WEAK_THRESHOLD = 20.0    # Below this = no trend
    ADX_STRONG_THRESHOLD = 25.0  # Above this = strong trend

    def __init__(
        self,
        atr_period: int = 14,
        atr_avg_lookback: int = 50,
        adx_period: int = 14,
        sma_fast: int = 20,
        sma_slow: int = 50,
        confirm_candles: int = 2,
        cooldown_candles: int = 2,
    ):
        self.atr_period = atr_period
        self.atr_avg_lookback = atr_avg_lookback
        self.adx_period = adx_period
        self.sma_fast = sma_fast
        self.sma_slow = sma_slow
        self.confirm_candles = confirm_candles
        self.cooldown_candles = cooldown_candles

        # State tracking
        self._current_regime = "TRANSITIONAL"
        self._candles_in_regime = 0
        self._pending_regime = None
        self._pending_count = 0
        self._cooldown_remaining = 0
        self._last_switch_time = None

    def _calc_atr(self, df: pd.DataFrame, idx: int) -> float:
        """Calculate ATR at a given index."""
        if idx < self.atr_period + 1:
            return 0
        trs = []
        for i in range(idx - self.atr_period, idx):
            h = df["High"].values[i]
            l = df["Low"].values[i]
            pc = df["Close"].values[i - 1]
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        return np.mean(trs)

    def _calc_atr_ratio(self, df: pd.DataFrame, idx: int) -> float:
        """Calculate current ATR vs longer-term average ATR."""
        current_atr = self._calc_atr(df, idx)
        if current_atr == 0:
            return 1.0

        # Calculate average ATR over lookback period
        lookback = min(self.atr_avg_lookback, idx - self.atr_period - 1)
        if lookback < 5:
            return 1.0

        atr_vals = []
        for i in range(idx - lookback, idx):
            v = self._calc_atr(df, i)
            if v > 0:
                atr_vals.append(v)

        if not atr_vals:
            return 1.0
        return current_atr / np.mean(atr_vals)

    def _calc_adx(self, df: pd.DataFrame, idx: int) -> float:
        """Calculate ADX at given index."""
        period = self.adx_period
        if idx < period * 2 + 1:
            return 0

        plus_dm_list, minus_dm_list, tr_list = [], [], []
        for i in range(idx - period * 2, idx):
            h = df["High"].values[i]
            l = df["Low"].values[i]
            ph = df["High"].values[i - 1]
            pl = df["Low"].values[i - 1]
            pc = df["Close"].values[i - 1]

            tr_list.append(max(h - l, abs(h - pc), abs(l - pc)))
            up = h - ph
            dn = pl - l
            plus_dm_list.append(up if up > dn and up > 0 else 0)
            minus_dm_list.append(dn if dn > up and dn > 0 else 0)

        def wilders(vals, p):
            s = [np.mean(vals[:p])]
            for v in vals[p:]:
                s.append(s[-1] - s[-1] / p + v)
            return s

        sm_tr = wilders(tr_list, period)
        sm_pdm = wilders(plus_dm_list, period)
        sm_mdm = wilders(minus_dm_list, period)

        dx_list = []
        for i in range(len(sm_tr)):
            if sm_tr[i] == 0:
                continue
            pdi = 100 * sm_pdm[i] / sm_tr[i]
            mdi = 100 * sm_mdm[i] / sm_tr[i]
            s = pdi + mdi
            if s > 0:
                dx_list.append(100 * abs(pdi - mdi) / s)

        if not dx_list:
            return 0
        return np.mean(dx_list[-period:]) if len(dx_list) >= period else np.mean(dx_list)

    def _calc_sma_direction(self, df: pd.DataFrame, idx: int) -> str:
        """Determine SMA cross direction (BULLISH / BEARISH / NEUTRAL)."""
        if idx < self.sma_slow + 1:
            return "NEUTRAL"

        sma_fast = df["Close"].values[idx - self.sma_fast : idx].mean()
        sma_slow = df["Close"].values[idx - self.sma_slow : idx].mean()

        diff_pct = (sma_fast - sma_slow) / sma_slow * 100
        if diff_pct > 0.05:
            return "BULLISH"
        elif diff_pct < -0.05:
            return "BEARISH"
        return "NEUTRAL"

    def _classify_raw(self, atr_ratio: float, adx: float) -> str:
        """Raw regime classification from indicators (no confirmation)."""
        calm_atr = atr_ratio < self.ATR_CALM_THRESHOLD
        volatile_atr = atr_ratio >= self.ATR_VOLATILE_THRESHOLD
        weak_trend = adx < self.ADX_WEAK_THRESHOLD
        strong_trend = adx >= self.ADX_STRONG_THRESHOLD

        # Both indicators agree on calm
        if calm_atr and weak_trend:
            return "MEAN_REVERSION"

        # Both indicators agree on volatile/trending
        if volatile_atr and strong_trend:
            return "BREAKOUT"

        # Strong consensus on one side
        if calm_atr and not strong_trend:
            return "MEAN_REVERSION"
        if volatile_atr and not weak_trend:
            return "BREAKOUT"

        # Mixed signals
        return "TRANSITIONAL"

    def detect(self, df: pd.DataFrame, idx: int = None) -> RegimeState:
        """
        Detect current market regime.

        Returns RegimeState with classification, confidence, and metadata.
        """
        if idx is None:
            idx = len(df) - 1

        warmup = max(self.atr_period * 2 + 1, self.adx_period * 2 + 1, self.sma_slow + 1)
        if idx < warmup:
            return RegimeState(
                regime="TRANSITIONAL",
                confidence=0,
                atr_ratio=1.0,
                adx=0,
                sma_direction="NEUTRAL",
                reason="Warmup period",
                confirmed=False,
                candles_in_regime=0,
            )

        # Calculate indicators
        atr_ratio = round(self._calc_atr_ratio(df, idx), 2)
        adx = round(self._calc_adx(df, idx), 1)
        sma_dir = self._calc_sma_direction(df, idx)

        # Raw classification
        raw_regime = self._classify_raw(atr_ratio, adx)

        # --- Confirmation logic ---
        # If raw matches current, strengthen conviction
        if raw_regime == self._current_regime:
            self._candles_in_regime += 1
            self._pending_regime = None
            self._pending_count = 0
        # If raw differs, start counting toward switch
        elif raw_regime == self._pending_regime:
            self._pending_count += 1
        else:
            self._pending_regime = raw_regime
            self._pending_count = 1

        # Switch regime if pending has confirmed
        confirmed = True
        if self._pending_regime and self._pending_count >= self.confirm_candles:
            old_regime = self._current_regime
            self._current_regime = self._pending_regime
            self._candles_in_regime = self._pending_count
            self._pending_regime = None
            self._pending_count = 0
            self._cooldown_remaining = self.cooldown_candles
            self._last_switch_time = datetime.now()
            print(
                f"🔄 REGIME SWITCH: {old_regime} → {self._current_regime} "
                f"(ATR×={atr_ratio}, ADX={adx})"
            )

        # Cooldown after switch
        if self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1
            confirmed = False

        # Confidence scoring
        confidence = 50
        if self._current_regime == "MEAN_REVERSION":
            if atr_ratio < 1.0:
                confidence += 25
            if adx < 15:
                confidence += 25
            elif adx < 20:
                confidence += 10
        elif self._current_regime == "BREAKOUT":
            if atr_ratio > 2.0:
                confidence += 25
            if adx > 35:
                confidence += 25
            elif adx > 25:
                confidence += 10
        else:  # TRANSITIONAL
            confidence = 30

        confidence = min(100, max(0, confidence))

        # Build reason string
        parts = []
        parts.append(f"ATR×={atr_ratio}")
        parts.append(f"ADX={adx}")
        parts.append(f"SMA={sma_dir}")
        if self._cooldown_remaining > 0:
            parts.append(f"cooldown={self._cooldown_remaining}")
        reason = " | ".join(parts)

        return RegimeState(
            regime=self._current_regime,
            confidence=confidence,
            atr_ratio=atr_ratio,
            adx=adx,
            sma_direction=sma_dir,
            reason=reason,
            confirmed=confirmed,
            candles_in_regime=self._candles_in_regime,
        )

    def get_state_dict(self) -> dict:
        """Return serializable state for persistence."""
        return {
            "current_regime": self._current_regime,
            "candles_in_regime": self._candles_in_regime,
            "pending_regime": self._pending_regime,
            "pending_count": self._pending_count,
            "cooldown_remaining": self._cooldown_remaining,
            "last_switch_time": self._last_switch_time.isoformat() if self._last_switch_time else None,
        }

    def load_state_dict(self, state: dict):
        """Restore state from dict."""
        self._current_regime = state.get("current_regime", "TRANSITIONAL")
        self._candles_in_regime = state.get("candles_in_regime", 0)
        self._pending_regime = state.get("pending_regime")
        self._pending_count = state.get("pending_count", 0)
        self._cooldown_remaining = state.get("cooldown_remaining", 0)
        ts = state.get("last_switch_time")
        self._last_switch_time = datetime.fromisoformat(ts) if ts else None
