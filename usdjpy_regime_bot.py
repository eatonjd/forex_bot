#!/usr/bin/env python3
"""
USD/JPY Regime-Switching Trading Bot

Detects market regime and deploys the appropriate strategy:
  - MEAN_REVERSION regime → Bollinger Bands + RSI (calm markets)
  - BREAKOUT regime → Donchian Channels + ATR + ADX (volatile markets)
  - TRANSITIONAL → Manage existing positions only, no new entries

Instruments:
  - USD/JPY: Both strategies
  - XAU/USD: Breakout only (too volatile for mean reversion on small accounts)

Uses simulated $5K balance for position sizing regardless of account size.

Author: Trading Bot Team
Created: 2026-04-19
"""

import os
import sys
import time
import json
import logging
from datetime import datetime
from pathlib import Path
import pytz

sys.path.insert(0, str(Path(__file__).parent))

from oandapyV20 import API
from oandapyV20.endpoints.accounts import AccountSummary
from oandapyV20.endpoints.instruments import InstrumentsCandles
from oandapyV20.endpoints.orders import OrderCreate
from oandapyV20.endpoints.positions import PositionDetails, PositionClose
from oandapyV20.endpoints.pricing import PricingInfo

import pandas as pd

from utils.mean_reversion import MeanReversionStrategy
from utils.volatility_breakout import VolatilityBreakoutStrategy
from utils.regime_detector import RegimeDetector, RegimeState
from utils.trade_logger import TradeLogger


def is_forex_market_open() -> tuple:
    """Check if forex market is open (Sunday 5pm - Friday 5pm ET)."""
    et = pytz.timezone("America/New_York")
    now = datetime.now(et)
    weekday = now.weekday()
    hour = now.hour

    if weekday == 4 and hour >= 17:
        return False, "Market closed (Friday evening)"
    if weekday == 5:
        return False, "Market closed (Saturday)"
    if weekday == 6 and hour < 17:
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
            notifier._send(msg, title="Regime Bot")
        except Exception as e:
            print(f"⚠️ Notification failed: {e}")
    print(f"📢 {msg}")


class USDJPYRegimeBot:
    """
    Regime-switching bot that uses mean reversion in calm markets
    and volatility breakout in chaotic markets.
    """

    # Per-instrument configuration
    INSTRUMENT_CONFIG = {
        "USD_JPY": {
            "pip_size": 0.01,
            "pip_value_fn": "jpy",
            "max_spread": 4.0,
            "strategies": ["MEAN_REVERSION", "BREAKOUT"],
        },
        "XAU_USD": {
            "pip_size": 0.01,
            "pip_value_fn": "direct",
            "max_spread": 50.0,
            "strategies": ["BREAKOUT"],  # Gold: breakout only
        },
    }

    def __init__(self, mode: str = "paper"):
        self.mode = mode
        self.granularity = "M15"

        # Account setup — use -002 practice account for regime bot
        if mode == "paper":
            self.api_key = os.getenv("OANDA_API_KEY")
            self.account_id = os.getenv("OANDA_ACCOUNT_ID_VOL", "101-001-38009813-002")
            self.environment = "practice"
        else:
            self.api_key = os.getenv("OANDA_API_KEY_LIVE")
            self.account_id = os.getenv("OANDA_ACCOUNT_ID_LIVE")
            self.environment = "live"

        self.api = API(access_token=self.api_key, environment=self.environment)

        # Instruments
        self.instruments = ["USD_JPY", "XAU_USD"]

        # Strategy engines
        self.mr_strategy = MeanReversionStrategy(
            bb_period=20, bb_std=2.0,
            rsi_period=14, rsi_oversold=30, rsi_overbought=70,
        )
        self.vol_strategy = VolatilityBreakoutStrategy(
            donchian_period=20, atr_period=14,
            atr_expansion_factor=1.5, adx_period=14,
            adx_threshold=25.0, volume_factor=1.2,
        )

        # Regime detector
        self.regime_detector = RegimeDetector(
            atr_period=14, atr_avg_lookback=50,
            adx_period=14, sma_fast=20, sma_slow=50,
            confirm_candles=2, cooldown_candles=2,
        )

        # Simulated balance for position sizing
        self.simulated_balance = 5000.0

        # Risk management
        self.risk_percent = 0.015  # 1.5% per trade
        self.max_daily_loss = -150.0
        self.daily_pnl = 0.0

        # MR-specific settings
        self.mr_stop_loss_pips = 20
        self.mr_trailing_trigger = 20.0  # Activate trailing at $20
        self.mr_trailing_amount = 10.0   # Trail by $10
        self.mr_max_holding_hours = 24

        # Breakout-specific settings
        self.vol_stop_atr_mult = 1.5
        self.vol_trailing_atr_mult = 2.0
        self.vol_trailing_trigger = 25.0
        self.vol_max_holding_hours = 8

        # Per-instrument state
        self._instrument_state = {}
        for inst in self.instruments:
            self._instrument_state[inst] = {
                "entry_time": None,
                "trailing_active": False,
                "peak_profit": 0,
                "stop_distance": 0,
                "trail_distance": 0,
                "entry_regime": None,  # Which regime was active at entry
            }

        # Metadata
        self.last_signal_data = {}
        self.last_market_data = {}
        self.last_regime_state = None
        self.trades_today = []
        self.last_reset_date = datetime.now().date()

        # State file
        self.state_file = "bot_state_regime.json"

        # Logging
        self.logger = logging.getLogger("regime_bot")
        self.logger.setLevel(logging.INFO)

        self.load_state()
        self._sync_positions()
        self._send_startup_alert()

    # ─── State Persistence ───────────────────────────────────────

    def save_state(self):
        """Save bot state to local + GCS."""
        try:
            state = {
                "daily_pnl": self.daily_pnl,
                "last_reset_date": str(self.last_reset_date),
                "instrument_state": {},
                "regime_detector": self.regime_detector.get_state_dict(),
                "last_update": datetime.now().isoformat(),
            }
            for inst, istate in self._instrument_state.items():
                state["instrument_state"][inst] = {
                    "entry_time": istate["entry_time"].isoformat() if istate["entry_time"] else None,
                    "trailing_active": istate["trailing_active"],
                    "peak_profit": istate["peak_profit"],
                    "entry_regime": istate["entry_regime"],
                }

            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)

            if os.getenv("USE_CLOUD_STORAGE", "").lower() == "true":
                from google.cloud import storage
                client = storage.Client()
                bucket = client.bucket(os.getenv("GCS_BUCKET_NAME", "forex-bot-state"))
                blob = bucket.blob(f"state/{self.state_file}")
                blob.upload_from_string(json.dumps(state, indent=2), content_type="application/json")
        except Exception as e:
            print(f"⚠️ State save error: {e}")

    def load_state(self):
        """Load bot state from GCS or local."""
        try:
            state = None
            if os.getenv("USE_CLOUD_STORAGE", "").lower() == "true":
                try:
                    from google.cloud import storage
                    client = storage.Client()
                    bucket = client.bucket(os.getenv("GCS_BUCKET_NAME", "forex-bot-state"))
                    blob = bucket.blob(f"state/{self.state_file}")
                    if blob.exists():
                        state = json.loads(blob.download_as_text())
                        print(f"🔄 State loaded from GCS")
                except Exception as e:
                    print(f"⚠️ GCS state load: {e}")

            if not state and os.path.exists(self.state_file):
                with open(self.state_file, "r") as f:
                    state = json.load(f)
                    print(f"🔄 State loaded from local")

            if state:
                self.daily_pnl = state.get("daily_pnl", 0)
                for inst, idata in state.get("instrument_state", {}).items():
                    if inst in self._instrument_state:
                        et = idata.get("entry_time")
                        self._instrument_state[inst]["entry_time"] = datetime.fromisoformat(et) if et else None
                        self._instrument_state[inst]["trailing_active"] = idata.get("trailing_active", False)
                        self._instrument_state[inst]["peak_profit"] = idata.get("peak_profit", 0)
                        self._instrument_state[inst]["entry_regime"] = idata.get("entry_regime")
                rd_state = state.get("regime_detector")
                if rd_state:
                    self.regime_detector.load_state_dict(rd_state)
        except Exception as e:
            print(f"⚠️ State load error: {e}")

    # ─── Account & Market Data ───────────────────────────────────

    def _sync_positions(self):
        """Sync with existing OANDA positions."""
        for inst in self.instruments:
            try:
                pos_info = self.get_current_position(inst)
                if pos_info is None:
                    print(f"⚠️ [{inst}] Sync error: failed to get position")
                    continue
                    
                pos_dir, pos_units, entry_price, upl = pos_info
                if pos_dir != 0:
                    d = "LONG" if pos_dir == 1 else "SHORT"
                    print(f"📍 [{inst}] {d} {pos_units:,}u @ {entry_price:.3f} | UPL: ${upl:+.2f}")
                else:
                    print(f"📍 [{inst}] Flat")
            except Exception as e:
                print(f"⚠️ [{inst}] Sync error: {e}")

    def _send_startup_alert(self):
        """Send startup notification."""
        try:
            balance = self.get_account_balance()
            regime = self.regime_detector._current_regime
            send_notification(
                f"🚀 REGIME BOT Started\n"
                f"Mode: {self.mode.upper()}\n"
                f"Balance: ${balance:,.2f} (sim ${self.simulated_balance:,.0f})\n"
                f"Instruments: {', '.join(self.instruments)}\n"
                f"Current Regime: {regime}"
            )
        except Exception as e:
            print(f"⚠️ Startup alert failed: {e}")

    def get_account_balance(self) -> float:
        try:
            r = AccountSummary(accountID=self.account_id)
            self.api.request(r)
            return float(r.response["account"]["balance"])
        except Exception as e:
            print(f"Error getting balance: {e}")
            return 0

    def get_candles(self, instrument: str, count: int = 100) -> pd.DataFrame:
        """Fetch M15 candles for an instrument."""
        try:
            params = {"count": count, "granularity": self.granularity}
            r = InstrumentsCandles(instrument=instrument, params=params)
            self.api.request(r)
            data = []
            for c in r.response["candles"]:
                if c["complete"]:
                    data.append({
                        "Date": c["time"],
                        "Open": float(c["mid"]["o"]),
                        "High": float(c["mid"]["h"]),
                        "Low": float(c["mid"]["l"]),
                        "Close": float(c["mid"]["c"]),
                        "Volume": int(c["volume"]),
                    })
            return pd.DataFrame(data)
        except Exception as e:
            print(f"Error fetching candles for {instrument}: {e}")
            return pd.DataFrame()

    def get_current_position(self, instrument: str) -> tuple:
        """Get position for an instrument: (direction, units, avg_price, upl)."""
        try:
            r = PositionDetails(accountID=self.account_id, instrument=instrument)
            self.api.request(r)
            pos = r.response["position"]
            long_u = int(pos["long"]["units"])
            short_u = int(pos["short"]["units"])
            upl = float(pos.get("unrealizedPL", 0))
            if long_u > 0:
                return 1, long_u, float(pos["long"].get("averagePrice", 0)), upl
            elif short_u != 0:
                return -1, abs(short_u), float(pos["short"].get("averagePrice", 0)), upl
            return 0, 0, 0, 0
        except Exception as e:
            # If the position doesn't exist, OANDA might return 404 Position not found
            if "not found" in str(e).lower() or "not_found" in str(e).lower():
                return 0, 0, 0, 0
            print(f"⚠️ get_position error for {instrument}: {e}")
            return None

    def get_current_spread(self, instrument: str) -> float:
        """Get bid/ask spread in pips."""
        try:
            cfg = self.INSTRUMENT_CONFIG[instrument]
            params = {"instruments": instrument}
            r = PricingInfo(accountID=self.account_id, params=params)
            self.api.request(r)
            if r.response["prices"]:
                pd_ = r.response["prices"][0]
                bid = float(pd_["bids"][0]["price"])
                ask = float(pd_["asks"][0]["price"])
                return round((ask - bid) / cfg["pip_size"], 2)
        except:
            pass
        return None

    def _get_mid_price(self, instrument: str) -> float:
        params = {"instruments": instrument}
        r = PricingInfo(accountID=self.account_id, params=params)
        self.api.request(r)
        pd_ = r.response.get("prices", [{}])[0]
        bid = float(pd_.get("bids", [{}])[0].get("price", 155.0))
        ask = float(pd_.get("asks", [{}])[0].get("price", 155.0))
        return (bid + ask) / 2

    # ─── Position Sizing ─────────────────────────────────────────

    def calculate_position_size(self, instrument: str, stop_distance_price: float) -> int:
        """Position size based on simulated $5K balance."""
        risk_amount = self.simulated_balance * self.risk_percent
        cfg = self.INSTRUMENT_CONFIG[instrument]
        pip_size = cfg["pip_size"]

        try:
            price = self._get_mid_price(instrument)
        except:
            price = 155.0 if instrument == "USD_JPY" else 2300.0

        if cfg["pip_value_fn"] == "jpy":
            pip_value_per_unit = pip_size / price
        else:
            pip_value_per_unit = pip_size

        stop_pips = stop_distance_price / pip_size
        size = int(risk_amount / (stop_pips * pip_value_per_unit))

        if instrument == "XAU_USD":
            return max(1, min(size, 100))
        return max(1000, min(size, 100000))

    # ─── Order Execution ─────────────────────────────────────────

    def open_position(self, instrument: str, direction: str, units: int, stop_dist: float, regime: str):
        """Open a position with ATR or fixed stop."""
        try:
            sign = 1 if direction == "BUY" else -1
            cfg = self.INSTRUMENT_CONFIG[instrument]

            order_data = {
                "order": {
                    "type": "MARKET",
                    "instrument": instrument,
                    "units": str(sign * units),
                    "stopLossOnFill": {"distance": f"{stop_dist:.5f}"},
                }
            }
            r = OrderCreate(accountID=self.account_id, data=order_data)
            self.api.request(r)

            fill = r.response.get("orderFillTransaction", {})
            price = float(fill.get("price", 0))

            istate = self._instrument_state[instrument]
            istate["entry_time"] = datetime.now()
            istate["entry_regime"] = regime

            sl_pips = stop_dist / cfg["pip_size"]
            print(f"✅ [{instrument}] {direction} {units}u @ {price} | SL: {sl_pips:.0f}p | Regime: {regime}")
            send_notification(
                f"🎯 {instrument} {direction} {units}u @ {price}\n"
                f"SL: {sl_pips:.0f} pips | Regime: {regime}"
            )

            self.save_state()
            self.trades_today.append({
                "time": datetime.now().isoformat(),
                "instrument": instrument,
                "direction": direction,
                "units": units,
                "price": price,
                "regime": regime,
                "type": "OPEN",
            })

            try:
                logger = TradeLogger()
                logger.log_forex_trade(
                    action="OPEN",
                    direction="LONG" if direction == "BUY" else "SHORT",
                    units=units, price=price,
                    account_type=self.mode,
                    signal_data=self.last_signal_data,
                    market_data=self.last_market_data,
                )
            except Exception as e:
                print(f"⚠️ Log error: {e}")

            return True, price
        except Exception as e:
            print(f"❌ [{instrument}] Order error: {e}")
            return False, 0

    def close_position(self, instrument: str):
        """Close position for an instrument."""
        try:
            pos_dir, pos_units, _, _ = self.get_current_position(instrument)
            if pos_dir == 0:
                return False, 0

            data = {"longUnits": "ALL"} if pos_dir == 1 else {"shortUnits": "ALL"}
            r = PositionClose(accountID=self.account_id, instrument=instrument, data=data)
            self.api.request(r)

            key = "longOrderFillTransaction" if pos_dir == 1 else "shortOrderFillTransaction"
            pnl = float(r.response.get(key, {}).get("pl", 0))

            print(f"✅ [{instrument}] Closed. P/L: ${pnl:+.2f}")
            send_notification(f"🎯 {instrument} Closed. P/L: ${pnl:+.2f}")

            self.trades_today.append({
                "time": datetime.now().isoformat(),
                "instrument": instrument,
                "direction": "CLOSE",
                "pnl": pnl,
                "type": "CLOSE",
            })

            try:
                logger = TradeLogger()
                logger.log_forex_trade(
                    action="CLOSE",
                    direction="LONG" if pos_dir == 1 else "SHORT",
                    units=pos_units, pnl=pnl,
                    account_type=self.mode,
                    signal_data=self.last_signal_data,
                    market_data=self.last_market_data,
                )
            except Exception as e:
                print(f"⚠️ Log error: {e}")

            self.daily_pnl += pnl
            istate = self._instrument_state[instrument]
            istate["entry_time"] = None
            istate["trailing_active"] = False
            istate["peak_profit"] = 0
            istate["entry_regime"] = None
            self.save_state()
            return True, pnl
        except Exception as e:
            print(f"❌ [{instrument}] Close error: {e}")
            return False, 0

    # ─── Main Loop ───────────────────────────────────────────────

    def run_once(self):
        """Run one iteration — detect regime, scan instruments."""
        if os.getenv("BOT_PAUSED", "false").lower() == "true":
            print("⏸️ BOT PAUSED")
            return

        market_open, reason = is_forex_market_open()
        if not market_open:
            print(f"💤 {reason} - pausing operations.")
            return

        # Daily reset
        today = datetime.now().date()
        if today != self.last_reset_date:
            print(f"🌅 New day. Previous P/L: ${self.daily_pnl:+.2f}")
            self.daily_pnl = 0
            self.trades_today = []
            self.last_reset_date = today
            for istate in self._instrument_state.values():
                istate["peak_profit"] = 0
                istate["trailing_active"] = False
            self.save_state()

        # Weekend protection
        et = pytz.timezone("America/New_York")
        now_et = datetime.now(et)
        if now_et.weekday() == 4 and now_et.hour >= 16:
            for inst in self.instruments:
                pi = self.get_current_position(inst)
                if pi and pi[0] != 0:
                    print(f"🏖️ WEEKEND: Closing {inst}")
                    self.close_position(inst)
            return

        # Daily loss limit
        total_upl = 0
        for inst in self.instruments:
            pi = self.get_current_position(inst)
            if pi and pi[0] != 0:
                total_upl += pi[3]
        if self.daily_pnl + total_upl <= self.max_daily_loss:
            print(f"🛑 Daily loss limit: ${self.daily_pnl + total_upl:+.2f}")
            for inst in self.instruments:
                pi = self.get_current_position(inst)
                if pi and pi[0] != 0:
                    self.close_position(inst)
            return

        # ─── Detect Regime on USD/JPY (primary instrument) ───
        df_jpy = self.get_candles("USD_JPY", count=100)
        if df_jpy.empty:
            print("⚠️ No USD/JPY candle data")
            return

        regime_state = self.regime_detector.detect(df_jpy)
        self.last_regime_state = regime_state

        # Regime display
        regime_emoji = {
            "MEAN_REVERSION": "📊",
            "BREAKOUT": "🔥",
            "TRANSITIONAL": "⚡",
        }
        emoji = regime_emoji.get(regime_state.regime, "❓")
        confirmed_str = "✓" if regime_state.confirmed else "…"
        print(
            f"\n{'='*60}\n"
            f"{emoji} REGIME: {regime_state.regime} ({regime_state.confidence}%) {confirmed_str}\n"
            f"   {regime_state.reason}\n"
            f"{'='*60}"
        )

        # Process each instrument
        for inst in self.instruments:
            self._process_instrument(inst, df_jpy, regime_state)

    def _process_instrument(self, instrument: str, df_jpy: pd.DataFrame, regime_state: RegimeState):
        """Process a single instrument under the current regime."""
        cfg = self.INSTRUMENT_CONFIG[instrument]
        istate = self._instrument_state[instrument]

        # Get candles for this instrument
        if instrument == "USD_JPY":
            df = df_jpy
        else:
            df = self.get_candles(instrument, count=100)
            if df.empty:
                return

        # Get position
        pos_info = self.get_current_position(instrument)
        if pos_info is None:
            print(f"⚠️ [{instrument}] Position sync error, skipping")
            return
        pos_dir, pos_units, entry_price, upl = pos_info

        current_price = df.iloc[-1]["Close"]
        timestamp = datetime.now().strftime("%H:%M:%S")
        price_fmt = f"{current_price:.2f}" if instrument == "XAU_USD" else f"{current_price:.3f}"

        # ─── POSITION MANAGEMENT (always runs) ───
        if pos_dir != 0:
            entry_regime = istate.get("entry_regime", "UNKNOWN")
            hold_h = 0
            if istate["entry_time"]:
                hold_h = (datetime.now() - istate["entry_time"]).total_seconds() / 3600

            # Determine max hold and trailing based on entry regime
            if entry_regime == "BREAKOUT":
                max_hold = self.vol_max_holding_hours
                trail_trigger = self.vol_trailing_trigger
            else:
                max_hold = self.mr_max_holding_hours
                trail_trigger = self.mr_trailing_trigger

            trail_str = " 🎯" if istate["trailing_active"] else ""
            print(
                f"[{timestamp}] {instrument} @ {price_fmt} | "
                f"{'LONG' if pos_dir == 1 else 'SHORT'} | "
                f"P/L: ${upl:+.2f} | Hold: {hold_h:.1f}h | "
                f"Via: {entry_regime}{trail_str}"
            )

            # Time stop
            if hold_h >= max_hold:
                print(f"⏱️ [{instrument}] TIME STOP after {hold_h:.1f}h")
                self.close_position(instrument)
                return

            # Trailing profit
            if upl >= trail_trigger and not istate["trailing_active"]:
                istate["trailing_active"] = True
                istate["peak_profit"] = upl
                print(f"🎯 [{instrument}] TRAILING at ${upl:+.2f}")
                send_notification(f"🎯 {instrument} Trailing at ${upl:+.2f}")

            if istate["trailing_active"] and upl > istate["peak_profit"]:
                istate["peak_profit"] = upl

            if istate["trailing_active"]:
                trail_amt = max(10, istate["peak_profit"] * 0.4)
                if upl <= istate["peak_profit"] - trail_amt:
                    print(f"🔒 [{instrument}] TRAILING STOP ${upl:+.2f}")
                    ok, rpnl = self.close_position(instrument)
                    if ok:
                        send_notification(f"🔒 {instrument} Trail stop ${rpnl:+.2f}")
                    return

            return  # In position, skip entry logic

        # ─── ENTRY LOGIC (only when flat) ───
        active_regime = regime_state.regime

        # No new entries during transition or cooldown
        if active_regime == "TRANSITIONAL" or not regime_state.confirmed:
            print(f"[{timestamp}] {instrument} @ {price_fmt} | Regime: {active_regime} — no new entries")
            return

        # Check if this instrument supports the active regime
        if active_regime not in cfg["strategies"]:
            # Gold only trades breakout
            return

        # Spread filter
        spread = self.get_current_spread(instrument)
        max_spread = cfg["max_spread"]

        # Get signal from active strategy
        idx = len(df) - 1
        if active_regime == "MEAN_REVERSION":
            signal_data = self.mr_strategy.get_signal(df, idx)
            signal = signal_data["signal"]
            confidence = signal_data["confidence"]
            reason = signal_data.get("reason", "")

            # MR: use regime filter from original bot
            # In MEAN_REVERSION regime, we only take the MR signals
            # that are appropriate for the SMA direction
            sma_dir = regime_state.sma_direction
            if signal == "BUY" and sma_dir == "BEARISH":
                return  # Don't buy in bearish SMA
            if signal == "SELL" and sma_dir == "BULLISH":
                return  # Don't sell in bullish SMA

        else:  # BREAKOUT
            signal_data = self.vol_strategy.get_signal(df, idx)
            signal = signal_data["signal"]
            confidence = signal_data["confidence"]
            reason = signal_data.get("reason", "")

        self.last_signal_data = {
            "instrument": instrument,
            "regime": active_regime,
            "signal": signal,
            "confidence": confidence,
            "reason": reason,
        }
        self.last_market_data = {
            "instrument": instrument,
            "price": current_price,
            "spread": spread,
        }

        print(
            f"[{timestamp}] {instrument} @ {price_fmt} | "
            f"{active_regime} → {signal} ({confidence}%)"
        )
        if reason and signal != "HOLD":
            print(f"   💡 {reason}")

        # Spread check
        if spread and spread > max_spread and signal in ["BUY", "SELL"]:
            print(f"   ⚠️ [{instrument}] SPREAD: {spread:.1f} > {max_spread:.1f}")
            return

        # Execute entry
        if signal in ["BUY", "SELL"] and confidence >= 60:
            if active_regime == "MEAN_REVERSION":
                # MR: fixed stop loss in pips
                stop_dist = self.mr_stop_loss_pips * cfg["pip_size"]
            else:
                # Breakout: ATR-based dynamic stop
                stop_dist = self.vol_strategy.calculate_dynamic_stop(
                    df, idx, self.vol_stop_atr_mult
                )

            if stop_dist <= 0:
                print(f"   ⚠️ [{instrument}] Bad stop distance")
                return

            units = self.calculate_position_size(instrument, stop_dist)
            sl_pips = stop_dist / cfg["pip_size"]

            action = "BUY" if signal == "BUY" else "SELL"
            print(
                f"🚀 [{instrument}] {active_regime} {action}: {units}u | "
                f"SL: {sl_pips:.0f}p"
            )
            self.open_position(instrument, signal, units, stop_dist, active_regime)

    # ─── Health Endpoint Data ────────────────────────────────────

    def get_health_data(self) -> dict:
        """Return health data for the endpoint."""
        # Read from detector directly so it works on startup/market close since state is loaded
        regime_name = self.regime_detector._current_regime
        # Call market open function
        market_open, _ = is_forex_market_open()
        
        # Synthesize a simple payload from internal state
        return {
            "bot": "regime_switcher",
            "mode": self.mode,
            "regime": regime_name,
            "regime_confirmed": self.regime_detector._cooldown_remaining == 0 and self.regime_detector._pending_regime is None,
            "market_open": market_open,
            "instruments": self.instruments,
            "daily_pnl": round(self.daily_pnl, 2),
        }


def run_bot(mode="paper"):
    """Main entry point for the regime bot."""
    bot = USDJPYRegimeBot(mode=mode)

    print(f"\n🤖 Regime Bot running in {mode.upper()} mode")
    print(f"   Checking every 15 minutes...\n")

    while True:
        try:
            market_open, reason = is_forex_market_open()
            if not market_open:
                print(f"💤 {reason}")
                time.sleep(300)
                continue

            bot.run_once()
        except Exception as e:
            print(f"❌ Bot error: {e}")
            import traceback
            traceback.print_exc()

        time.sleep(900)  # 15 minutes


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="paper", choices=["paper", "live"])
    args = parser.parse_args()
    run_bot(args.mode)
