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

        # Safety Settings (Synced with usdjpy_mean_reversion.py)
        self.daily_target = self.demo_bot.daily_target
        self.stop_loss_pips = self.demo_bot.stop_loss_pips
        self.max_daily_loss = self.demo_bot.max_daily_loss
        self.daily_pnl = 0

        # Probe Entry Settings (Synced)
        self.use_probe_entry = self.demo_bot.use_probe_entry
        self.probe_size_pct = self.demo_bot.probe_size_pct
        self.probe_confirm_profit = self.demo_bot.probe_confirm_profit
        self.probe_max_candles = self.demo_bot.probe_max_candles
        self.probe_entry_candle = 0
        self.is_probe_position = False
        self.candle_count = 0

        # Regime Detection Settings (Synced)
        self.use_regime_filter = self.demo_bot.use_regime_filter
        self.current_regime = "RANGING"

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

        # Detect regime
        if self.use_regime_filter:
            self.current_regime = self.demo_bot.get_market_regime(df)
            regime_emoji = {
                "TRENDING_UP": "📈",
                "TRENDING_DOWN": "📉",
                "RANGING": "↔️",
            }.get(self.current_regime, "?")
        else:
            self.current_regime = "RANGING"
            regime_emoji = "↔️"

        # In trending markets, use trend-following signals
        if self.current_regime in ("TRENDING_UP", "TRENDING_DOWN"):
            trend_signal = self.demo_bot.strategy.get_trend_signal(
                df, len(df) - 1, self.current_regime
            )
            if trend_signal["signal"] != "HOLD":
                signal = trend_signal["signal"]
                confidence = trend_signal["confidence"]
                reason = trend_signal.get("reason", "")

        print(
            f"\n[{timestamp}] Price: {current_price:.3f} | {regime_emoji} {self.current_regime} | Signal: {signal} ({confidence}%) | {reason}"
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

        # Safety Checks (Realized + Unrealized)
        combined_unrealized = demo_pnl  # We use demo as the source of truth for safety
        total_pnl = self.daily_pnl + combined_unrealized

        # 1. Daily Loss Limit
        if total_pnl <= self.max_daily_loss:
            print(f"🛑 DAILY LOSS LIMIT HIT! Combined P/L: ${total_pnl:+.2f}")
            if demo_pos != 0:
                print("   ⚠️ Closing BOTH accounts due to loss limit...")
                self.demo_bot.close_position()
                self.live_bot.close_position()
            return

        # 2. Stop Loss (Pip-based)
        if demo_pos != 0:
            # We use demo_bot for entry_price
            _, _, entry_price, _ = self.demo_bot.get_current_position()
            pip_size = 0.01  # USD/JPY

            if demo_pos == 1:  # LONG
                drawdown_pips = (entry_price - current_price) / pip_size
            else:  # SHORT
                drawdown_pips = (current_price - entry_price) / pip_size

            if drawdown_pips >= self.stop_loss_pips:
                print(f"🛑 STOP LOSS HIT! Drawdown: {drawdown_pips:.1f} pips")
                self.demo_bot.close_position()
                self.live_bot.close_position()
                self.is_probe_position = False
                return

        # Increment candle counter
        self.candle_count += 1

        # *** PROBE MANAGEMENT (Parallel) ***
        if self.is_probe_position and demo_pos != 0:
            candles_since_entry = self.candle_count - self.probe_entry_candle

            # 1. Confirmation (Scale up)
            if demo_pnl >= self.probe_confirm_profit:
                print(f"✅ PROBE CONFIRMED (Parallel)! Scaling up...")

                # Demo scale up
                base_units = self.demo_bot.calculate_position_size()
                rem_units = int(base_units * (1 - self.probe_size_pct))
                direction = "BUY" if demo_pos == 1 else "SELL"
                self.demo_bot.open_position(direction, rem_units)

                # Live scale up (Live uses its own sizing)
                live_full = self.live_bot.calculate_position_size(
                    self.live_bot.get_account_balance()
                )
                live_rem = int(live_full * (1 - self.probe_size_pct))
                self.live_bot.open_position(direction, live_rem)

                self.is_probe_position = False
                send_notification(
                    f"✅ USD/JPY Probe confirmed! Scaled both accounts (+${demo_pnl:.2f})"
                )

            # 2. Timeout (Exit)
            elif candles_since_entry >= self.probe_max_candles:
                if demo_pnl < 0:
                    print(f"⏱️ PROBE TIMEOUT (Parallel)! Closing both...")
                    self.demo_bot.close_position()
                    self.live_bot.close_position()
                    self.is_probe_position = False
                    send_notification(
                        f"⏱️ USD/JPY Probe timed out. Closed for ${demo_pnl:+.2f}"
                    )
                    return
                else:
                    print(f"📊 Probe profitable but not confirmed. Holding...")
                    self.is_probe_position = False

        # Execute on both accounts if signal is actionable
        if signal in ("BUY", "SELL") and confidence >= 50:
            # REGIME FILTER: Skip counter-trend trades
            if self.use_regime_filter:
                if (
                    signal == "BUY"
                    and self.current_regime == "TRENDING_DOWN"
                    and demo_pos != 1
                ):
                    print(
                        f"   ⚠️ REGIME FILTER: Skipping BUY signal (market trending DOWN)"
                    )
                    return
                if (
                    signal == "SELL"
                    and self.current_regime == "TRENDING_UP"
                    and demo_pos != -1
                ):
                    print(
                        f"   ⚠️ REGIME FILTER: Skipping SELL signal (market trending UP)"
                    )
                    return

            print(f"\n🔀 Executing {signal} on BOTH accounts...")

            # Calculate position sizes
            live_balance = self.live_bot.get_account_balance()

            # Close existing positions if reversing
            if (signal == "BUY" and demo_pos == -1) or (
                signal == "SELL" and demo_pos == 1
            ):
                print("   Closing demo position...")
                success, pnl = self.demo_bot.close_position()
                if success:
                    self.daily_pnl += pnl

            if (signal == "BUY" and live_pos == -1) or (
                signal == "SELL" and live_pos == 1
            ):
                print("   Closing live position...")
                self.live_bot.close_position()

            self.is_probe_position = False

            # Open new positions (only if not already in same direction)
            demo_fill = {"success": False}
            live_fill = {"success": False}

            if (signal == "BUY" and demo_pos != 1) or (
                signal == "SELL" and demo_pos != -1
            ):
                # Apply Probe Sizing
                base_demo_units = self.demo_bot.calculate_position_size()
                base_live_units = self.live_bot.calculate_position_size(
                    self.live_bot.get_account_balance()
                )

                if self.use_probe_entry:
                    units_demo = int(base_demo_units * self.probe_size_pct)
                    units_live = int(base_live_units * self.probe_size_pct)
                    print(
                        f"🔍 PROBE ENTRY: {signal} {units_demo} demo / {units_live} live"
                    )
                    self.is_probe_position = True
                    self.probe_entry_candle = self.candle_count
                else:
                    units_demo = base_demo_units
                    units_live = base_live_units

                success, price = self.demo_bot.open_position(signal, units_demo)
                demo_fill = {"success": success, "price": price, "units": units_demo}
                print(f"   ✅ Demo: {signal} {units_demo:,} @ {price:.3f}")

                live_fill = self.live_bot.open_position(signal, units_live)
                if live_fill["success"]:
                    print(
                        f"   ✅ Live: {signal} {units_live:,} @ {live_fill['price']:.3f}"
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
