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

    def _get_summary_dict(self) -> dict:
        """Get summary as a dictionary for JSON export."""
        now = datetime.now()
        total_trades = self.stats["wins"] + self.stats["losses"]
        win_rate = (self.stats["wins"] / total_trades * 100) if total_trades > 0 else 0

        return {
            "date": now.strftime("%Y-%m-%d"),
            "bot": "forex_bot",
            "summary": {
                "iterations": self.stats["iterations"],
                "trades_executed": self.stats["trades_executed"],
                "win_rate": round(win_rate, 1),
                "wins": self.stats["wins"],
                "losses": self.stats["losses"],
                "total_pnl_pips": round(self.stats["total_pnl_pips"], 1),
                "total_pnl_usd": round(self.stats["total_pnl_usd"], 2),
                "best_trade": self.stats["best_trade"],
                "worst_trade": self.stats["worst_trade"],
                "hold_reasons": dict(self.stats["hold_reasons"]),
            },
        }

    def upload_to_gcs(self, summary_type: str = "daily"):
        """Upload summary to Google Cloud Storage."""
        if os.environ.get("USE_CLOUD_STORAGE", "").lower() != "true":
            return None

        try:
            from google.cloud import storage

            bucket_name = os.environ.get("GCS_BUCKET_NAME", "forex-bot-state")
            client = storage.Client()
            bucket = client.bucket(bucket_name)

            # Create JSON report
            report_data = self._get_summary_dict()
            report_data["summary_type"] = summary_type

            filename = (
                f"reports/{summary_type}_{datetime.now().strftime('%Y-%m-%d')}.json"
            )
            blob = bucket.blob(filename)
            blob.upload_from_string(
                json.dumps(report_data, indent=2), content_type="application/json"
            )

            print(f"📤 Report uploaded to GCS: gs://{bucket_name}/{filename}")
            return f"gs://{bucket_name}/{filename}"

        except Exception as e:
            print(f"❌ GCS upload failed: {e}")
            return None

    def save_summary(self, summary_type: str = "daily"):
        """Save summary to file and optionally upload to GCS."""
        summary = self.generate_summary(summary_type)
        filename = f"{summary_type}_summary_{datetime.now().strftime('%Y-%m-%d')}.txt"
        filepath = os.path.join(self.data_dir, filename)

        with open(filepath, "w") as f:
            f.write(summary)

        print(f"📊 Summary saved to: {filepath}")

        # Upload to GCS if enabled
        self.upload_to_gcs(summary_type)

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
