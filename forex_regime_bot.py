#!/usr/bin/env python3
"""
Forex Multi-Pair Regime-Switching Trading Bot

Detects market regime per instrument and deploys the appropriate strategy:
  - MEAN_REVERSION regime → Bollinger Bands + RSI (calm markets)
  - BREAKOUT regime → Donchian Channels + ATR + ADX (volatile markets)
  - RANGE regime → Support / Resistance bounds (consolidating markets)
  - TRANSITIONAL → Manage existing positions only, no new entries

Instruments:
  - Dynamically configured via active_instruments.json (USD_CAD, EUR_USD, GBP_USD, AUD_USD, USD_JPY, etc.)

Author: Trading Bot Team
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
from utils.range_trading import RangeTradingStrategy
from utils.regime_detector import RegimeDetector, RegimeState
from utils.trade_logger import TradeLogger
from utils.news_filter import EconomicNewsFilter
from utils.environment_parity_checker import EnvironmentParityChecker


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


class ForexRegimeBot:
    """
    Multi-pair regime-switching bot that uses mean reversion in calm markets,
    volatility breakout in trending/volatile markets, and range trading in consolidations.
    """

    # Per-instrument fallback prices (used when live pricing API is unavailable)
    INSTRUMENT_PRICE_FALLBACKS = {
        "USD_JPY": 150.0,
        "GBP_USD": 1.27,
        "USD_CAD": 1.37,
        "EUR_USD": 1.09,
        "AUD_USD": 0.65,
        "EUR_JPY": 163.0,
        "XAU_USD": 2400.0,
    }

    # Per-instrument configuration
    INSTRUMENT_CONFIG = {
        "USD_JPY": {
            "pip_size": 0.01,
            "pip_value_fn": "jpy",
            "max_spread": 4.0,
            "margin_rate": 0.05,
            "strategies": ["MEAN_REVERSION", "BREAKOUT", "TREND_FOLLOWING", "RANGE"],
        },
        "GBP_USD": {
            "pip_size": 0.0001,
            "pip_value_fn": "direct",
            "max_spread": 4.0,
            "margin_rate": 0.05,
            "strategies": ["MEAN_REVERSION", "BREAKOUT", "TREND_FOLLOWING", "RANGE"],
        },
        "USD_CAD": {
            "pip_size": 0.0001,
            "pip_value_fn": "cad",  # Quote is CAD; pip value = pip_size / price (similar to JPY pairs)
            "max_spread": 4.0,
            "margin_rate": 0.02,
            "strategies": ["MEAN_REVERSION", "BREAKOUT", "TREND_FOLLOWING", "RANGE"],
        },
        "EUR_USD": {
            "pip_size": 0.0001,
            "pip_value_fn": "direct",
            "max_spread": 3.0,
            "margin_rate": 0.02,
            "strategies": ["MEAN_REVERSION", "BREAKOUT", "TREND_FOLLOWING", "RANGE"],
        },
        "AUD_USD": {
            "pip_size": 0.0001,
            "pip_value_fn": "direct",
            "max_spread": 3.0,
            "margin_rate": 0.03,
            "strategies": ["MEAN_REVERSION", "BREAKOUT", "TREND_FOLLOWING", "RANGE"],
        },
        "EUR_JPY": {
            "pip_size": 0.01,
            "pip_value_fn": "jpy",
            "max_spread": 4.0,
            "margin_rate": 0.04,
            "strategies": ["MEAN_REVERSION", "BREAKOUT", "TREND_FOLLOWING", "RANGE"],
        },
        "XAU_USD": {
            "pip_size": 0.01,
            "pip_value_fn": "direct",
            "max_spread": 50.0,
            "margin_rate": 0.05,
            "strategies": ["BREAKOUT", "TREND_FOLLOWING"],  # Gold: breakout & trend only
        },
    }

    def __init__(self, mode: str = "paper"):
        self.mode = mode
        self.granularity = "M15"

        # Account setup
        if mode == "paper":
            self.api_key = os.getenv("OANDA_API_KEY") or os.getenv("OANDA_API_KEY_DEMO")
            self.account_id = os.getenv("OANDA_ACCOUNT_ID") or os.getenv("OANDA_ACCOUNT_ID_DEMO", "101-001-38009813-001")
            self.environment = "practice"
        else:
            self.api_key = os.getenv("OANDA_API_KEY_LIVE") or os.getenv("OANDA_API_KEY")
            self.account_id = os.getenv("OANDA_ACCOUNT_ID_LIVE", "001-001-20048243-002")
            self.environment = "live"

        self.api = API(access_token=self.api_key, environment=self.environment)

        # Instruments — dynamically load optimized roster if available
        self.instruments = ["USD_JPY", "USD_CAD", "EUR_USD"]
        try:
            if os.path.exists("active_instruments.json"):
                with open("active_instruments.json", "r") as f:
                    opt_data = json.load(f)
                    active = opt_data.get("active_instruments", [])
                    if active:
                        self.instruments = active
                        print(f"🎯 Dynamic Portfolio Roster Loaded: {self.instruments}", flush=True)
        except Exception as e:
            print(f"⚠️ Error loading active_instruments.json: {e}", flush=True)

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
        self.range_strategy = RangeTradingStrategy(
            range_period=20, adx_period=14, adx_max=20.0,
            buffer_pips=3.0, stop_loss_pips=15.0,
        )

        # Regime detectors per instrument
        self.regime_detectors = {}
        for inst in self.instruments:
            self.regime_detectors[inst] = RegimeDetector(
                atr_period=14, atr_avg_lookback=50,
                adx_period=14, sma_fast=20, sma_slow=50,
                confirm_candles=1, cooldown_candles=1,
            )

        # Track last regime state per instrument for UI
        self.last_regime_states = {}

        # Simulated balance for position sizing
        self.simulated_balance = 5000.0

        # Risk management — reduced to 1.0% while proving R:R enforcement is profitable.
        # At ~$304 balance: risk ~$3/trade. Raise back to 1.5% once bot shows positive edge.
        self.risk_percent = 0.01  # 1.0% per trade
        self.max_margin_utilization = 0.50  # Capped at 50% of NAV in margin usage
        self.max_daily_loss = -30.0  # Scaled down from -$150 for ~$304 balance
        self.daily_pnl = 0.0

        # MR-specific settings
        self.mr_stop_loss_pips = 20
        self.mr_take_profit_pips = 20    # Fixed TP target for MR trades (fallback; min_rr_multiple takes effect)
        self.mr_trailing_trigger = 20.0  # Activate trailing at $20
        self.mr_trailing_amount = 10.0   # Trail by $10
        self.mr_max_holding_hours = 12

        # Breakout-specific settings
        self.vol_stop_atr_mult = 1.5
        self.vol_trailing_atr_mult = 2.0
        self.vol_trailing_trigger = 25.0
        self.vol_max_holding_hours = 8

        # Minimum Risk:Reward enforcement — applied to ALL trade types at entry.
        # If take_profit_dist is not set by a strategy, it is forced to stop_dist * min_rr_multiple.
        # At 42% win rate, break-even requires R:R >= 1.38. This enforces a profitable buffer.
        self.min_rr_multiple = 1.5

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

        # Dual Environment Parity Auditor
        self.parity_checker = EnvironmentParityChecker(current_mode=self.mode)

        # News Filter (Risk Gate)
        self.news_filter = EconomicNewsFilter()
        self._last_news_refresh = datetime.now()  # Track when we last refreshed the news calendar

        # Cached balance (refreshed once per run_once() cycle to avoid redundant API calls)
        self._cached_balance: float = 0.0

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
            rd_states = {inst: self.regime_detectors[inst].get_state_dict() for inst in self.instruments}
            state = {
                "daily_pnl": self.daily_pnl,
                "last_reset_date": str(self.last_reset_date),
                "regime_detectors": rd_states,
                "instrument_state": {},
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
                rd_states = state.get("regime_detectors", {})
                for inst, rd_state in rd_states.items():
                    if inst in self.regime_detectors:
                        self.regime_detectors[inst].load_state_dict(rd_state)
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

    def send_bot_notification(self, msg: str, title: str = None):
        """Send notification enriched with prominent LIVE / DEMO badge and account ID."""
        is_live = (self.mode == "live")
        badge = f"🔴 [LIVE | {self.account_id}]" if is_live else f"🧪 [DEMO | {self.account_id}]"
        full_msg = f"{badge}\n\n{msg}" if not msg.startswith(badge) else msg
        if notifier:
            try:
                notifier._send(full_msg, title=title or badge)
            except Exception as e:
                print(f"⚠️ Notification failed: {e}")
        print(f"📢 {full_msg}")

    def _send_startup_alert(self):
        """Send startup notification."""
        try:
            balance = self.get_account_balance()
            balance_str = f"${balance:,.2f}" if balance > 0 else f"${self.simulated_balance:,.2f} (sim fallback)"
            
            regimes = []
            for inst in self.instruments:
                r_det = self.regime_detectors.get(inst)
                r_val = r_det._current_regime if r_det and hasattr(r_det, "_current_regime") else "UNKNOWN"
                regimes.append(f"{inst}: {r_val}")
            regimes_str = ", ".join(regimes)

            self.send_bot_notification(
                f"🚀 REGIME BOT Started\n"
                f"Mode: {self.mode.upper()}\n"
                f"Balance: {balance_str}\n"
                f"Instruments: {', '.join(self.instruments)}\n"
                f"Regimes: {regimes_str}"
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
            # If the position doesn't exist, OANDA might return 404 Position not found or NO_SUCH_POSITION
            e_str = str(e).lower()
            if "not found" in e_str or "not_found" in e_str or "no_such_position" in e_str or "no position exists" in e_str:
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

    def calculate_position_size(self, instrument: str, stop_distance_price: float, cached_balance: float = None) -> int:
        """Position size based on actual account balance, capped by margin capacity.
        
        Args:
            instrument: Instrument to size (e.g. "USD_CAD")
            stop_distance_price: Stop distance in price units
            cached_balance: Pre-fetched balance from run_once() to avoid redundant API calls
        """
        current_balance = cached_balance if cached_balance and cached_balance > 0 else self.get_account_balance()
        if current_balance <= 0:
            current_balance = self.simulated_balance
            
        risk_amount = current_balance * self.risk_percent
        cfg = self.INSTRUMENT_CONFIG[instrument]
        pip_size = cfg["pip_size"]

        try:
            price = self._get_mid_price(instrument)
        except Exception as e:
            price = self.INSTRUMENT_PRICE_FALLBACKS.get(instrument, 1.0)
            print(f"⚠️ [{instrument}] Price fetch failed ({e}), using fallback: {price}")

        pip_value_fn = cfg["pip_value_fn"]
        if pip_value_fn in ("jpy", "cad"):  # Quote currency is not USD — pip value depends on price
            pip_value_per_unit = pip_size / price
        else:  # "direct" — quote currency IS USD, pip value is fixed
            pip_value_per_unit = pip_size

        stop_pips = stop_distance_price / pip_size
        size = int(risk_amount / (stop_pips * pip_value_per_unit))

        # Margin/leverage safety cap:
        # Margin required = size * margin_rate * unit_price_in_usd
        margin_rate = cfg.get("margin_rate", 0.05)
        # Convert first currency of instrument to USD to get unit price in USD
        if instrument.startswith("USD_"):
            unit_price_usd = 1.0
        elif instrument.endswith("_USD"):
            unit_price_usd = price
        else:
            unit_price_usd = price

        max_margin = current_balance * self.max_margin_utilization
        max_units = int(max_margin / (margin_rate * unit_price_usd))

        if size > max_units:
            print(f"⚠️ [{instrument}] Position size restricted by margin cap: {size}u -> {max_units}u (Max margin: ${max_margin:.2f})")
            size = max_units

        if instrument == "XAU_USD":
            return max(1, min(size, 100))
        return max(1000, min(size, 100000))

    # ─── Order Execution ─────────────────────────────────────────

    def open_position(self, instrument: str, direction: str, units: int, stop_dist: float, regime: str, take_profit_dist: float = None):
        """Open a position with SL and optional TP."""
        try:
            sign = 1 if direction == "BUY" else -1
            cfg = self.INSTRUMENT_CONFIG[instrument]
            
            # OANDA enforces strict precision limits. JPY pairs max 3 decimals.
            precision = 3 if "JPY" in instrument else 5
            stop_dist_str = f"{stop_dist:.{precision}f}"

            order_data = {
                "order": {
                    "type": "MARKET",
                    "instrument": instrument,
                    "units": str(sign * units),
                    "stopLossOnFill": {"distance": stop_dist_str},
                }
            }

            if take_profit_dist is not None:
                take_profit_dist_str = f"{take_profit_dist:.{precision}f}"
                order_data["order"]["takeProfitOnFill"] = {"distance": take_profit_dist_str}

            r = OrderCreate(accountID=self.account_id, data=order_data)
            self.api.request(r)

            fill = r.response.get("orderFillTransaction", {})
            if not fill:
                cancel_trans = r.response.get("orderCancelTransaction", {})
                reject_trans = r.response.get("orderRejectTransaction", {})
                reason = (
                    cancel_trans.get("reason")
                    or reject_trans.get("rejectReason")
                    or "Unknown OANDA reject reason"
                )
                err_msg = f"❌ [{instrument}] Order rejected by OANDA: {reason}"
                print(err_msg)
                self.send_bot_notification(err_msg)
                return False, 0

            price = float(fill.get("price", 0))

            istate = self._instrument_state[instrument]
            istate["entry_time"] = datetime.now()
            istate["entry_regime"] = regime

            sl_pips = stop_dist / cfg["pip_size"]
            tp_pips_str = f" | TP: {take_profit_dist / cfg['pip_size']:.0f}p" if take_profit_dist else ""
            print(f"✅ [{instrument}] {direction} {units}u @ {price} | SL: {sl_pips:.0f}p{tp_pips_str} | Regime: {regime}")
            
            tp_alert_str = f"SL: {sl_pips:.0f} pips | TP: {take_profit_dist / cfg['pip_size']:.0f} pips | Regime: {regime}" if take_profit_dist else f"SL: {sl_pips:.0f} pips | Regime: {regime}"
            self.send_bot_notification(
                f"🎯 {instrument} {direction} {units}u @ {price}\n"
                f"{tp_alert_str}"
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
                    symbol=instrument,  # Fix symbol logging bug
                    units=units, price=price,
                    account_type=self.mode,
                    account_id=self.account_id,
                    signal_data=self.last_signal_data,
                    market_data=self.last_market_data,
                )
            except Exception as e:
                print(f"⚠️ Log error: {e}")

            # ─── Dual Environment Parity Verification ───
            try:
                self.parity_checker.check_and_notify_parity(
                    instrument=instrument,
                    direction=direction,
                    units=units,
                    entry_price=price,
                    regime=regime,
                    max_spread=cfg.get("max_spread", 4.0),
                    margin_rate=cfg.get("margin_rate", 0.02)
                )
            except Exception as parity_err:
                print(f"⚠️ Parity check error: {parity_err}", flush=True)

            return True, price
        except Exception as e:
            err_msg = f"❌ [{instrument}] Order execution failed: {e}"
            print(err_msg)
            try:
                self.send_bot_notification(err_msg)
            except Exception as notifier_err:
                print(f"⚠️ Failed to send order failure alert: {notifier_err}")
            return False, 0

    def close_position(self, instrument: str, reason: str = None):
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
            exit_price = float(r.response.get(key, {}).get("price", 0.0))
            if exit_price == 0.0:
                try:
                    exit_price = self._get_mid_price(instrument)
                except Exception:
                    pass

            reason_str = f" ({reason})" if reason else ""
            price_str = f" @ {exit_price}" if exit_price > 0 else ""
            print(f"✅ [{instrument}] Closed{reason_str}. P/L: ${pnl:+.2f}{price_str}")
            self.send_bot_notification(f"🎯 {instrument} Closed{reason_str}. P/L: ${pnl:+.2f}{price_str}")

            self.trades_today.append({
                "time": datetime.now().isoformat(),
                "instrument": instrument,
                "direction": "CLOSE",
                "price": exit_price,
                "pnl": pnl,
                "type": "CLOSE",
            })

            try:
                logger = TradeLogger()
                logger.log_forex_trade(
                    action="CLOSE",
                    direction="LONG" if pos_dir == 1 else "SHORT",
                    symbol=instrument,
                    units=pos_units,
                    price=exit_price,  # FIXED: Pass exit price so telemetry logs accurately
                    pnl=pnl,
                    account_type=self.mode,
                    account_id=self.account_id,
                    signal_data=self.last_signal_data,
                    market_data=self.last_market_data,
                )
            except Exception as e:
                print(f"⚠️ Log error: {e}")

            # Trigger automatic post-trade AI commentary & analysis
            try:
                from utils.post_trade_analyzer import PostTradeAnalyzer
                analyzer = PostTradeAnalyzer()
                analyzer.analyze_new_trades(days=1)
            except Exception as pta_err:
                print(f"⚠️ Post-trade analysis error: {pta_err}")

            self.daily_pnl += pnl
            istate = self._instrument_state[instrument]
            istate["entry_time"] = None
            istate["trailing_active"] = False
            istate["peak_profit"] = 0
            istate["entry_regime"] = None
            self.save_state()
            return True, pnl
        except Exception as e:
            err_msg = f"❌ [{instrument}] Close execution failed: {e}"
            print(err_msg)
            try:
                self.send_bot_notification(err_msg)
            except Exception as notifier_err:
                print(f"⚠️ Failed to send close failure alert: {notifier_err}")
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

        # Refresh news calendar every 4 hours (the in-memory calendar goes stale otherwise)
        now = datetime.now()
        if (now - self._last_news_refresh).total_seconds() >= 14400:
            print("🗓️ Refreshing economic news calendar...")
            self.news_filter.fetch_fresh_calendar()
            self._last_news_refresh = now

        # Cache account balance once per cycle (passed to position sizing to avoid N API calls)
        self._cached_balance = self.get_account_balance()

        # Process each instrument independently
        for inst in self.instruments:
            self._process_instrument(inst, cached_balance=self._cached_balance)

    def _process_instrument(self, instrument: str, cached_balance: float = None):
        """Process a single instrument under its own regime."""
        cfg = self.INSTRUMENT_CONFIG[instrument]
        istate = self._instrument_state[instrument]

        # Get current position first to determine if we should throttle
        pos_info = self.get_current_position(instrument)
        if pos_info is None:
            print(f"⚠️ [{instrument}] Position sync error, skipping")
            return
        pos_dir, pos_units, entry_price, upl = pos_info

        # Throttle check: If flat, only scan on M15 candle boundaries (America/New_York)
        now_et = datetime.now(pytz.timezone("America/New_York"))
        if pos_dir == 0 and (now_et.minute % 15 != 0):
            return

        # Get candles for this instrument
        df = self.get_candles(instrument, count=100)
        if df.empty:
            print(f"⚠️ No candle data for {instrument}")
            return
            
        # Detect Regime for this specific instrument
        regime_state = self.regime_detectors[instrument].detect(df)
        self.last_regime_states[instrument] = regime_state
        
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
            f"{emoji} [{instrument}] REGIME: {regime_state.regime} ({regime_state.confidence}%) {confirmed_str}\n"
            f"   {regime_state.reason}\n"
            f"{'='*60}"
        )

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
            if entry_regime in ["BREAKOUT", "TREND_FOLLOWING"]:
                max_hold = self.vol_max_holding_hours
                trail_trigger = self.vol_trailing_trigger
                use_trailing = True
            elif entry_regime == "MEAN_REVERSION":
                max_hold = self.mr_max_holding_hours
                trail_trigger = self.mr_trailing_trigger
                use_trailing = True
            elif entry_regime in ["RANGE", "VOLATILITY_SQUEEZE"]:
                # Range / squeeze trades use fixed TP at channel boundaries — no trailing
                max_hold = self.mr_max_holding_hours
                trail_trigger = self.mr_trailing_trigger
                use_trailing = False
            else:
                # EXTREME_VOLATILITY or unknown — apply shortest hold, no trailing
                max_hold = min(self.mr_max_holding_hours, self.vol_max_holding_hours)
                trail_trigger = self.vol_trailing_trigger
                use_trailing = False

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
                self.close_position(instrument, reason="Time stop")
                return

            # Trailing profit
            if use_trailing and trail_trigger is not None:
                if upl >= trail_trigger and not istate["trailing_active"]:
                    istate["trailing_active"] = True
                    istate["peak_profit"] = upl
                    print(f"🎯 [{instrument}] TRAILING at ${upl:+.2f}")
                    self.send_bot_notification(f"🎯 {instrument} Trailing Active at ${upl:+.2f}")

                if istate["trailing_active"] and upl > istate["peak_profit"]:
                    istate["peak_profit"] = upl

                if istate["trailing_active"]:
                    # Tightened giveback for Breakout trades: 15% of peak profit (min $5, max $15)
                    trail_amt = max(5.0, min(15.0, istate["peak_profit"] * 0.15))
                    if upl <= istate["peak_profit"] - trail_amt:
                        print(f"🔒 [{instrument}] TRAILING STOP ${upl:+.2f}")
                        self.close_position(instrument, reason="Trail stop")
                        return

            return  # In position, skip entry logic

        # ─── ENTRY LOGIC (only when flat) ───
        active_regime = regime_state.regime

        # ─── NEWS BLACKOUT RISK GATE ───
        is_news_blocked, news_reason, _ = self.news_filter.is_blackout_active(instrument, pre_minutes=30, post_minutes=15)
        if is_news_blocked:
            print(f"🛡️ [{timestamp}] [{instrument}] NEWS BLACKOUT ACTIVE: {news_reason} — skipping new entries")
            return

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
        if active_regime == "EXTREME_VOLATILITY":
            signal = "HOLD"
            confidence = 95
            reason = "Extreme Volatility Circuit Breaker (ATR >= 2.5x)"
        elif active_regime == "VOLATILITY_SQUEEZE":
            signal = "HOLD"
            confidence = 70
            reason = "Volatility Squeeze Compression Pause (ATR <= 0.75x)"
        elif active_regime == "TREND_FOLLOWING":
            # Smooth directional trend: ride SMA direction
            sma_dir = regime_state.sma_direction
            if sma_dir == "BULLISH":
                signal = "BUY"
                confidence = 75
                reason = "Trend Following (Bullish SMA alignment)"
            elif sma_dir == "BEARISH":
                signal = "SELL"
                confidence = 75
                reason = "Trend Following (Bearish SMA alignment)"
            else:
                signal = "HOLD"
                confidence = 50
                reason = "Trend Following (Neutral SMA)"
        elif active_regime == "MEAN_REVERSION":
            signal_data = self.mr_strategy.get_signal(df, idx)
            signal = signal_data["signal"]
            confidence = signal_data["confidence"]
            reason = signal_data.get("reason", "")

            # In MEAN_REVERSION regime, require stronger exhaustion on counter-trend moves
            # (allow strong oversold bounces RSI < 28 or overbought shorts RSI > 72 even if SMA opposes)
            sma_dir = regime_state.sma_direction
            rsi_val = signal_data.get("rsi", 50)
            if signal == "BUY" and sma_dir == "BEARISH" and rsi_val > 28:
                signal = "HOLD"
            elif signal == "SELL" and sma_dir == "BULLISH" and rsi_val < 72:
                signal = "HOLD"

            # If Mean Reversion has no signal, fall back to Range Trading Strategy
            if signal == "HOLD":
                signal_data_range = self.range_strategy.get_signal(df, idx, cfg["pip_size"])
                if signal_data_range["signal"] != "HOLD":
                    signal_data = signal_data_range
                    signal_data["regime"] = "RANGE"  # Mark as range trade
                    signal = signal_data["signal"]
                    confidence = signal_data["confidence"]
                    reason = signal_data.get("reason", "")

        elif active_regime == "BREAKOUT":
            signal_data = self.vol_strategy.get_signal(df, idx)
            signal = signal_data["signal"]
            confidence = signal_data["confidence"]
            reason = signal_data.get("reason", "")
        else:  # TRANSITIONAL or unknown
            signal = "HOLD"
            confidence = 30
            reason = f"Regime {active_regime} - no new entries allowed"

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

        # Calculate volume anomaly ratio & ADX metric
        vol_ratio = 1.0
        if "Volume" in df.columns and len(df) >= 20:
            avg_vol = df["Volume"].iloc[-20:-1].mean()
            if avg_vol > 0:
                vol_ratio = df["Volume"].iloc[-1] / avg_vol
        adx_val = getattr(regime_state, "adx", 25.0)

        # Execute entry
        if signal in ["BUY", "SELL"] and confidence >= 60:
            if active_regime == "MEAN_REVERSION":
                if signal_data.get("regime") == "RANGE":
                    # Range strategy: use dynamic range-based stop/profit targets
                    stop_dist = signal_data["stop_dist"]
                    take_profit_dist = signal_data["take_profit_dist"]
                else:
                    # MR: fixed stop loss in pips
                    stop_dist = self.mr_stop_loss_pips * cfg["pip_size"]
                    take_profit_dist = None  # Will be set by min R:R enforcement below
            else:
                # Breakout / Trend Following: ATR-based dynamic stop
                stop_dist = self.vol_strategy.calculate_dynamic_stop(
                    df, idx, self.vol_stop_atr_mult
                )
                take_profit_dist = None  # Will be set by min R:R enforcement below

                # Dynamic TP Scaling on Volume Anomalies (Volume >= 5.0x avg & ADX > 35)
                if vol_ratio >= 5.0 and adx_val > 35.0:
                    atr_val = stop_dist / self.vol_stop_atr_mult if self.vol_stop_atr_mult > 0 else stop_dist
                    take_profit_dist = atr_val * 2.5
                    print(f"🔥 [{instrument}] High-Volume Momentum Burst (Vol: {vol_ratio:.1f}x avg, ADX: {adx_val:.1f}) -> Scaling TP to 2.5x ATR ({take_profit_dist / cfg['pip_size']:.0f}p)")

            if stop_dist <= 0:
                print(f"   ⚠️ [{instrument}] Bad stop distance")
                return

            # ─── Minimum R:R Enforcement ────────────────────────────────────────
            # If no strategy-specific TP was set (range / volume-burst already set one),
            # enforce TP at min_rr_multiple × stop_dist to guarantee viable risk:reward.
            # At 42% live WR, break-even requires R:R ≥ 1.38. We enforce 1.5.
            if take_profit_dist is None:
                take_profit_dist = stop_dist * self.min_rr_multiple
                tp_pips = take_profit_dist / cfg["pip_size"]
                sl_pips_preview = stop_dist / cfg["pip_size"]
                print(f"   📐 [{instrument}] R:R enforced {self.min_rr_multiple}:1 | SL: {sl_pips_preview:.0f}p | TP: {tp_pips:.0f}p")

            units = self.calculate_position_size(instrument, stop_dist, cached_balance=cached_balance)
            sl_pips = stop_dist / cfg["pip_size"]

            action = "BUY" if signal == "BUY" else "SELL"
            tp_pips_str = f" | TP: {take_profit_dist / cfg['pip_size']:.0f}p" if take_profit_dist else ""
            
            trade_regime = "RANGE" if signal_data.get("regime") == "RANGE" else active_regime
            print(
                f"🚀 [{instrument}] {trade_regime} {action}: {units}u | "
                f"SL: {sl_pips:.0f}p{tp_pips_str}"
            )
            self.open_position(instrument, signal, units, stop_dist, trade_regime, take_profit_dist)

    # ─── Health Endpoint Data ────────────────────────────────────

    def get_health_data(self) -> dict:
        """Return health data for the endpoint. Dynamically uses first active instrument for regime."""
        regime_name = "UNKNOWN"
        regime_reason = ""
        regime_confirmed = False
        regime_instrument = None

        # Use first instrument that has an active detector and a cached regime state
        for inst in self.instruments:
            if inst in self.regime_detectors:
                rd = self.regime_detectors[inst]
                regime_name = rd._current_regime
                regime_confirmed = rd._cooldown_remaining == 0 and rd._pending_regime is None
                regime_instrument = inst
                if inst in self.last_regime_states:
                    regime_reason = getattr(self.last_regime_states[inst], "reason", "")
                break

        # Also include per-instrument regime map for richer dashboards
        regime_map = {}
        for inst in self.instruments:
            rd = self.regime_detectors.get(inst)
            if rd:
                regime_map[inst] = rd._current_regime

        market_open, _ = is_forex_market_open()
        return {
            "bot": "regime_switcher",
            "mode": self.mode,
            "regime": regime_name,
            "regime_instrument": regime_instrument,
            "regime_confirmed": regime_confirmed,
            "regime_reason": regime_reason,
            "regime_map": regime_map,
            "market_open": market_open,
            "instruments": self.instruments,
            "daily_pnl": round(self.daily_pnl, 2),
        }


# Backward compatibility alias
USDJPYRegimeBot = ForexRegimeBot


def run_bot(mode="paper"):
    """Main entry point for the regime bot."""
    bot = ForexRegimeBot(mode=mode)

    print(f"\n🤖 Forex Regime Bot running in {mode.upper()} mode")
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
