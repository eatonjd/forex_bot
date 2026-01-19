#!/usr/bin/env python3
"""
Trade Logger and Performance Analyzer.

Logs all trades with full context for continuous improvement.
Stores data in JSON format for easy analysis.
Supports both local file and Google Cloud Storage.

Usage:
    # Log a trade
    from utils.trade_logger import TradeLogger
    logger = TradeLogger()
    logger.log_trade("BUY", "QQQ", 2, 520.50, ...)

    # Analyze performance
    python utils/trade_logger.py --analyze
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any
from dataclasses import dataclass, asdict
from pathlib import Path
import statistics

# Try to import GCS, fall back to local file if not available
try:
    from google.cloud import storage

    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False


@dataclass
class TradeRecord:
    """Complete record of a trade for analysis."""

    # Trade details
    timestamp: str
    action: str  # BUY, SELL, STOP_LOSS
    symbol: str
    shares: float
    price: float
    total_value: float

    # Context at time of trade
    portfolio_value: float
    regime: str  # bull, bear, sideways, volatile
    sentiment: float  # -1 to 1

    # Model votes
    ensemble_decision: int  # 0=hold, 1=buy, 2=sell
    confidence: float
    model_votes: Dict[str, int]  # model_name -> action

    # Technical indicators snapshot
    rsi: float = None
    macd: float = None
    sma_20: float = None
    sma_50: float = None

    # Outcome (filled after position closed)
    exit_price: float = None
    exit_timestamp: str = None
    pnl: float = None
    pnl_pct: float = None
    holding_period_hours: float = None

    # Metadata
    stop_price: float = None
    trailing_stop: bool = False
    model_version: str = "1.0"


class TradeLogger:
    """Log trades and analyze performance. Supports local files and GCS."""

    def __init__(self, log_dir: str = "trade_logs", bucket_name: str = None):
        """
        Initialize trade logger.

        Args:
            log_dir: Directory to store trade logs (local)
            bucket_name: GCS bucket name (optional, uses env var if not provided)
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)

        # GCS configuration
        self.bucket_name = bucket_name or os.getenv(
            "GCS_BUCKET_NAME", "forex-bot-state"
        )
        self.use_gcs = (
            GCS_AVAILABLE and os.getenv("USE_CLOUD_STORAGE", "").lower() == "true"
        )
        self.gcs_client = None
        self.gcs_bucket = None

        if self.use_gcs:
            try:
                self.gcs_client = storage.Client()
                self.gcs_bucket = self.gcs_client.bucket(self.bucket_name)
                print(f"📝 Trade logger: GCS enabled ({self.bucket_name})")
            except Exception as e:
                print(f"⚠️ GCS init failed, using local: {e}")
                self.use_gcs = False
        else:
            print(f"📝 Trade logger: Local mode ({self.log_dir})")

        # Current open positions for P&L tracking
        self.open_positions = {}
        self._load_open_positions()

    def _get_log_file(self, date: datetime = None) -> Path:
        """Get log file for a specific date."""
        if date is None:
            date = datetime.now()
        return self.log_dir / f"trades_{date.strftime('%Y_%m')}.json"

    def _get_gcs_blob_name(self, date: datetime = None) -> str:
        """Get GCS blob name for a specific date."""
        if date is None:
            date = datetime.now()
        return f"trade_logs/trades_{date.strftime('%Y_%m')}.json"

    def _load_trades(self, log_file: Path) -> List[Dict]:
        """Load trades from storage (GCS or local)."""
        trades = []

        # Try GCS first if enabled
        if self.use_gcs and self.gcs_bucket:
            try:
                blob_name = f"trade_logs/{log_file.name}"
                blob = self.gcs_bucket.blob(blob_name)
                if blob.exists():
                    content = blob.download_as_text()
                    trades = json.loads(content)
            except Exception as e:
                print(f"⚠️ GCS load error: {e}")

        # Fallback to local file
        if not trades and log_file.exists():
            with open(log_file, "r") as f:
                trades = json.load(f)

        return trades

    def _save_trades(self, trades: List[Dict], log_file: Path):
        """Save trades to storage (GCS and local)."""
        content = json.dumps(trades, indent=2, default=str)

        # Always save locally
        with open(log_file, "w") as f:
            f.write(content)

        # Also save to GCS if enabled
        if self.use_gcs and self.gcs_bucket:
            try:
                blob_name = f"trade_logs/{log_file.name}"
                blob = self.gcs_bucket.blob(blob_name)
                blob.upload_from_string(content, content_type="application/json")
            except Exception as e:
                print(f"⚠️ GCS save error: {e}")

    def _load_open_positions(self):
        """Load open positions from file."""
        positions_file = self.log_dir / "open_positions.json"

        # Try GCS first
        if self.use_gcs and self.gcs_bucket:
            try:
                blob = self.gcs_bucket.blob("trade_logs/open_positions.json")
                if blob.exists():
                    content = blob.download_as_text()
                    self.open_positions = json.loads(content)
                    return
            except Exception as e:
                print(f"⚠️ GCS load positions error: {e}")

        # Fallback to local
        if positions_file.exists():
            with open(positions_file, "r") as f:
                self.open_positions = json.load(f)

    def _save_open_positions(self):
        """Save open positions to file (local and GCS)."""
        positions_file = self.log_dir / "open_positions.json"
        content = json.dumps(self.open_positions, indent=2, default=str)

        # Save locally
        with open(positions_file, "w") as f:
            f.write(content)

        # Also save to GCS if enabled
        if self.use_gcs and self.gcs_bucket:
            try:
                blob = self.gcs_bucket.blob("trade_logs/open_positions.json")
                blob.upload_from_string(content, content_type="application/json")
            except Exception as e:
                print(f"⚠️ GCS save positions error: {e}")

    def log_trade(
        self,
        action: str,
        symbol: str,
        shares: float,
        price: float,
        total_value: float,
        portfolio_value: float,
        regime: str = "unknown",
        sentiment: float = 0.0,
        ensemble_decision: int = 0,
        confidence: float = 0.0,
        model_votes: Dict[str, int] = None,
        stop_price: float = None,
        trailing_stop: bool = False,
        indicators: Dict[str, float] = None,
    ) -> TradeRecord:
        """
        Log a trade with full context.

        Args:
            action: BUY, SELL, or STOP_LOSS
            symbol: Stock symbol
            shares: Number of shares
            price: Price per share
            total_value: Total trade value
            portfolio_value: Portfolio value at time of trade
            regime: Market regime (bull/bear/sideways/volatile)
            sentiment: News sentiment score (-1 to 1)
            ensemble_decision: The ensemble's decision (0/1/2)
            confidence: Confidence score
            model_votes: Dictionary of model name -> vote
            stop_price: Stop-loss price if set
            trailing_stop: Whether trailing stop is enabled
            indicators: Dictionary of indicator values

        Returns:
            The trade record
        """
        indicators = indicators or {}

        record = TradeRecord(
            timestamp=datetime.now().isoformat(),
            action=action,
            symbol=symbol,
            shares=shares,
            price=price,
            total_value=total_value,
            portfolio_value=portfolio_value,
            regime=regime,
            sentiment=sentiment,
            ensemble_decision=ensemble_decision,
            confidence=confidence,
            model_votes=model_votes or {},
            stop_price=stop_price,
            trailing_stop=trailing_stop,
            rsi=indicators.get("rsi"),
            macd=indicators.get("macd"),
            sma_20=indicators.get("sma_20"),
            sma_50=indicators.get("sma_50"),
        )

        # Save to log file
        log_file = self._get_log_file()
        trades = self._load_trades(log_file)
        trades.append(asdict(record))
        self._save_trades(trades, log_file)

        # Track open positions for P&L
        if action == "BUY":
            if symbol not in self.open_positions:
                self.open_positions[symbol] = []
            self.open_positions[symbol].append(
                {
                    "entry_price": price,
                    "shares": shares,
                    "timestamp": record.timestamp,
                }
            )
            self._save_open_positions()

        elif action in ["SELL", "STOP_LOSS"]:
            # Calculate P&L for closed position
            if symbol in self.open_positions and self.open_positions[symbol]:
                entry = self.open_positions[symbol].pop(0)  # FIFO
                pnl = (price - entry["entry_price"]) * shares
                pnl_pct = ((price / entry["entry_price"]) - 1) * 100

                # Update the record with outcome
                record.exit_price = price
                record.exit_timestamp = record.timestamp
                record.pnl = pnl
                record.pnl_pct = pnl_pct

                # Calculate holding period
                entry_time = datetime.fromisoformat(entry["timestamp"])
                record.holding_period_hours = (
                    datetime.now() - entry_time
                ).total_seconds() / 3600

                # Update the saved record
                trades[-1] = asdict(record)
                self._save_trades(trades, log_file)
                self._save_open_positions()

        print(f"📝 Trade logged: {action} {shares} {symbol} @ ${price:.2f}")
        return record

    def log_forex_trade(
        self,
        action: str,  # "OPEN" or "CLOSE"
        direction: str,  # "LONG" or "SHORT"
        symbol: str = "USD_JPY",
        units: int = 0,
        price: float = 0.0,
        pnl: float = None,
        account_type: str = "demo",
        signal_data: Dict = None,
        market_data: Dict = None,
    ):
        """
        Log a forex trade with context for future analysis.

        Args:
            action: "OPEN" or "CLOSE"
            direction: "LONG" or "SHORT"
            symbol: Currency pair
            units: Position size
            price: Fill price
            pnl: P/L (for close trades)
            account_type: "demo" or "live"
            signal_data: RSI, BB position, confidence
            market_data: Current price, ATR, etc
        """
        signal_data = signal_data or {}
        market_data = market_data or {}

        trade = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "direction": direction,
            "symbol": symbol,
            "units": units,
            "price": price,
            "pnl": pnl,
            "account_type": account_type,
            # Signal context
            "rsi": signal_data.get("rsi"),
            "bb_position": signal_data.get("bb_position"),
            "confidence": signal_data.get("confidence"),
            "signal_reason": signal_data.get("reason"),
            # Market context
            "current_price": market_data.get("current_price"),
            "atr": market_data.get("atr"),
            "spread": market_data.get("spread"),
        }

        # Load existing forex trades
        forex_file = self.log_dir / "forex_trades.json"
        trades = []

        if self.use_gcs and self.gcs_bucket:
            try:
                blob = self.gcs_bucket.blob("trade_logs/forex_trades.json")
                if blob.exists():
                    trades = json.loads(blob.download_as_text())
            except Exception:
                pass

        if not trades and forex_file.exists():
            with open(forex_file, "r") as f:
                trades = json.load(f)

        trades.append(trade)

        # Save trades
        content = json.dumps(trades, indent=2, default=str)
        with open(forex_file, "w") as f:
            f.write(content)

        if self.use_gcs and self.gcs_bucket:
            try:
                blob = self.gcs_bucket.blob("trade_logs/forex_trades.json")
                blob.upload_from_string(content, content_type="application/json")
            except Exception as e:
                print(f"⚠️ GCS forex save error: {e}")

        print(f"📝 Forex trade: {action} {direction} {units} {symbol} @ {price:.3f}")
        return trade

    def get_all_trades(self, days: int = None) -> List[Dict]:
        """
        Get all trades, optionally filtered by recency.

        Args:
            days: Only include trades from last N days

        Returns:
            List of trade records
        """
        all_trades = []

        # Read from GCS if enabled
        if self.use_gcs and self.gcs_bucket:
            try:
                blobs = self.gcs_bucket.list_blobs(prefix="trade_logs/trades_")
                for blob in blobs:
                    if blob.name.endswith(".json"):
                        content = blob.download_as_text()
                        trades = json.loads(content)
                        if isinstance(trades, list):
                            all_trades.extend(trades)
            except Exception as e:
                print(f"⚠️ GCS read error in get_all_trades: {e}")
        else:
            # Fall back to local files
            for log_file in sorted(self.log_dir.glob("trades_*.json")):
                all_trades.extend(self._load_trades(log_file))

        if days:
            cutoff = datetime.now() - timedelta(days=days)
            all_trades = [
                t for t in all_trades if datetime.fromisoformat(t["timestamp"]) > cutoff
            ]

        return all_trades

    def get_performance_summary(self, days: int = 30) -> Dict[str, Any]:
        """
        Get performance summary.

        Args:
            days: Lookback period in days

        Returns:
            Performance metrics
        """
        trades = self.get_all_trades(days=days)

        if not trades:
            return {"error": "No trades found"}

        # Separate buys and sells
        buys = [t for t in trades if t["action"] == "BUY"]
        sells = [t for t in trades if t["action"] in ["SELL", "STOP_LOSS"]]

        # Calculate P&L
        completed_trades = [t for t in sells if t.get("pnl") is not None]

        if not completed_trades:
            return {
                "total_trades": len(trades),
                "buys": len(buys),
                "sells": len(sells),
                "completed_trades": 0,
                "total_pnl": 0.0,
                "avg_pnl": 0.0,
                "avg_pnl_pct": 0.0,
                "win_rate": 0.0,
                "winners": 0,
                "losers": 0,
                "avg_winner": 0.0,
                "avg_loser": 0.0,
                "best_trade": 0.0,
                "worst_trade": 0.0,
                "profit_factor": 0.0,
                "regime_performance": {},
                "model_accuracy": {},
                "message": "No completed trades with P&L yet",
            }

        pnls = [t["pnl"] for t in completed_trades]
        pnl_pcts = [t["pnl_pct"] for t in completed_trades]

        winners = [p for p in pnls if p > 0]
        losers = [p for p in pnls if p < 0]

        summary = {
            "period_days": days,
            "total_trades": len(trades),
            "completed_trades": len(completed_trades),
            "total_pnl": sum(pnls),
            "avg_pnl": statistics.mean(pnls),
            "avg_pnl_pct": statistics.mean(pnl_pcts),
            "win_rate": len(winners) / len(completed_trades) * 100,
            "winners": len(winners),
            "losers": len(losers),
            "avg_winner": statistics.mean(winners) if winners else 0,
            "avg_loser": statistics.mean(losers) if losers else 0,
            "best_trade": max(pnls),
            "worst_trade": min(pnls),
            "profit_factor": abs(sum(winners) / sum(losers))
            if losers
            else float("inf"),
        }

        # Regime analysis
        regime_performance = {}
        for t in completed_trades:
            regime = t.get("regime", "unknown")
            if regime not in regime_performance:
                regime_performance[regime] = []
            regime_performance[regime].append(t["pnl"])

        summary["regime_performance"] = {
            k: {"count": len(v), "total_pnl": sum(v), "avg_pnl": statistics.mean(v)}
            for k, v in regime_performance.items()
        }

        # Model vote analysis
        model_performance = {}
        for t in completed_trades:
            for model, vote in t.get("model_votes", {}).items():
                if model not in model_performance:
                    model_performance[model] = {"correct": 0, "incorrect": 0}

                # Check if model vote was profitable
                if t["action"] == "SELL":
                    was_profitable = t["pnl"] > 0
                    if (vote == 2 and was_profitable) or (
                        vote != 2 and not was_profitable
                    ):
                        model_performance[model]["correct"] += 1
                    else:
                        model_performance[model]["incorrect"] += 1

        for model, perf in model_performance.items():
            total = perf["correct"] + perf["incorrect"]
            perf["accuracy"] = (perf["correct"] / total * 100) if total > 0 else 0

        summary["model_accuracy"] = model_performance

        return summary

    def get_improvement_suggestions(self) -> List[str]:
        """Get suggestions for improving the bot based on trade history."""
        summary = self.get_performance_summary(days=30)
        suggestions = []

        if "error" in summary:
            return ["Not enough trade data yet. Keep trading to gather insights."]

        if summary.get("win_rate", 0) < 50:
            suggestions.append(
                f"⚠️ Win rate is {summary['win_rate']:.1f}%. Consider:\n"
                "   - Tightening entry criteria (higher confidence threshold)\n"
                "   - Adding more confirmation signals"
            )

        if summary.get("profit_factor", 0) < 1.5:
            suggestions.append(
                f"⚠️ Profit factor is {summary.get('profit_factor', 0):.2f}. Consider:\n"
                "   - Letting winners run longer (adjust trailing stop)\n"
                "   - Cutting losers faster (tighter stop-loss)"
            )

        # Check regime performance
        regime_perf = summary.get("regime_performance", {})
        for regime, perf in regime_perf.items():
            if perf["avg_pnl"] < 0:
                suggestions.append(
                    f"⚠️ Losing money in {regime} regime (avg P&L: ${perf['avg_pnl']:.2f}). Consider:\n"
                    "   - Reduce position size or skip trading in {regime} markets\n"
                    "   - Train a specialized model for {regime} conditions"
                )

        # Check model accuracy
        model_acc = summary.get("model_accuracy", {})
        for model, perf in model_acc.items():
            if perf.get("accuracy", 0) < 45:
                suggestions.append(
                    f"⚠️ Model '{model}' has low accuracy ({perf['accuracy']:.1f}%). Consider:\n"
                    "   - Reducing its weight in the ensemble\n"
                    "   - Retraining with more recent data"
                )

        if not suggestions:
            suggestions.append("✅ Performance looks good! Keep monitoring.")

        return suggestions

    def export_for_training(self, output_file: str = "training_feedback.json"):
        """
        Export trade data in a format suitable for retraining models.

        This creates a dataset of (observation, action, outcome) tuples
        that can be used to improve the reward function or fine-tune models.
        """
        trades = self.get_all_trades()
        completed_trades = [t for t in trades if t.get("pnl") is not None]

        training_data = []
        for t in completed_trades:
            training_data.append(
                {
                    "timestamp": t["timestamp"],
                    "symbol": t["symbol"],
                    "action": t["action"],
                    "regime": t["regime"],
                    "sentiment": t["sentiment"],
                    "indicators": {
                        "rsi": t.get("rsi"),
                        "macd": t.get("macd"),
                        "sma_20": t.get("sma_20"),
                        "sma_50": t.get("sma_50"),
                    },
                    "model_votes": t.get("model_votes", {}),
                    "confidence": t["confidence"],
                    "outcome": {
                        "pnl": t["pnl"],
                        "pnl_pct": t["pnl_pct"],
                        "holding_period_hours": t.get("holding_period_hours"),
                        "was_profitable": t["pnl"] > 0,
                    },
                }
            )

        output_path = self.log_dir / output_file
        with open(output_path, "w") as f:
            json.dump(training_data, f, indent=2)

        print(f"📊 Exported {len(training_data)} trades to {output_path}")
        return str(output_path)

    def generate_markdown_report(self, days: int = 30) -> str:
        """Generate a detailed markdown report file."""
        summary = self.get_performance_summary(days=days)
        date_str = datetime.now().strftime("%Y-%m-%d")
        report_file = self.log_dir / f"report_{date_str}.md"

        if "error" in summary:
            with open(report_file, "w") as f:
                f.write(f"# 📊 Trading Bot Performance Report\n")
                f.write(f"**Date:** {date_str}\n\n")
                f.write(f"> **Status:** ⏳ {summary['error']}\n\n")
                f.write(
                    "The bot is running but hasn't completed enough trades to generate a full statistical report.\n"
                )
                f.write("Check back later once trading activity has occurred.")

            print(f"📄 Report generated: {report_file}")
            return str(report_file)

        with open(report_file, "w") as f:
            f.write("# 📊 Trading Bot Performance Report\n")
            f.write(f"**Date:** {date_str}\n")
            f.write(f"**Period:** Last {days} days\n\n")

            f.write("## 📈 Executive Summary\n")
            f.write("| Metric | Value |\n")
            f.write("|---|---|\n")
            f.write(f"| **Total P&L** | **${summary['total_pnl']:,.2f}** |\n")
            f.write(f"| Win Rate | {summary['win_rate']:.1f}% |\n")
            f.write(f"| Profit Factor | {summary['profit_factor']:.2f} |\n")
            f.write(f"| Total Trades | {summary['total_trades']} |\n")
            f.write(
                f"| Avg P&L | ${summary['avg_pnl']:,.2f} ({summary['avg_pnl_pct']:+.2f}%) |\n"
            )
            f.write("\n")

            f.write("## 🌤️ Regime Performance\n")
            f.write("| Regime | Trades | win Rate | Avg P&L | Total P&L |\n")
            f.write("|---|---|---|---|---|\n")
            for regime, perf in summary.get("regime_performance", {}).items():
                emoji = "🟢" if perf["avg_pnl"] > 0 else "🔴"
                f.write(
                    f"| {emoji} {regime.capitalize()} | {perf['count']} | "
                    f"N/A | ${perf['avg_pnl']:.2f} | ${perf['total_pnl']:.2f} |\n"
                )
            f.write("\n")

            f.write("## 🤖 Model Accuracy\n")
            f.write("| Model | Accuracy | Correct | Incorrect |\n")
            f.write("|---|---|---|---|\n")
            for model, perf in summary.get("model_accuracy", {}).items():
                emoji = "✅" if perf.get("accuracy", 0) > 50 else "⚠️"
                f.write(
                    f"| {emoji} {model} | **{perf.get('accuracy', 0):.1f}%** | "
                    f"{perf['correct']} | {perf['incorrect']} |\n"
                )
            f.write("\n")

            f.write("## 💡 Improvement Suggestions\n")
            for suggestion in self.get_improvement_suggestions():
                f.write(f"- {suggestion}\n")
            f.write("\n")

            f.write("---\n")
            f.write("*Generated by Big E's Trading Bot*\n")

        print(f"📄 Report generated: {report_file}")
        return str(report_file)


def print_performance_report():
    """Print a nice performance report."""
    logger = TradeLogger()
    summary = logger.get_performance_summary(days=30)

    print("\n" + "=" * 60)
    print("📊 TRADING BOT PERFORMANCE REPORT (Last 30 Days)")
    print("=" * 60)

    if "error" in summary:
        print(f"\n{summary['error']}")
        return

    print(f"\n📈 OVERALL PERFORMANCE")
    print(f"   Total Trades: {summary['total_trades']}")
    print(f"   Completed Trades: {summary['completed_trades']}")
    print(f"   Total P&L: ${summary['total_pnl']:,.2f}")
    print(
        f"   Average P&L: ${summary['avg_pnl']:,.2f} ({summary['avg_pnl_pct']:+.2f}%)"
    )

    print(f"\n🎯 WIN/LOSS ANALYSIS")
    print(f"   Win Rate: {summary['win_rate']:.1f}%")
    print(f"   Winners: {summary['winners']} (avg: ${summary['avg_winner']:,.2f})")
    print(f"   Losers: {summary['losers']} (avg: ${summary['avg_loser']:,.2f})")
    print(f"   Profit Factor: {summary['profit_factor']:.2f}")
    print(f"   Best Trade: ${summary['best_trade']:,.2f}")
    print(f"   Worst Trade: ${summary['worst_trade']:,.2f}")

    print(f"\n🌤️ REGIME PERFORMANCE")
    for regime, perf in summary.get("regime_performance", {}).items():
        emoji = "📈" if perf["avg_pnl"] > 0 else "📉"
        print(
            f"   {emoji} {regime.capitalize()}: {perf['count']} trades, avg P&L: ${perf['avg_pnl']:,.2f}"
        )

    print(f"\n🤖 MODEL ACCURACY")
    for model, perf in summary.get("model_accuracy", {}).items():
        emoji = "✅" if perf.get("accuracy", 0) > 50 else "⚠️"
        print(f"   {emoji} {model}: {perf.get('accuracy', 0):.1f}%")

    print(f"\n💡 IMPROVEMENT SUGGESTIONS")
    for suggestion in logger.get_improvement_suggestions():
        print(f"   {suggestion}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    import sys

    if "--analyze" in sys.argv:
        print_performance_report()
    elif "--report" in sys.argv:
        logger = TradeLogger()
        logger.generate_markdown_report()
    else:
        # Demo
        print("📝 Trade Logger Demo\n")

        logger = TradeLogger()

        # Log a sample trade
        logger.log_trade(
            action="BUY",
            symbol="QQQ",
            shares=2,
            price=520.50,
            total_value=1041.00,
            portfolio_value=5000.00,
            regime="bull",
            sentiment=0.3,
            ensemble_decision=1,
            confidence=0.75,
            model_votes={"QQQ_Bull": 1, "QQQ_Bear": 0, "SPY_General": 1},
            stop_price=494.48,
            trailing_stop=True,
            indicators={"rsi": 55.2, "macd": 2.5, "sma_20": 515.0, "sma_50": 505.0},
        )

        print("\n✅ Demo complete! Run with --analyze to see performance report.")
