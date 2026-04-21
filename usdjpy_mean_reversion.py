#!/usr/bin/env python3
"""
USD/JPY Mean Reversion Trading Bot

Uses the Mean Reversion strategy (BB + RSI) on USD/JPY M15 timeframe.
Backtested return: +957% over 60 days with 63.5% win rate.

Usage:
    python usdjpy_mean_reversion.py --mode paper
    python usdjpy_mean_reversion.py --mode live

Author: Trading Bot Team
Created: 2025-12-28
"""

import os
import sys
import time
import argparse
import json
import logging  # PHASE 7.1
from datetime import datetime
from pathlib import Path
import pytz

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from oandapyV20 import API
from oandapyV20.endpoints.accounts import AccountSummary
from oandapyV20.endpoints.instruments import InstrumentsCandles
from oandapyV20.endpoints.orders import OrderCreate
from oandapyV20.endpoints.positions import PositionDetails, PositionClose
from oandapyV20.endpoints.pricing import PricingInfo

import pandas as pd

from utils.mean_reversion import MeanReversionStrategy
from utils.trade_logger import TradeLogger


def is_forex_market_open() -> tuple:
    """Check if forex market is open (Sunday 5pm - Friday 5pm ET)."""
    et = pytz.timezone("America/New_York")
    now = datetime.now(et)
    weekday = now.weekday()  # 0=Monday, 6=Sunday
    hour = now.hour

    # Market closed: Friday after 5pm ET until Sunday 5pm ET
    if weekday == 4 and hour >= 17:  # Friday after 5pm
        return False, "Market closed (Friday evening)"
    if weekday == 5:  # Saturday
        return False, "Market closed (Saturday)"
    if weekday == 6 and hour < 17:  # Sunday before 5pm
        return False, "Market closed (Sunday - opens at 5pm ET)"

    return True, "Market open"


try:
    from utils.notifications import TradingNotifier

    notifier = TradingNotifier()
except Exception as e:
    print(f"⚠️ Notifications disabled: {e}")
    notifier = None


def send_notification(msg):
    """Send notification if available."""
    if notifier:
        try:
            # Use _send for simple messages
            notifier._send(msg, title="USD/JPY Bot")
        except Exception as e:
            print(f"⚠️ Notification failed: {e}")
    print(f"📢 {msg}")


class USDJPYMeanReversionBot:
    """
    USD/JPY Mean Reversion Trading Bot

    Entry: Buy when RSI < 30 + price at lower BB
    Exit: Sell when RSI > 70 + price at upper BB
    """

    def __init__(self, mode: str = "paper"):
        self.mode = mode
        self.instrument = "USD_JPY"
        self.granularity = "M15"  # 15-minute candles

        # OANDA setup
        self.api_key = (
            os.getenv("OANDA_API_KEY") 
            if mode == "paper" 
            else os.getenv("OANDA_API_KEY_LIVE")
        )
        self.account_id = (
            os.getenv("OANDA_ACCOUNT_ID")
            if mode == "paper"
            else os.getenv("OANDA_ACCOUNT_ID_LIVE")
        )
        self.environment = "practice" if mode == "paper" else "live"

        self.api = API(access_token=self.api_key, environment=self.environment)

        # Strategy
        self.strategy = MeanReversionStrategy(
            bb_period=20,
            bb_std=2.0,
            rsi_period=14,
            rsi_oversold=30,
            rsi_overbought=70,
        )

        # Risk management
        self.risk_percent = 0.02  # 2% risk per trade
        self.daily_target = 20  # PHASE 7.1: Activates trailing at $20 (was 50)
        self.trailing_amount = 10  # PHASE 7.1: Trail by $10 from peak (was 20)
        self.daily_pnl = 0
        self.max_daily_loss = -200  # Stop trading if down $200 (including open trades)
        self.stop_loss_pips = 20  # Tighter stop - was 50, reduced for better R:R
        self.take_profit_pips = (
            25  # Target profit in pips (DISABLED - trailing handles exits)
        )
        self.use_take_profit = (
            False  # PHASE 7.1: Disabled to let winners run with trailing
        )

        # Time-based exit (PHASE 7.1)
        self.max_holding_hours = 24  # Close position after 24h
        self.entry_time = None  # Track when position was entered

        # Pyramiding / Scale-in settings
        self.max_scale_ins = 0  # Disabled - amplifies losses at 48% WR
        self.scale_in_count = 0  # Current number of scale-ins
        self.min_profit_to_add = 25  # Must be $25+ in profit to add
        self.scale_in_size_pct = 0.5  # Scale-ins are 50% of initial size

        # Probe Entry Settings (Start small, confirm before full size)
        self.use_probe_entry = False  # PHASE 7.3: Disabled - amplifies losses
        self.probe_size_pct = 0.40  # Initial entry is 40% of full size
        self.probe_confirm_profit = 25  # Need +$25 to confirm and scale up
        self.probe_max_candles = (
            10  # Give probes more time - was 3 (45min), now 10 (2.5hr)
        )
        self.probe_entry_candle = 0  # Track candle count when probe was entered
        self.is_probe_position = False  # Is current position a probe?
        self.candle_count = 0  # Running candle counter

        # Trailing stop tracking
        self.trailing_active = False  # Becomes True when profit >= daily_target
        self.peak_profit = 0  # Highest profit seen while trailing

        # Position tracking
        self.position = 0  # -1=short, 0=flat, 1=long
        self.entry_price = 0

        # Regime Detection Settings
        self.use_regime_filter = True  # Enable trend/range detection
        self.regime_sma_period = 20  # SMA period for trend detection
        self.regime_slope_threshold = (
            0.015  # Min slope per candle to call it trending (lowered from 0.03)
        )
        self.current_regime = "RANGING"  # RANGING, TRENDING_UP, TRENDING_DOWN
        self._sma_cross_direction = "NEUTRAL"  # PHASE 7.3: Track SMA20/50 cross

        # Trend confirmation (PHASE 7.3)
        self.trend_confirm_candles = (
            8  # SMA cross must hold for 8 candles (2h) to confirm
        )

        # Volatility filter (PHASE 7.1)
        self.use_volatility_filter = True
        self.volatility_factor = 2.0  # PHASE 7.3: Skip if ATR > 2x average (was 1.5)
        self.atr_lookback = 20  # Candles for ATR calculation

        # Trade metadata for logging
        self.last_signal_data = {}  # RSI, BB position, confidence, reason
        self.last_market_data = {}  # Current price, ATR, spread

        # Date tracking for daily resets
        self.last_reset_date = datetime.now().date()

        # State persistence settings
        self.state_file = "bot_state_usdjpy.json"

        # Performance tracking
        self.trades_today = []  # List of trades for daily summary

        # Structured logging (PHASE 7.1)
        self.logger = logging.getLogger("forex_bot")
        self.logger.setLevel(logging.INFO)

        # Load saved state if it exists
        self.load_state()

        self.start_balance = 0  # Set on startup
        self.last_summary_date = None  # Track when last summary was sent
        self.daily_summary_hour = 17  # Send daily summary at 5pm ET (market close)

        print(f"\n{'=' * 60}")
        print("🤖 USD/JPY MEAN REVERSION BOT - PHASE 7.3")
        print(f"{'=' * 60}")
        print(f"Mode: {mode.upper()}")
        print(f"Account: {self.account_id}")
        print(f"Instrument: {self.instrument}")
        print(f"Timeframe: {self.granularity}")
        print(f"Risk per trade: {self.risk_percent * 100}%")
        print(
            f"Trailing: ${self.daily_target} activate, ${self.trailing_amount} trail; Loss limit: ${self.max_daily_loss}"
        )
        print(f"{'=' * 60}\n")

        # Sync positions and send startup alert
        self._sync_positions()
        self._send_startup_alert()

    def save_state(self):
        """Save bot state to storage."""
        try:
            state = {
                "is_probe_position": self.is_probe_position,
                "scale_in_count": self.scale_in_count,
                "probe_entry_candle": self.probe_entry_candle,
                "candle_count": self.candle_count,
                "last_reset_date": str(self.last_reset_date),
                "daily_pnl": self.daily_pnl,
                "trailing_active": self.trailing_active,
                "peak_profit": self.peak_profit,
                "last_update": datetime.now().isoformat(),
            }

            # Save locally
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)

            # Save to GCS if available
            bucket_name = os.getenv("GCS_BUCKET_NAME", "forex-bot-state")
            if os.getenv("USE_CLOUD_STORAGE", "").lower() == "true":
                from google.cloud import storage

                client = storage.Client()
                bucket = client.bucket(bucket_name)
                blob = bucket.blob(f"state/{self.state_file}")
                blob.upload_from_string(
                    json.dumps(state, indent=2), content_type="application/json"
                )
                print(f"💾 State saved to GCS: {self.state_file}")
        except Exception as e:
            print(f"⚠️ State save error: {e}")

    def load_state(self):
        """Load bot state from storage."""
        try:
            state = None
            # Try GCS first
            bucket_name = os.getenv("GCS_BUCKET_NAME", "forex-bot-state")
            if os.getenv("USE_CLOUD_STORAGE", "").lower() == "true":
                try:
                    from google.cloud import storage

                    client = storage.Client()
                    bucket = client.bucket(bucket_name)
                    blob = bucket.blob(f"state/{self.state_file}")
                    if blob.exists():
                        state = json.loads(blob.download_as_text())
                        print(f"🔄 State loaded from GCS: {self.state_file}")
                except Exception as gcs_err:
                    print(f"⚠️ GCS state load error: {gcs_err}")

            # Fallback to local
            if not state and os.path.exists(self.state_file):
                with open(self.state_file, "r") as f:
                    state = json.load(f)
                    print(f"🔄 State loaded from local file: {self.state_file}")

            if state:
                self.is_probe_position = state.get("is_probe_position", False)
                self.scale_in_count = state.get("scale_in_count", 0)
                self.probe_entry_candle = state.get("probe_entry_candle", 0)
                self.candle_count = state.get("candle_count", 0)
                # self.daily_pnl = state.get("daily_pnl", 0) # Use OANDA for pnl normally
                self.trailing_active = state.get("trailing_active", False)
                self.peak_profit = state.get("peak_profit", 0)
                # last_reset_date is handled by _sync_positions and daily reset logic
        except Exception as e:
            print(f"⚠️ State load error: {e}")

    def _sync_positions(self):
        """Sync with existing OANDA positions on startup."""
        try:
            pos_dir, pos_units, entry_price, unrealized_pnl = (
                self.get_current_position()
            )
            if pos_dir != 0:
                self.position = pos_dir
                self.entry_price = entry_price
                direction = "LONG" if pos_dir == 1 else "SHORT"
                print(
                    f"📍 Found existing position: {direction} {pos_units:,} units @ {entry_price:.3f}"
                )
                print(f"   Unrealized P/L: ${unrealized_pnl:+.2f}")
            else:
                print("📍 No existing position found")
        except Exception as e:
            print(f"⚠️ Could not sync positions: {e}")

    def _send_startup_alert(self):
        """Send startup notification with account info."""
        try:
            balance = self.get_account_balance()
            self.start_balance = balance

            msg = (
                f"🚀 USD/JPY Bot Started\n"
                f"Mode: {self.mode.upper()}\n"
                f"Balance: ${balance:,.2f}\n"
                f"Strategy: Mean Reversion (BB+RSI)\n"
                f"Timeframe: {self.granularity}\n"
                f"Daily Target: ${self.daily_target}"
            )
            send_notification(msg)
            print("✅ Startup alert sent")
        except Exception as e:
            print(f"⚠️ Startup alert failed: {e}")

    def get_account_balance(self) -> float:
        """Get current account balance."""
        try:
            r = AccountSummary(accountID=self.account_id)
            self.api.request(r)
            return float(r.response["account"]["balance"])
        except Exception as e:
            print(f"Error getting balance: {e}")
            return 0

    def get_candles(self, count: int = 100) -> pd.DataFrame:
        """Fetch M15 candles from OANDA."""
        try:
            params = {
                "count": count,
                "granularity": self.granularity,
            }
            r = InstrumentsCandles(instrument=self.instrument, params=params)
            self.api.request(r)

            candles = r.response["candles"]
            data = []
            for c in candles:
                if c["complete"]:
                    data.append(
                        {
                            "Date": c["time"],
                            "Open": float(c["mid"]["o"]),
                            "High": float(c["mid"]["h"]),
                            "Low": float(c["mid"]["l"]),
                            "Close": float(c["mid"]["c"]),
                            "Volume": int(c["volume"]),
                        }
                    )

            return pd.DataFrame(data)
        except Exception as e:
            print(f"Error fetching candles: {e}")
            return pd.DataFrame()

    def get_current_position(self) -> tuple:
        """
        Get current position for USD_JPY.
        Returns (direction, units, average_price, unrealized_pnl)
        direction: 1 (LONG), -1 (SHORT), 0 (FLAT)
        """
        try:
            r = PositionDetails(accountID=self.account_id, instrument=self.instrument)
            self.api.request(r)

            pos = r.response["position"]
            long_units = int(pos["long"]["units"])
            short_units = int(pos["short"]["units"])

            # Sum up P/L from all open trades for more accurate reading
            # Sometimes PositionDetails P/L is slightly delayed
            unrealized_pnl = float(pos.get("unrealizedPL", 0))

            if long_units > 0:
                avg_price = float(pos["long"].get("averagePrice", 0))
                return 1, long_units, avg_price, unrealized_pnl
            elif short_units != 0:
                avg_price = float(pos["short"].get("averagePrice", 0))
                return -1, abs(short_units), avg_price, unrealized_pnl
            else:
                return 0, 0, 0, 0
        except Exception as e:
            print(f"⚠️ Error syncing position: {e}")
            # IMPORTANT: Return a special value or re-raise if you want to skip iteration
            # Returning 0,0,0,0 here can cause 'double positions' if signal matches
            return None  # Skip this iteration if we can't sync

    def get_current_spread(self) -> float:
        """Get current bid/ask spread in pips for USD_JPY."""
        try:
            params = {"instruments": self.instrument}
            r = PricingInfo(accountID=self.account_id, params=params)
            self.api.request(r)

            if r.response["prices"]:
                price_data = r.response["prices"][0]
                bid = float(price_data["bids"][0]["price"])
                ask = float(price_data["asks"][0]["price"])
                spread_pips = (ask - bid) * 100  # USD/JPY: 1 pip = 0.01
                return round(spread_pips, 2)
        except Exception as e:
            print(f"⚠️ Spread fetch error: {e}")
        return None

    def get_market_regime(self, df) -> str:
        """
        Detect market regime: RANGING, TRENDING_UP, or TRENDING_DOWN.
        Uses SMA slope + price position to determine if market is trending.
        PHASE 7.3: Widened slope window from 5 to 20 candles to reduce flickering.
        """
        if len(df) < self.regime_sma_period + 5:
            return "RANGING"  # Not enough data, assume ranging

        # Calculate 20-period SMA
        sma = df["Close"].rolling(window=self.regime_sma_period).mean()
        current_price = df["Close"].iloc[-1]
        current_sma = sma.iloc[-1]

        # PHASE 7.3: Calculate slope over 20 candles (5 hours) instead of 5 (75 min)
        # Prevents regime from flickering between RANGING and TRENDING
        lookback = min(20, len(sma.dropna()))
        recent_sma = sma.iloc[-lookback:].values
        slope = (recent_sma[-1] - recent_sma[0]) / lookback

        # Calculate price position relative to SMA (percentage)
        price_vs_sma_pct = ((current_price - current_sma) / current_sma) * 100

        # Classify regime using both slope and price position
        # If slope is strong, trust it
        if slope > self.regime_slope_threshold:
            regime = "TRENDING_UP"
        elif slope < -self.regime_slope_threshold:
            regime = "TRENDING_DOWN"
        # If slope is weak but price is clearly above/below SMA, bias toward trend
        elif price_vs_sma_pct > 0.15:  # Price >0.15% above SMA
            regime = "TRENDING_UP"
        elif price_vs_sma_pct < -0.15:  # Price >0.15% below SMA
            regime = "TRENDING_DOWN"
        else:
            regime = "RANGING"

        # PHASE 7.3: Track SMA20/50 cross direction for trend confirmation
        sma50 = df["Close"].rolling(window=50).mean()
        if len(sma50.dropna()) >= 1:
            sma20_val = sma.iloc[-1]
            sma50_val = sma50.iloc[-1]
            self._sma_cross_direction = (
                "BEARISH" if sma20_val < sma50_val else "BULLISH"
            )

            # Count consecutive candles the cross has been in current direction
            cross_count = 0
            for j in range(len(sma50.dropna())):
                idx = -(j + 1)
                if pd.isna(sma.iloc[idx]) or pd.isna(sma50.iloc[idx]):
                    break
                if (
                    self._sma_cross_direction == "BULLISH"
                    and sma.iloc[idx] >= sma50.iloc[idx]
                ):
                    cross_count += 1
                elif (
                    self._sma_cross_direction == "BEARISH"
                    and sma.iloc[idx] < sma50.iloc[idx]
                ):
                    cross_count += 1
                else:
                    break
            self._sma_cross_duration = cross_count
        else:
            self._sma_cross_duration = 0

        # Debug logging for regime detection
        print(
            f"   📊 Regime: {regime} | SMA slope={slope:.4f} ({lookback} candles) | Cross={self._sma_cross_direction} ({self._sma_cross_duration} candles)"
        )

        return regime

    def calculate_position_size(self, stop_pips: float = 20) -> int:
        """Calculate position size based on risk with dynamic pip value.

        PHASE 7.2 FIX: Uses actual USD/JPY price to calculate true pip value
        instead of hardcoded $10/lot which assumed USD/JPY @ 100.00.
        At 155.00, pip value is ~$6.45/lot, not $10.
        """
        balance = self.get_account_balance()
        risk_amount = balance * self.risk_percent

        # Get current price for accurate pip value calculation
        try:
            current_price = self._get_current_mid_price()
        except Exception:
            current_price = 155.0  # Fallback if price unavailable

        # USD/JPY: 1 pip = 0.01 / current_price in USD per unit
        # For 100k units at 155.00: 0.01/155 * 100000 = $6.45 per pip
        pip_value_per_unit = 0.01 / current_price

        # Position size = Risk / (Stop loss pips * pip value per unit)
        position_size = int(risk_amount / (stop_pips * pip_value_per_unit))

        # Clamp to reasonable range
        return max(1000, min(position_size, 100000))

    def _get_current_mid_price(self) -> float:
        """Get current mid price for USD/JPY."""
        from oandapyV20.endpoints.pricing import PricingInfo

        params = {"instruments": self.instrument}
        r = PricingInfo(accountID=self.account_id, params=params)
        self.api.request(r)
        price_data = r.response.get("prices", [{}])[0]
        bid = float(price_data.get("bids", [{}])[0].get("price", 155.0))
        ask = float(price_data.get("asks", [{}])[0].get("price", 155.0))
        return (bid + ask) / 2

    def open_position(self, direction: str, units: int):
        """Open a position."""
        try:
            if direction == "BUY":
                sign = 1
            else:  # SELL
                sign = -1

            order_data = {
                "order": {
                    "type": "MARKET",
                    "instrument": self.instrument,
                    "units": str(sign * units),
                    "stopLossOnFill": {
                        "distance": str(self.stop_loss_pips * 0.01),
                    },
                }
            }

            r = OrderCreate(accountID=self.account_id, data=order_data)
            self.api.request(r)

            # Get fill price
            fill = r.response.get("orderFillTransaction", {})
            price = float(fill.get("price", 0))

            print(f"✅ Opened {direction} {units} units at {price}")
            send_notification(f"🤖 USD/JPY {direction} {units} units at {price}")

            # Save state immediately after trade
            self.save_state()

            # Track trade for daily summary
            self.trades_today.append(
                {
                    "time": datetime.now().isoformat(),
                    "direction": direction,
                    "units": units,
                    "price": price,
                    "type": "OPEN",
                }
            )

            # Log trade to GCS for analysis
            try:
                logger = TradeLogger()
                logger.log_forex_trade(
                    action="OPEN",
                    direction="LONG" if direction == "BUY" else "SHORT",
                    units=units,
                    price=price,
                    account_type=self.mode,
                    signal_data=self.last_signal_data,
                    market_data=self.last_market_data,
                )
            except Exception as log_err:
                print(f"⚠️ Trade log error: {log_err}")

            return True, price
        except Exception as e:
            print(f"❌ Order error: {e}")
            return False, 0

    def calculate_atr(self, candles, period=14):
        """
        Calculate Average True Range for volatility assessment (PHASE 7.1).

        Args:
            candles: List of OANDA candle dicts
            period: ATR period (default 14)

        Returns:
            float: ATR value
        """
        try:
            if len(candles) < period + 1:
                return 0.0

            highs = [float(c["mid"]["h"]) for c in candles]
            lows = [float(c["mid"]["l"]) for c in candles]
            closes = [float(c["mid"]["c"]) for c in candles]

            true_ranges = []
            for i in range(1, len(candles)):
                high_low = highs[i] - lows[i]
                high_close = abs(highs[i] - closes[i - 1])
                low_close = abs(lows[i] - closes[i - 1])
                tr = max(high_low, high_close, low_close)
                true_ranges.append(tr)

            # Average of last 'period' true ranges
            atr = sum(true_ranges[-period:]) / min(period, len(true_ranges))
            return atr
        except Exception as e:
            print(f"⚠️ ATR calculation error: {e}")
            return 0.0

    def close_position(self):
        """Close current position."""
        try:
            # First check what position we actually have
            pos_dir, pos_units, _, _ = self.get_current_position()

            if pos_dir == 0:
                print("ℹ️ No position to close")
                return False, 0

            # Only close the direction we're actually in
            if pos_dir == 1:  # LONG
                data = {"longUnits": "ALL"}
            else:  # SHORT
                data = {"shortUnits": "ALL"}

            r = PositionClose(
                accountID=self.account_id,
                instrument=self.instrument,
                data=data,
            )
            self.api.request(r)

            # Get P/L from response
            if pos_dir == 1:
                pnl = float(r.response.get("longOrderFillTransaction", {}).get("pl", 0))
            else:
                pnl = float(
                    r.response.get("shortOrderFillTransaction", {}).get("pl", 0)
                )

            print(f"✅ Closed position. P/L: ${pnl:+.2f}")
            send_notification(f"🤖 USD/JPY Closed. P/L: ${pnl:+.2f}")

            # Track trade for daily summary
            self.trades_today.append(
                {
                    "time": datetime.now().isoformat(),
                    "direction": "CLOSE",
                    "pnl": pnl,
                    "type": "CLOSE",
                }
            )

            # Log trade to GCS for analysis
            try:
                logger = TradeLogger()
                logger.log_forex_trade(
                    action="CLOSE",
                    direction="LONG" if pos_dir == 1 else "SHORT",
                    units=pos_units,
                    pnl=pnl,
                    account_type=self.mode,
                    signal_data=self.last_signal_data,
                    market_data=self.last_market_data,
                )
            except Exception as log_err:
                print(f"⚠️ Trade log error: {log_err}")

            self.daily_pnl += pnl
            self.scale_in_count = 0  # Reset pyramiding count
            self.save_state()  # Save state after closing position
            return True, pnl
        except Exception as e:
            print(f"❌ Close error: {e}")
            return False, 0

    def run_once(self):
        """Run one iteration of the strategy."""
        # PHASE 7.3: BOT_PAUSED env var support
        if os.getenv("BOT_PAUSED", "false").lower() == "true":
            print("⏸️ BOT PAUSED via environment variable")
            return

        # Sync position
        pos_info = self.get_current_position()
        if pos_info is None:
            print("⚠️ Skipping iteration due to position sync error.")
            return

        pos_dir, pos_units, entry_price, unrealized_pnl = pos_info

        # Reset daily stats if it's a new day
        current_date = datetime.now().date()
        if current_date != self.last_reset_date:
            print(
                f"🌅 New day detected ({current_date}). Resetting daily P/L. (Previous: ${self.daily_pnl:+.2f})"
            )
            self.daily_pnl = 0
            self.trades_today = []
            self.last_reset_date = current_date
            self.peak_profit = 0
            self.trailing_active = False
            self.candle_count = 0  # Reset candle counter daily
            self.save_state()  # Save state after daily reset

        # WEEKEND GAP PROTECTION: Close positions before Friday market close
        et = pytz.timezone("America/New_York")
        now_et = datetime.now(et)
        if now_et.weekday() == 4 and now_et.hour >= 16 and pos_dir != 0:
            print("🏖️ WEEKEND PROTECTION: Closing position before Friday market close")
            self.close_position()
            send_notification("🏖️ USD/JPY closed before weekend gap risk")
            return

        # Get candles
        df = self.get_candles(count=50)
        if df.empty:
            print("⚠️ No candle data")
            return

        # Get signal
        signal_data = self.strategy.get_signal(df, len(df) - 1)
        signal = signal_data["signal"]
        confidence = signal_data["confidence"]
        reason = signal_data.get("reason", "")

        current_price = df.iloc[-1]["Close"]
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Store metadata for trade logging
        self.last_signal_data = {
            "rsi": signal_data.get("rsi"),
            "bb_position": signal_data.get("bb_position"),
            "confidence": confidence,
            "reason": reason,
        }

        # Calculate ATR for market context
        if len(df) >= 14:
            high_low = df["High"] - df["Low"]
            atr = high_low.rolling(window=14).mean().iloc[-1]
        else:
            atr = None

        self.last_market_data = {
            "current_price": current_price,
            "atr": atr,
            "spread": self.get_current_spread(),
        }

        # PHASE 7.3: Volatility pause - skip ALL entries if ATR is extremely high
        if self.use_volatility_filter and pos_dir == 0:
            if len(df) >= 50:
                atr_current = (df["High"] - df["Low"]).tail(14).mean()
                atr_avg = (df["High"] - df["Low"]).tail(50).mean()
                if atr_current > atr_avg * self.volatility_factor:
                    print(
                        f"   ⚠️ VOLATILITY PAUSE: ATR {atr_current:.4f} > {self.volatility_factor}x avg {atr_avg:.4f}"
                    )
                    return

        # Detect market regime (trending or ranging)
        if self.use_regime_filter:
            self.current_regime = self.get_market_regime(df)
            regime_emoji = {
                "TRENDING_UP": "📈",
                "TRENDING_DOWN": "📉",
                "RANGING": "↔️",
            }.get(self.current_regime, "?")
        else:
            self.current_regime = "RANGING"
            regime_emoji = "↔️"

        # In trending markets, use trend-following signals instead of mean reversion
        if self.current_regime in ("TRENDING_UP", "TRENDING_DOWN"):
            trend_signal = self.strategy.get_trend_signal(
                df, len(df) - 1, self.current_regime
            )
            if trend_signal["signal"] != "HOLD":
                signal = trend_signal["signal"]
                confidence = trend_signal["confidence"]
                reason = trend_signal.get("reason", "")
                # Update metadata
                self.last_signal_data = {
                    "rsi": trend_signal.get("rsi"),
                    "bb_position": trend_signal.get("bb_position"),
                    "confidence": confidence,
                    "reason": reason,
                }

        print(
            f"[{timestamp}] Price: {current_price:.3f} | {regime_emoji} {self.current_regime} | Signal: {signal} ({confidence}%) | {reason}"
        )

        # Show unrealized P/L if in position
        if pos_dir != 0:
            trailing_status = " 🎯 TRAILING" if self.trailing_active else ""
            print(
                f"   📊 Position: {'LONG' if pos_dir == 1 else 'SHORT'} | P/L: ${unrealized_pnl:+.2f}{trailing_status}"
            )
            if self.trailing_active:
                print(
                    f"   📈 Peak: ${self.peak_profit:+.2f} | Trail trigger: ${self.peak_profit - self.trailing_amount:+.2f}"
                )

        # *** TRAILING PROFIT STOP ***
        if pos_dir != 0:
            # Activate trailing stop when profit >= target
            if unrealized_pnl >= self.daily_target and not self.trailing_active:
                self.trailing_active = True
                self.peak_profit = unrealized_pnl
                print(
                    f"🎯 TRAILING STOP ACTIVATED! Profit: ${unrealized_pnl:+.2f} >= ${self.daily_target}"
                )
                send_notification(
                    f"🎯 USD/JPY Trailing stop activated at ${unrealized_pnl:+.2f}"
                )

            # Update peak profit if still rising
            if self.trailing_active and unrealized_pnl > self.peak_profit:
                self.peak_profit = unrealized_pnl
                print(f"📈 NEW PEAK PROFIT: ${self.peak_profit:+.2f}")

            # Close if profit drops below peak - trailing amount
            if self.trailing_active:
                trailing_trigger = self.peak_profit - self.trailing_amount
                if unrealized_pnl <= trailing_trigger:
                    print(
                        f"🔒 TRAILING STOP TRIGGERED! P/L: ${unrealized_pnl:+.2f} <= ${trailing_trigger:+.2f}"
                    )
                    success, realized_pnl = self.close_position()
                    if success:
                        self.daily_pnl += realized_pnl
                        peak_before_close = self.peak_profit  # Save peak before reset
                        self.trailing_active = False
                        self.peak_profit = 0
                        print(
                            f"💰 Locked in ${realized_pnl:+.2f} (Peak was ${peak_before_close:+.2f})"
                        )
                        send_notification(
                            f"🔒 USD/JPY Trailing stop! Closed for ${realized_pnl:+.2f}"
                        )
                    return

        # PHASE 7.2: Removed daily winning target - maximize profits on good days!
        # Only the $200 loss limit (max_daily_loss) stops trading now.
        # Rationale: We have asymmetric risk with -$200 floor, so let winners run.
        # Old code:
        # if self.daily_pnl >= self.daily_target:
        #     print(f"🎯 Daily target reached! P/L: ${self.daily_pnl:+.2f}")
        #     return

        # Check daily limits (Realized + Unrealized)
        total_pnl = self.daily_pnl + unrealized_pnl
        if total_pnl <= self.max_daily_loss:
            print(
                f"🛑 Daily loss limit hit! P/L: ${total_pnl:+.2f} (Max: ${self.max_daily_loss})"
            )
            if pos_dir != 0:
                print("⚠️ Closing open position due to loss limit.")
                self.close_position()
            return

        # Check for hard Stop Loss (Pip-based)
        if pos_dir != 0:
            pip_size = 0.01  # USD/JPY pip size
            if pos_dir == 1:  # LONG
                drawdown_pips = (entry_price - current_price) / pip_size
            else:  # SHORT
                drawdown_pips = (current_price - entry_price) / pip_size

            if drawdown_pips >= self.stop_loss_pips:
                print(
                    f"🛑 STOP LOSS HIT! Drawdown: {drawdown_pips:.1f} pips (Max: {self.stop_loss_pips})"
                )
                self.close_position()
                return

        # PROFIT TARGET: Lock in gains at target
        if pos_dir != 0 and self.use_take_profit:
            pip_size = 0.01  # USD/JPY pip size
            if pos_dir == 1:  # LONG
                profit_pips = (current_price - entry_price) / pip_size
            else:  # SHORT
                profit_pips = (entry_price - current_price) / pip_size

            if profit_pips >= self.take_profit_pips:
                print(
                    f"🎯 PROFIT TARGET HIT! Profit: {profit_pips:.1f} pips (Target: {self.take_profit_pips})"
                )
                success, realized_pnl = self.close_position()
                if success:
                    self.daily_pnl += realized_pnl
                    send_notification(
                        f"🎯 USD/JPY Profit target hit! +{profit_pips:.1f} pips (${realized_pnl:+.2f})"
                    )
                return

        # Increment candle counter
        self.candle_count += 1

        # *** PROBE ENTRY MANAGEMENT ***
        # Check if we have a probe position that needs confirmation or timeout
        if self.is_probe_position and pos_dir != 0:
            candles_since_entry = self.candle_count - self.probe_entry_candle

            # Check for confirmation (scale up to full size)
            if unrealized_pnl >= self.probe_confirm_profit:
                base_units = self.calculate_position_size()
                remaining_units = int(base_units * (1 - self.probe_size_pct))
                direction = "BUY" if pos_dir == 1 else "SELL"
                print(
                    f"✅ PROBE CONFIRMED! Scaling up with {remaining_units} units (+${unrealized_pnl:.2f})"
                )
                self.open_position(direction, remaining_units)
                self.is_probe_position = False  # Now it's a full position
                send_notification(
                    f"✅ USD/JPY Probe confirmed! Scaled to full size (+${unrealized_pnl:.2f})"
                )

            # Check for timeout (always close probe if not confirmed)
            elif candles_since_entry >= self.probe_max_candles:
                print(
                    f"⏱️ PROBE TIMEOUT! Closing after {candles_since_entry} candles (P/L: ${unrealized_pnl:+.2f})"
                )
                self.close_position()
                self.is_probe_position = False
                send_notification(
                    f"⏱️ USD/JPY Probe timed out. Closed for ${unrealized_pnl:+.2f}"
                )
                return

        # Execute trades
        # SPREAD FILTER: Skip entries during wide spreads (volatile periods)
        current_spread = self.get_current_spread()
        if current_spread > 3.0 and signal in ["BUY", "SELL"]:
            print(
                f"   ⚠️ SPREAD FILTER: Skipping {signal} signal due to wide spread ({current_spread:.1f} pips)"
            )
            return

        if signal == "BUY" and confidence >= 50:
            # PHASE 7.3: Regime filter + SMA cross direction
            # Block BUY if regime is TRENDING_DOWN OR SMA cross is bearish
            if self.use_regime_filter and pos_dir != 1:
                if self.current_regime == "TRENDING_DOWN":
                    print(
                        "   ⚠️ REGIME FILTER: Skipping BUY signal (market trending DOWN)"
                    )
                    return
                if getattr(self, "_sma_cross_direction", "") == "BEARISH":
                    print(
                        "   ⚠️ SHORT-ONLY MODE: Blocking BUY (SMA20 < SMA50 = bearish cross)"
                    )
                    return

            if pos_dir == -1:  # Close short first
                self.close_position()
                self.scale_in_count = 0  # Reset scale-in count
                self.is_probe_position = False

            if pos_dir != 1:  # Open long if not already
                base_units = self.calculate_position_size()
                if self.use_probe_entry:
                    # Probe entry: start with reduced size
                    probe_units = int(base_units * self.probe_size_pct)
                    print(
                        f"🔍 PROBE ENTRY: Opening LONG with {probe_units} units (40% size)"
                    )
                    self.open_position("BUY", probe_units)
                    self.is_probe_position = True
                    self.probe_entry_candle = self.candle_count
                    send_notification(
                        f"🔍 USD/JPY Probe LONG: {probe_units} units (40% size)"
                    )
                else:
                    # Standard full-size entry
                    self.open_position("BUY", base_units)
                self.scale_in_count = 0
            elif (
                pos_dir == 1 and not self.is_probe_position
            ):  # Already long (full) - consider pyramiding
                # NO-AVERAGING-DOWN: Must be in profit to add
                if unrealized_pnl < 0:
                    print(
                        f"   ⚠️ Skipping Pyramid: Current position underwater (${unrealized_pnl:+.2f})"
                    )
                    return

                if (
                    unrealized_pnl >= self.min_profit_to_add
                    and self.scale_in_count < self.max_scale_ins
                ):
                    # Add to winning position
                    base_units = self.calculate_position_size()
                    add_units = int(base_units * self.scale_in_size_pct)
                    print(
                        f"📈 PYRAMIDING: Adding {add_units} units (scale-in #{self.scale_in_count + 1})"
                    )
                    self.open_position("BUY", add_units)
                    self.scale_in_count += 1
                    send_notification(
                        f"📈 USD/JPY Pyramid: Added {add_units} units (P/L: ${unrealized_pnl:+.2f})"
                    )

        elif signal == "SELL" and confidence >= 50:
            # PHASE 7.3: Regime filter + SMA cross direction
            # Block SELL if regime is TRENDING_UP OR SMA cross is bullish
            if self.use_regime_filter and pos_dir != -1:
                if self.current_regime == "TRENDING_UP":
                    print(
                        "   ⚠️ REGIME FILTER: Skipping SELL signal (market trending UP)"
                    )
                    return
                if getattr(self, "_sma_cross_direction", "") == "BULLISH":
                    print(
                        "   ⚠️ LONG-ONLY MODE: Blocking SELL (SMA20 > SMA50 = bullish cross)"
                    )
                    return

            if pos_dir == 1:  # Close long first
                self.close_position()
                self.scale_in_count = 0  # Reset scale-in count
                self.is_probe_position = False

            if pos_dir != -1:  # Open short if not already
                base_units = self.calculate_position_size()
                if self.use_probe_entry:
                    # Probe entry: start with reduced size
                    probe_units = int(base_units * self.probe_size_pct)
                    print(
                        f"🔍 PROBE ENTRY: Opening SHORT with {probe_units} units (40% size)"
                    )
                    self.open_position("SELL", probe_units)
                    self.is_probe_position = True
                    self.probe_entry_candle = self.candle_count
                    send_notification(
                        f"🔍 USD/JPY Probe SHORT: {probe_units} units (40% size)"
                    )
                else:
                    # Standard full-size entry
                    self.open_position("SELL", base_units)
                self.scale_in_count = 0
            elif (
                pos_dir == -1 and not self.is_probe_position
            ):  # Already short (full) - consider pyramiding
                # NO-AVERAGING-DOWN: Must be in profit to add
                if unrealized_pnl < 0:
                    print(
                        f"   ⚠️ Skipping Pyramid: Current position underwater (${unrealized_pnl:+.2f})"
                    )
                    return

                if (
                    unrealized_pnl >= self.min_profit_to_add
                    and self.scale_in_count < self.max_scale_ins
                ):
                    # Add to winning position
                    base_units = self.calculate_position_size()
                    add_units = int(base_units * self.scale_in_size_pct)
                    print(
                        f"📉 PYRAMIDING: Adding {add_units} units (scale-in #{self.scale_in_count + 1})"
                    )
                    self.open_position("SELL", add_units)
                    self.scale_in_count += 1
                    send_notification(
                        f"📉 USD/JPY Pyramid: Added {add_units} units (P/L: ${unrealized_pnl:+.2f})"
                    )

    def _send_daily_summary(self):
        """Send daily trading summary at market close."""
        try:
            balance = self.get_account_balance()
            pnl = (
                balance - self.start_balance
                if self.start_balance > 0
                else self.daily_pnl
            )
            pnl_pct = (pnl / self.start_balance * 100) if self.start_balance > 0 else 0

            trades_count = len(self.trades_today)

            emoji = "📈" if pnl >= 0 else "📉"
            msg = (
                f"{emoji} USD/JPY Daily Summary\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"Trades: {trades_count}\n"
                f"Start: ${self.start_balance:,.2f}\n"
                f"End: ${balance:,.2f}\n"
                f"P/L: ${pnl:+,.2f} ({pnl_pct:+.2f}%)\n"
                f"━━━━━━━━━━━━━━━━━━"
            )
            send_notification(msg)
            print(f"📊 Daily summary sent: P/L ${pnl:+,.2f}")

            # Reset for next day
            self.trades_today = []
            self.start_balance = balance
            self.daily_pnl = 0

        except Exception as e:
            print(f"⚠️ Daily summary failed: {e}")

    def run(self, interval_minutes: int = 15):
        """Run the bot continuously."""
        print(f"🚀 Starting bot (checking every {interval_minutes} minutes)...")

        import pytz

        et = pytz.timezone("America/New_York")

        while True:
            try:
                # Check if forex market is open
                market_open, reason = is_forex_market_open()
                if not market_open:
                    print(f"\n🌙 {reason} - sleeping 30 min")
                    time.sleep(30 * 60)  # Sleep 30 min when market closed
                    continue

                # Check for daily summary time (5pm ET on weekdays)
                now_et = datetime.now(et)
                if now_et.hour == self.daily_summary_hour and now_et.weekday() < 5:
                    today = now_et.date()
                    if self.last_summary_date != today:
                        self._send_daily_summary()
                        self.last_summary_date = today

                # Run trading logic
                self.run_once()

            except Exception as e:
                print(f"❌ Error: {e}")

            # Wait for next candle
            time.sleep(interval_minutes * 60)


def main():
    parser = argparse.ArgumentParser(description="USD/JPY Mean Reversion Bot")
    parser.add_argument("--mode", "-m", choices=["paper", "live"], default="paper")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument(
        "--interval", "-i", type=int, default=15, help="Check interval in minutes"
    )
    args = parser.parse_args()

    bot = USDJPYMeanReversionBot(mode=args.mode)

    if args.once:
        bot.run_once()
    else:
        bot.run(interval_minutes=args.interval)


if __name__ == "__main__":
    main()
