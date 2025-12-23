"""
Performance Tracker for Forex Trading Bot

Tracks trading activity, P&L, and generates daily/weekly summaries.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict


class PerformanceTracker:
    """Track bot performance and generate summaries"""

    def __init__(self, data_dir: str = "reports"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

        self.stats = {
            "start_time": datetime.now().isoformat(),
            "iterations": 0,
            "trades_executed": 0,
            "positions_opened": 0,
            "positions_closed": 0,
            "total_pnl_pips": 0.0,
            "total_pnl_usd": 0.0,
            "wins": 0,
            "losses": 0,
            "hold_reasons": defaultdict(int),
            "symbols_analyzed": defaultdict(int),
            "best_trade": None,
            "worst_trade": None,
        }

    def record_iteration(self):
        """Record a trading iteration"""
        self.stats["iterations"] += 1

    def record_hold(self, symbol: str, reason: str):
        """Record a HOLD decision with reason"""
        self.stats["hold_reasons"][reason] += 1
        self.stats["symbols_analyzed"][symbol] += 1

    def record_trade(self, symbol: str, pnl_pips: float, pnl_usd: float):
        """Record a completed trade"""
        self.stats["trades_executed"] += 1
        self.stats["total_pnl_pips"] += pnl_pips
        self.stats["total_pnl_usd"] += pnl_usd

        if pnl_pips > 0:
            self.stats["wins"] += 1
        else:
            self.stats["losses"] += 1

        # Track best/worst trades
        if (
            self.stats["best_trade"] is None
            or pnl_pips > self.stats["best_trade"]["pnl_pips"]
        ):
            self.stats["best_trade"] = {
                "symbol": symbol,
                "pnl_pips": pnl_pips,
                "pnl_usd": pnl_usd,
            }

        if (
            self.stats["worst_trade"] is None
            or pnl_pips < self.stats["worst_trade"]["pnl_pips"]
        ):
            self.stats["worst_trade"] = {
                "symbol": symbol,
                "pnl_pips": pnl_pips,
                "pnl_usd": pnl_usd,
            }

    def generate_summary(self, summary_type: str = "daily") -> str:
        """Generate performance summary"""
        now = datetime.now()

        if summary_type == "daily":
            title = f"DAILY PERFORMANCE SUMMARY - {now.strftime('%Y-%m-%d')}"
        else:
            title = (
                f"WEEKLY PERFORMANCE SUMMARY - Week ending {now.strftime('%Y-%m-%d')}"
            )

        # Calculate win rate
        total_trades = self.stats["wins"] + self.stats["losses"]
        win_rate = (self.stats["wins"] / total_trades * 100) if total_trades > 0 else 0

        # Format summary
        summary = f"""
{"=" * 60}
📊 {title}
{"=" * 60}

Trading Activity:
  • Iterations: {self.stats["iterations"]:,}
  • Trades Executed: {self.stats["trades_executed"]}
  • Win Rate: {win_rate:.1f}% ({self.stats["wins"]} wins, {self.stats["losses"]} losses)

Performance:
  • Total P&L: {self.stats["total_pnl_pips"]:+.1f} pips (${self.stats["total_pnl_usd"]:+.2f})
"""

        if self.stats["best_trade"]:
            summary += f"  • Best Trade: {self.stats['best_trade']['symbol']} {self.stats['best_trade']['pnl_pips']:+.1f} pips\n"

        if self.stats["worst_trade"]:
            summary += f"  • Worst Trade: {self.stats['worst_trade']['symbol']} {self.stats['worst_trade']['pnl_pips']:+.1f} pips\n"

        # Top reasons for not trading
        if self.stats["hold_reasons"]:
            summary += "\nReasons for Not Trading:\n"
            total_holds = sum(self.stats["hold_reasons"].values())
            sorted_reasons = sorted(
                self.stats["hold_reasons"].items(), key=lambda x: x[1], reverse=True
            )
            for reason, count in sorted_reasons[:5]:
                percentage = (count / total_holds * 100) if total_holds > 0 else 0
                summary += f"  • {reason}: {percentage:.1f}%\n"

        summary += f"\n{'=' * 60}\n"

        return summary

    def save_summary(self, summary_type: str = "daily"):
        """Save summary to file"""
        summary = self.generate_summary(summary_type)
        filename = f"{summary_type}_summary_{datetime.now().strftime('%Y-%m-%d')}.txt"
        filepath = os.path.join(self.data_dir, filename)

        with open(filepath, "w") as f:
            f.write(summary)

        print(f"📊 Summary saved to: {filepath}")
        return filepath

    def print_summary(self, summary_type: str = "daily"):
        """Print summary to console"""
        summary = self.generate_summary(summary_type)
        print(summary)

    def reset_daily_stats(self):
        """Reset stats for new day (keep cumulative data)"""
        # Save current stats before reset
        self.save_summary("daily")

        # Reset counters
        self.stats["iterations"] = 0
        self.stats["hold_reasons"] = defaultdict(int)
        self.stats["symbols_analyzed"] = defaultdict(int)
