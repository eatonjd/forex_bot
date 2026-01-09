#!/usr/bin/env python3
"""
Parallel Trading Bot - Demo + Live with Slippage Tracking

Runs the same strategy on both demo and live accounts simultaneously
to measure real slippage and execution differences.

Author: Trading Bot Team
Created: 2026-01-09
"""

import os
import time
import json
import argparse
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
import pytz

load_dotenv()

# Import the base strategy components
from usdjpy_mean_reversion import (
    USDJPYMeanReversionBot,
    is_forex_market_open,
    send_notification,
)


class SlippageTracker:
    """Track and compare execution between demo and live accounts."""

    def __init__(self, log_file: str = "slippage_log.json"):
        self.log_file = Path(log_file)
        self.trades = []
        self._load()

    def _load(self):
        """Load existing trade log."""
        if self.log_file.exists():
            try:
                with open(self.log_file) as f:
                    self.trades = json.load(f)
            except:
                self.trades = []

    def _save(self):
        """Save trade log."""
        with open(self.log_file, "w") as f:
            json.dump(self.trades, f, indent=2, default=str)

    def record_trade(self, demo_fill: dict, live_fill: dict, signal: str):
        """Record a matched trade from both accounts."""
        slippage_pips = 0
        if demo_fill.get("price") and live_fill.get("price"):
            # Calculate slippage in pips (USD/JPY: 1 pip = 0.01)
            slippage_pips = (live_fill["price"] - demo_fill["price"]) * 100
            if signal == "SELL":
                slippage_pips = -slippage_pips  # Reverse for sells

        trade = {
            "timestamp": datetime.now().isoformat(),
            "signal": signal,
            "demo": demo_fill,
            "live": live_fill,
            "slippage_pips": round(slippage_pips, 2),
        }
        self.trades.append(trade)
        self._save()
        return slippage_pips

    def get_summary(self) -> dict:
        """Get slippage summary statistics."""
        if not self.trades:
            return {"count": 0}

        slippages = [t["slippage_pips"] for t in self.trades]
        avg_slip = sum(slippages) / len(slippages)
        max_slip = max(slippages)
        min_slip = min(slippages)

        return {
            "count": len(self.trades),
            "avg_slippage_pips": round(avg_slip, 2),
            "max_slippage_pips": round(max_slip, 2),
            "min_slippage_pips": round(min_slip, 2),
            "total_slippage_pips": round(sum(slippages), 2),
        }


class ParallelTradingBot:
    """
    Runs trading signals on both demo and live accounts simultaneously.
    """

    def __init__(self):
        # Initialize demo bot (main strategy)
        self.demo_bot = USDJPYMeanReversionBot(mode="paper")

        # Initialize live bot with live credentials
        self.live_bot = self._create_live_bot()

        # Slippage tracker
        self.tracker = SlippageTracker()

        print("\n" + "=" * 60)
        print("🔀 PARALLEL TRADING BOT (Demo + Live)")
        print("=" * 60)
        print(f"Demo Account: {self.demo_bot.account_id}")
        print(f"Live Account: {self.live_bot.account_id}")
        print("=" * 60 + "\n")

        # Send startup notification
        send_notification(
            f"🔀 Parallel Trading Started\n"
            f"Demo: {self.demo_bot.account_id}\n"
            f"Live: {self.live_bot.account_id}\n"
            f"Purpose: Slippage measurement"
        )

    def _create_live_bot(self):
        """Create a live trading bot instance."""
        from oandapyV20 import API
        from utils.mean_reversion import MeanReversionStrategy

        # Create a minimal live bot
        class LiveBot:
            def __init__(self):
                self.api_key = os.getenv("OANDA_API_KEY_LIVE")
                self.account_id = os.getenv(
                    "OANDA_ACCOUNT_ID_LIVE", "001-001-20048243-002"
                )
                self.instrument = "USD_JPY"
                self.api = API(access_token=self.api_key, environment="live")

            def get_account_balance(self):
                from oandapyV20.endpoints.accounts import AccountSummary

                r = AccountSummary(accountID=self.account_id)
                self.api.request(r)
                return float(r.response["account"]["balance"])

            def calculate_position_size(self, balance: float, risk_pct: float = 0.02):
                """Calculate position size for live account (smaller)."""
                risk_amount = balance * risk_pct
                # Smaller positions for live testing
                return max(1000, min(int(risk_amount * 100), 10000))

            def open_position(self, direction: str, units: int):
                """Open position on live account."""
                from oandapyV20.endpoints.orders import OrderCreate

                sign = 1 if direction == "BUY" else -1
                order_data = {
                    "order": {
                        "type": "MARKET",
                        "instrument": self.instrument,
                        "units": str(sign * units),
                    }
                }

                try:
                    r = OrderCreate(accountID=self.account_id, data=order_data)
                    self.api.request(r)

                    fill = r.response.get("orderFillTransaction", {})
                    price = float(fill.get("price", 0))

                    return {
                        "success": True,
                        "price": price,
                        "units": units,
                        "direction": direction,
                    }
                except Exception as e:
                    print(f"❌ Live order error: {e}")
                    return {"success": False, "error": str(e)}

            def close_position(self):
                """Close position on live account."""
                from oandapyV20.endpoints.positions import (
                    PositionClose,
                    PositionDetails,
                )

                try:
                    # Check current position
                    r = PositionDetails(
                        accountID=self.account_id, instrument=self.instrument
                    )
                    self.api.request(r)
                    pos = r.response.get("position", {})

                    long_units = int(pos.get("long", {}).get("units", 0))
                    short_units = int(pos.get("short", {}).get("units", 0))

                    if long_units == 0 and short_units == 0:
                        return {"success": False, "error": "No position"}

                    if long_units > 0:
                        data = {"longUnits": "ALL"}
                    else:
                        data = {"shortUnits": "ALL"}

                    r = PositionClose(
                        accountID=self.account_id, instrument=self.instrument, data=data
                    )
                    self.api.request(r)

                    if long_units > 0:
                        pnl = float(
                            r.response.get("longOrderFillTransaction", {}).get("pl", 0)
                        )
                        price = float(
                            r.response.get("longOrderFillTransaction", {}).get(
                                "price", 0
                            )
                        )
                    else:
                        pnl = float(
                            r.response.get("shortOrderFillTransaction", {}).get("pl", 0)
                        )
                        price = float(
                            r.response.get("shortOrderFillTransaction", {}).get(
                                "price", 0
                            )
                        )

                    return {"success": True, "pnl": pnl, "price": price}
                except Exception as e:
                    print(f"❌ Live close error: {e}")
                    return {"success": False, "error": str(e)}

            def get_current_position(self):
                """Get current position on live account."""
                from oandapyV20.endpoints.positions import PositionDetails

                try:
                    r = PositionDetails(
                        accountID=self.account_id, instrument=self.instrument
                    )
                    self.api.request(r)
                    pos = r.response.get("position", {})

                    long_units = int(pos.get("long", {}).get("units", 0))
                    short_units = int(pos.get("short", {}).get("units", 0))

                    if long_units > 0:
                        return (
                            1,
                            long_units,
                            float(pos["long"].get("averagePrice", 0)),
                            float(pos["long"].get("unrealizedPL", 0)),
                        )
                    elif short_units < 0:
                        return (
                            -1,
                            abs(short_units),
                            float(pos["short"].get("averagePrice", 0)),
                            float(pos["short"].get("unrealizedPL", 0)),
                        )
                    return 0, 0, 0, 0
                except:
                    return 0, 0, 0, 0

        return LiveBot()

    def run_once(self):
        """Run one iteration on both accounts."""
        # Get signal from demo bot (main strategy)
        # Use demo bot's strategy to get the signal
        df = self.demo_bot.get_candles(count=50)
        if df.empty:
            print("⚠️ No candle data")
            return

        signal_data = self.demo_bot.strategy.get_signal(df, len(df) - 1)
        signal = signal_data["signal"]
        confidence = signal_data["confidence"]
        reason = signal_data.get("reason", "")

        current_price = df.iloc[-1]["Close"]
        timestamp = datetime.now().strftime("%H:%M:%S")

        print(
            f"\n[{timestamp}] Price: {current_price:.3f} | Signal: {signal} ({confidence}%) | {reason}"
        )

        # Get current positions
        demo_pos, _, _, demo_pnl = self.demo_bot.get_current_position()
        live_pos, _, _, live_pnl = self.live_bot.get_current_position()

        if demo_pos != 0:
            print(
                f"   📊 Demo: {'LONG' if demo_pos == 1 else 'SHORT'} | P/L: ${demo_pnl:+.2f}"
            )
        if live_pos != 0:
            print(
                f"   📊 Live: {'LONG' if live_pos == 1 else 'SHORT'} | P/L: ${live_pnl:+.2f}"
            )

        # Execute on both accounts if signal is actionable
        if signal in ("BUY", "SELL") and confidence >= 50:
            print(f"\n🔀 Executing {signal} on BOTH accounts...")

            # Calculate position sizes
            demo_units = self.demo_bot.calculate_position_size()
            live_balance = self.live_bot.get_account_balance()
            live_units = self.live_bot.calculate_position_size(live_balance)

            # Close existing positions if reversing
            if (signal == "BUY" and demo_pos == -1) or (
                signal == "SELL" and demo_pos == 1
            ):
                print("   Closing demo position...")
                self.demo_bot.close_position()

            if (signal == "BUY" and live_pos == -1) or (
                signal == "SELL" and live_pos == 1
            ):
                print("   Closing live position...")
                self.live_bot.close_position()

            # Open new positions (only if not already in same direction)
            demo_fill = {"success": False}
            live_fill = {"success": False}

            if (signal == "BUY" and demo_pos != 1) or (
                signal == "SELL" and demo_pos != -1
            ):
                success, price = self.demo_bot.open_position(signal, demo_units)
                demo_fill = {"success": success, "price": price, "units": demo_units}
                print(f"   ✅ Demo: {signal} {demo_units:,} @ {price:.3f}")

            if (signal == "BUY" and live_pos != 1) or (
                signal == "SELL" and live_pos != -1
            ):
                live_fill = self.live_bot.open_position(signal, live_units)
                if live_fill["success"]:
                    print(
                        f"   ✅ Live: {signal} {live_units:,} @ {live_fill['price']:.3f}"
                    )
                else:
                    print(f"   ❌ Live: Failed - {live_fill.get('error', 'Unknown')}")

            # Record slippage if both succeeded
            if demo_fill.get("success") and live_fill.get("success"):
                slippage = self.tracker.record_trade(demo_fill, live_fill, signal)
                print(f"   📏 Slippage: {slippage:+.2f} pips")

                if abs(slippage) > 2:
                    send_notification(
                        f"⚠️ High Slippage Alert!\n"
                        f"Signal: {signal}\n"
                        f"Demo: {demo_fill['price']:.3f}\n"
                        f"Live: {live_fill['price']:.3f}\n"
                        f"Slippage: {slippage:+.2f} pips"
                    )

        # Check for trailing stops (demo only manages this for now)
        # Live mirrors demo, so when demo closes, live should too

    def run(self, interval_minutes: int = 15):
        """Run continuously."""
        print(
            f"🚀 Starting parallel bot (checking every {interval_minutes} minutes)..."
        )

        et = pytz.timezone("America/New_York")

        while True:
            try:
                # Check if market is open
                market_open, reason = is_forex_market_open()
                if not market_open:
                    print(f"\n🌙 {reason} - sleeping 30 min")
                    time.sleep(30 * 60)
                    continue

                self.run_once()

                # Print slippage summary periodically
                summary = self.tracker.get_summary()
                if summary["count"] > 0:
                    print(
                        f"\n📊 Slippage Summary: {summary['count']} trades, avg: {summary['avg_slippage_pips']:.2f} pips"
                    )

            except Exception as e:
                print(f"❌ Error: {e}")

            time.sleep(interval_minutes * 60)

    def print_slippage_report(self):
        """Print detailed slippage report."""
        summary = self.tracker.get_summary()
        print("\n" + "=" * 60)
        print("📊 SLIPPAGE REPORT")
        print("=" * 60)
        print(f"Total trades tracked: {summary.get('count', 0)}")
        print(f"Average slippage: {summary.get('avg_slippage_pips', 0):.2f} pips")
        print(f"Max slippage: {summary.get('max_slippage_pips', 0):.2f} pips")
        print(f"Min slippage: {summary.get('min_slippage_pips', 0):.2f} pips")
        print(f"Total slippage: {summary.get('total_slippage_pips', 0):.2f} pips")
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Parallel Demo + Live Trading Bot")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument(
        "--interval", "-i", type=int, default=15, help="Check interval in minutes"
    )
    parser.add_argument(
        "--report", action="store_true", help="Print slippage report only"
    )
    args = parser.parse_args()

    bot = ParallelTradingBot()

    if args.report:
        bot.print_slippage_report()
    elif args.once:
        bot.run_once()
        bot.print_slippage_report()
    else:
        bot.run(interval_minutes=args.interval)


if __name__ == "__main__":
    main()
