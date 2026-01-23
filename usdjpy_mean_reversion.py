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
        self.api_key = os.getenv("OANDA_API_KEY")
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
        self.daily_target = 50  # $50 - triggers trailing stop
        self.trailing_amount = 20  # $20 - close if profit drops this much from peak
        self.daily_pnl = 0
        self.max_daily_loss = -200  # Stop trading if down $200 (including open trades)
        self.stop_loss_pips = 50  # Hard stop loss in pips

        # Pyramiding / Scale-in settings
        self.max_scale_ins = 3  # Max positions to add (total 4 including initial)
        self.scale_in_count = 0  # Current number of scale-ins
        self.min_profit_to_add = 25  # Must be $25+ in profit to add
        self.scale_in_size_pct = 0.5  # Scale-ins are 50% of initial size

        # Probe Entry Settings (Start small, confirm before full size)
        self.use_probe_entry = True  # Enable probe mode
        self.probe_size_pct = 0.40  # Initial entry is 40% of full size
        self.probe_confirm_profit = 25  # Need +$25 to confirm and scale up
        self.probe_max_candles = 3  # Exit probe if not confirmed in 3 candles
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
        self.regime_slope_threshold = 0.03  # Min slope per candle to call it trending
        self.current_regime = "RANGING"  # RANGING, TRENDING_UP, TRENDING_DOWN

        # Trade metadata for logging
        self.last_signal_data = {}  # RSI, BB position, confidence, reason
        self.last_market_data = {}  # Current price, ATR, spread

        # Performance tracking
        self.trades_today = []  # List of trades for daily summary
        self.start_balance = 0  # Set on startup
        self.last_summary_date = None  # Track when last summary was sent
        self.daily_summary_hour = 17  # Send daily summary at 5pm ET (market close)

        print(f"\n{'=' * 60}")
        print("🤖 USD/JPY MEAN REVERSION BOT")
        print(f"{'=' * 60}")
        print(f"Mode: {mode.upper()}")
        print(f"Account: {self.account_id}")
        print(f"Instrument: {self.instrument}")
        print(f"Timeframe: {self.granularity}")
        print(f"Risk per trade: {self.risk_percent * 100}%")
        print(f"Daily target: ${self.daily_target}")
        print(f"{'=' * 60}\n")

        # Sync positions and send startup alert
        self._sync_positions()
        self._send_startup_alert()

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
        """Get current position for USD_JPY."""
        try:
            r = PositionDetails(accountID=self.account_id, instrument=self.instrument)
            self.api.request(r)

            pos = r.response["position"]
            long_units = int(pos["long"]["units"])
            short_units = int(pos["short"]["units"])
            long_pnl = float(pos["long"].get("unrealizedPL", 0))
            short_pnl = float(pos["short"].get("unrealizedPL", 0))

            if long_units > 0:
                return 1, long_units, float(pos["long"]["averagePrice"]), long_pnl
            elif short_units != 0:
                return (
                    -1,
                    abs(short_units),
                    float(pos["short"]["averagePrice"]),
                    short_pnl,
                )
            else:
                return 0, 0, 0, 0
        except:
            return 0, 0, 0, 0

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
        Uses SMA slope to determine if market is trending.
        """
        if len(df) < self.regime_sma_period + 5:
            return "RANGING"  # Not enough data, assume ranging

        # Calculate 20-period SMA
        sma = df["Close"].rolling(window=self.regime_sma_period).mean()

        # Calculate slope over last 5 candles (5 * 15min = 1.25 hours)
        recent_sma = sma.iloc[-5:].values
        slope = (recent_sma[-1] - recent_sma[0]) / 5  # Average change per candle

        # Classify regime
        if slope > self.regime_slope_threshold:
            return "TRENDING_UP"
        elif slope < -self.regime_slope_threshold:
            return "TRENDING_DOWN"
        else:
            return "RANGING"

    def calculate_position_size(self, stop_pips: float = 20) -> int:
        """Calculate position size based on risk."""
        balance = self.get_account_balance()
        risk_amount = balance * self.risk_percent

        # For USD/JPY: 1 pip = ~$10 per standard lot
        pip_value = 10
        units_per_lot = 100000

        # Position size = Risk / (Stop loss pips * pip value per unit)
        position_size = int(risk_amount / (stop_pips * (pip_value / units_per_lot)))

        # Clamp to reasonable range
        return max(1000, min(position_size, 100000))

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
                }
            }

            r = OrderCreate(accountID=self.account_id, data=order_data)
            self.api.request(r)

            # Get fill price
            fill = r.response.get("orderFillTransaction", {})
            price = float(fill.get("price", 0))

            print(f"✅ Opened {direction} {units} units at {price}")
            send_notification(f"🤖 USD/JPY {direction} {units} units at {price}")

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
            return True, pnl
        except Exception as e:
            print(f"❌ Close error: {e}")
            return False, 0

    def run_once(self):
        """Run one iteration of the strategy."""
        # Get current position and unrealized P/L
        pos_dir, pos_units, entry_price, unrealized_pnl = self.get_current_position()

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
                        self.trailing_active = False
                        self.peak_profit = 0
                        print(
                            f"💰 Locked in ${realized_pnl:+.2f} (Peak was ${self.peak_profit:+.2f})"
                        )
                        send_notification(
                            f"🔒 USD/JPY Trailing stop! Closed for ${realized_pnl:+.2f}"
                        )
                    return

        # Check daily target (Realized P/L)
        if self.daily_pnl >= self.daily_target:
            print(f"🎯 Daily target reached! P/L: ${self.daily_pnl:+.2f}")
            return

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

            # Check for timeout (exit if not profitable after max candles)
            elif candles_since_entry >= self.probe_max_candles:
                if unrealized_pnl < 0:
                    print(
                        f"⏱️ PROBE TIMEOUT! Closing after {candles_since_entry} candles (P/L: ${unrealized_pnl:+.2f})"
                    )
                    self.close_position()
                    self.is_probe_position = False
                    send_notification(
                        f"⏱️ USD/JPY Probe timed out. Closed for ${unrealized_pnl:+.2f}"
                    )
                    return
                else:
                    # Profitable but not confirmed - keep holding, disable timeout
                    print(f"📊 Probe profitable but not confirmed. Holding...")
                    self.is_probe_position = False  # Treat as regular position now

        # Execute trades
        if signal == "BUY" and confidence >= 50:
            # REGIME FILTER: Skip BUY in downtrend (counter-trend trade)
            if (
                self.use_regime_filter
                and self.current_regime == "TRENDING_DOWN"
                and pos_dir != 1
            ):
                print(f"   ⚠️ REGIME FILTER: Skipping BUY signal (market trending DOWN)")
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
            # REGIME FILTER: Skip SELL in uptrend (counter-trend trade)
            if (
                self.use_regime_filter
                and self.current_regime == "TRENDING_UP"
                and pos_dir != -1
            ):
                print(f"   ⚠️ REGIME FILTER: Skipping SELL signal (market trending UP)")
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
