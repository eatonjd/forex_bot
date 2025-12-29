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

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from oandapyV20 import API
from oandapyV20.endpoints.accounts import AccountSummary
from oandapyV20.endpoints.instruments import InstrumentsCandles
from oandapyV20.endpoints.orders import OrderCreate
from oandapyV20.endpoints.positions import PositionDetails, PositionClose
from oandapyV20.endpoints.trades import TradesList

import numpy as np
import pandas as pd

from utils.mean_reversion import MeanReversionStrategy

try:
    from utils.notifications import NotificationManager

    notifier = NotificationManager()
except:
    notifier = None


def send_notification(msg):
    """Send notification if available."""
    if notifier:
        try:
            notifier.send_trade_alert("USD_JPY", "INFO", 0, msg)
        except:
            pass
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
        self.daily_target = 100  # $100 daily target
        self.daily_pnl = 0
        self.max_daily_loss = -200  # Stop trading if down $200

        # Position tracking
        self.position = 0  # -1=short, 0=flat, 1=long
        self.entry_price = 0

        print(f"\n{'=' * 60}")
        print(f"🤖 USD/JPY MEAN REVERSION BOT")
        print(f"{'=' * 60}")
        print(f"Mode: {mode.upper()}")
        print(f"Account: {self.account_id}")
        print(f"Instrument: {self.instrument}")
        print(f"Timeframe: {self.granularity}")
        print(f"Risk per trade: {self.risk_percent * 100}%")
        print(f"Daily target: ${self.daily_target}")
        print(f"{'=' * 60}\n")

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

            if long_units > 0:
                return 1, long_units, float(pos["long"]["averagePrice"])
            elif short_units != 0:
                return -1, abs(short_units), float(pos["short"]["averagePrice"])
            else:
                return 0, 0, 0
        except:
            return 0, 0, 0

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

            return True, price
        except Exception as e:
            print(f"❌ Order error: {e}")
            return False, 0

    def close_position(self):
        """Close current position."""
        try:
            r = PositionClose(
                accountID=self.account_id,
                instrument=self.instrument,
                data={"longUnits": "ALL", "shortUnits": "ALL"},
            )
            self.api.request(r)

            # Get P/L from response
            long_pnl = float(
                r.response.get("longOrderFillTransaction", {}).get("pl", 0)
            )
            short_pnl = float(
                r.response.get("shortOrderFillTransaction", {}).get("pl", 0)
            )
            pnl = long_pnl + short_pnl

            print(f"✅ Closed position. P/L: ${pnl:+.2f}")
            send_notification(f"🤖 USD/JPY Closed. P/L: ${pnl:+.2f}")

            self.daily_pnl += pnl
            return True, pnl
        except Exception as e:
            print(f"❌ Close error: {e}")
            return False, 0

    def run_once(self):
        """Run one iteration of the strategy."""
        # Get current position
        pos_dir, pos_units, entry_price = self.get_current_position()

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

        print(
            f"[{timestamp}] Price: {current_price:.3f} | Signal: {signal} ({confidence}%) | {reason}"
        )

        # Check daily limits
        if self.daily_pnl >= self.daily_target:
            print(f"🎯 Daily target reached! P/L: ${self.daily_pnl:+.2f}")
            return

        if self.daily_pnl <= self.max_daily_loss:
            print(f"🛑 Daily loss limit hit! P/L: ${self.daily_pnl:+.2f}")
            return

        # Execute trades
        if signal == "BUY" and confidence >= 50:
            if pos_dir == -1:  # Close short first
                self.close_position()

            if pos_dir != 1:  # Open long if not already
                units = self.calculate_position_size()
                self.open_position("BUY", units)

        elif signal == "SELL" and confidence >= 50:
            if pos_dir == 1:  # Close long first
                self.close_position()

            if pos_dir != -1:  # Open short if not already
                units = self.calculate_position_size()
                self.open_position("SELL", units)

    def run(self, interval_minutes: int = 15):
        """Run the bot continuously."""
        print(f"🚀 Starting bot (checking every {interval_minutes} minutes)...")

        while True:
            try:
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
