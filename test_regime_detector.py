#!/usr/bin/env python3
"""
Unit tests for RegimeDetector (5 Active Market Regimes)
"""

import numpy as np
import pandas as pd
import unittest
from utils.regime_detector import RegimeDetector

class TestRegimeDetector(unittest.TestCase):
    def setUp(self):
        self.detector = RegimeDetector(confirm_candles=1, cooldown_candles=0)

    def test_classify_raw_extreme_volatility(self):
        regime = self.detector._classify_raw(atr_ratio=2.6, adx=18.0)
        self.assertEqual(regime, "EXTREME_VOLATILITY")

    def test_classify_raw_breakout(self):
        regime = self.detector._classify_raw(atr_ratio=1.8, adx=28.0)
        self.assertEqual(regime, "BREAKOUT")

        regime_override = self.detector._classify_raw(atr_ratio=1.1, adx=36.0)
        self.assertEqual(regime_override, "BREAKOUT")

    def test_classify_raw_trend_following(self):
        regime = self.detector._classify_raw(atr_ratio=1.1, adx=27.0)
        self.assertEqual(regime, "TREND_FOLLOWING")

    def test_classify_raw_volatility_squeeze(self):
        regime = self.detector._classify_raw(atr_ratio=0.6, adx=12.0)
        self.assertEqual(regime, "VOLATILITY_SQUEEZE")

    def test_classify_raw_mean_reversion(self):
        regime = self.detector._classify_raw(atr_ratio=1.0, adx=15.0)
        self.assertEqual(regime, "MEAN_REVERSION")

if __name__ == "__main__":
    unittest.main()
