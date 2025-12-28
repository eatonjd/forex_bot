"""
Daily Summary Collector for Trading Bots.

Collects trading data throughout the day and generates structured EOD reports.
"""

import json
import os
from datetime import datetime, date
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict


@dataclass
class TradeRecord:
    """Record of an executed trade."""

    timestamp: str
    symbol: str
    action: str  # BUY, SELL, STOP_LOSS
    shares: float
    price: float
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None


@dataclass
class DecisionRecord:
    """Record of a trading decision (executed or not)."""

    timestamp: str
    symbol: str
    action: int  # 0=HOLD, 1=BUY, 2=SELL
    executed: bool
    confidence: float
    regime: str
    sentiment: float
    model_votes: Dict[str, int] = field(default_factory=dict)
    reasoning: str = ""


@dataclass
class PositionRecord:
    """Record of an overnight position."""

    symbol: str
    shares: float
    entry_price: float
    current_price: float
    pnl: float
    regime: str
    confidence: float


class DailySummaryCollector:
    """
    Collects trading data throughout the day for EOD summary.

    Usage:
        collector = DailySummaryCollector("stock_bot", "AP")
        collector.set_start_balance(5000.00)

        # Throughout the day:
        collector.log_decision(...)
        collector.log_trade(...)
        collector.log_regime("bull")

        # At EOD:
        summary = collector.generate_summary(end_balance=5125.50)
    """

    # Environment codes
    ENV_CODES = {
        "alpaca_paper": "AP",
        "alpaca_live": "AL",
        "oanda_practice": "OP",
        "oanda_live": "OL",
    }

    def __init__(self, bot_name: str, env_code: str):
        """
        Initialize daily summary collector.

        Args:
            bot_name: "stock_bot" or "forex_bot"
            env_code: AP/AL/OP/OL
        """
        self.bot_name = bot_name
        self.env_code = env_code
        self.date = date.today()
        self.start_balance: Optional[float] = None

        # Collections
        self.decisions: List[DecisionRecord] = []
        self.trades: List[TradeRecord] = []
        self.regime_samples: List[str] = []
        self.sentiment_samples: List[float] = []
        self.overnight_positions: List[PositionRecord] = []

        # Forex-specific
        self.pips_pnl: float = 0.0
        self.margin_used: float = 0.0
        self.margin_available: float = 0.0

    def set_start_balance(self, balance: float):
        """Set the starting balance for the day."""
        self.start_balance = balance

    def log_decision(
        self,
        symbol: str,
        action: int,
        executed: bool,
        confidence: float,
        regime: str = "unknown",
        sentiment: float = 0.0,
        model_votes: Dict[str, int] = None,
        reasoning: str = "",
    ):
        """Log a trading decision."""
        self.decisions.append(
            DecisionRecord(
                timestamp=datetime.now().isoformat(),
                symbol=symbol,
                action=action,
                executed=executed,
                confidence=confidence,
                regime=regime,
                sentiment=sentiment,
                model_votes=model_votes or {},
                reasoning=reasoning,
            )
        )

        # Track regime and sentiment
        if regime and regime != "unknown":
            self.regime_samples.append(regime)
        if sentiment != 0.0:
            self.sentiment_samples.append(sentiment)

    def log_trade(
        self,
        symbol: str,
        action: str,
        shares: float,
        price: float,
        pnl: Optional[float] = None,
        pnl_pct: Optional[float] = None,
    ):
        """Log an executed trade."""
        self.trades.append(
            TradeRecord(
                timestamp=datetime.now().isoformat(),
                symbol=symbol,
                action=action,
                shares=shares,
                price=price,
                pnl=pnl,
                pnl_pct=pnl_pct,
            )
        )

    def log_regime(self, regime: str):
        """Log a regime sample."""
        self.regime_samples.append(regime)

    def log_overnight_position(
        self,
        symbol: str,
        shares: float,
        entry_price: float,
        current_price: float,
        regime: str = "unknown",
        confidence: float = 0.0,
    ):
        """Log a position being held overnight."""
        pnl = (current_price - entry_price) * shares
        self.overnight_positions.append(
            PositionRecord(
                symbol=symbol,
                shares=shares,
                entry_price=entry_price,
                current_price=current_price,
                pnl=pnl,
                regime=regime,
                confidence=confidence,
            )
        )

    def set_forex_metrics(
        self,
        pips_pnl: float,
        margin_used: float,
        margin_available: float,
    ):
        """Set forex-specific metrics."""
        self.pips_pnl = pips_pnl
        self.margin_used = margin_used
        self.margin_available = margin_available

    def _calculate_regime_breakdown(self) -> Dict[str, float]:
        """Calculate percentage of time in each regime."""
        if not self.regime_samples:
            return {}

        total = len(self.regime_samples)
        breakdown = {}
        for regime in set(self.regime_samples):
            count = self.regime_samples.count(regime)
            breakdown[regime] = round(count / total * 100, 1)
        return breakdown

    def _get_best_worst_trades(self) -> Dict[str, Optional[TradeRecord]]:
        """Get best and worst trades by P&L."""
        completed = [t for t in self.trades if t.pnl is not None]
        if not completed:
            return {"best": None, "worst": None}

        best = max(completed, key=lambda t: t.pnl)
        worst = min(completed, key=lambda t: t.pnl)
        return {"best": best, "worst": worst}

    def generate_summary(self, end_balance: float) -> Dict:
        """
        Generate the daily summary.

        Args:
            end_balance: Ending account balance

        Returns:
            Structured summary dictionary
        """
        start = self.start_balance or end_balance
        pnl = end_balance - start
        pnl_pct = (pnl / start * 100) if start > 0 else 0

        # Win/loss calculation
        completed_trades = [t for t in self.trades if t.pnl is not None]
        wins = sum(1 for t in completed_trades if t.pnl > 0)
        losses = sum(1 for t in completed_trades if t.pnl < 0)
        win_rate = (wins / len(completed_trades) * 100) if completed_trades else 0

        # Signals vs executed
        signals = len([d for d in self.decisions if d.action != 0])
        executed = len([d for d in self.decisions if d.executed])

        best_worst = self._get_best_worst_trades()

        summary = {
            "bot_name": self.bot_name,
            "env_code": self.env_code,
            "date": self.date.isoformat(),
            "balance": {
                "start": round(start, 2),
                "end": round(end_balance, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
            },
            "activity": {
                "signals_generated": signals,
                "trades_executed": executed,
                "wins": wins,
                "losses": losses,
                "win_rate": round(win_rate, 1),
            },
            "best_trade": asdict(best_worst["best"]) if best_worst["best"] else None,
            "worst_trade": asdict(best_worst["worst"]) if best_worst["worst"] else None,
            "overnight_positions": [asdict(p) for p in self.overnight_positions],
            "market_conditions": {
                "regime_breakdown": self._calculate_regime_breakdown(),
                "avg_sentiment": round(
                    sum(self.sentiment_samples) / len(self.sentiment_samples), 2
                )
                if self.sentiment_samples
                else 0,
            },
        }

        # Add forex-specific if applicable
        if self.bot_name == "forex_bot":
            summary["forex"] = {
                "pips_pnl": round(self.pips_pnl, 1),
                "margin_used": round(self.margin_used, 2),
                "margin_available": round(self.margin_available, 2),
                "margin_pct": round(
                    self.margin_used / (self.margin_used + self.margin_available) * 100,
                    1,
                )
                if (self.margin_used + self.margin_available) > 0
                else 0,
            }

        return summary

    def format_telegram_message(self, end_balance: float) -> str:
        """Generate formatted Telegram message."""
        s = self.generate_summary(end_balance)

        msg = f"📊 DAILY SUMMARY\n"
        msg += f"Bot: {s['bot_name']} | Env: {s['env_code']} | {s['date']}\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"💰 BALANCE\n"
        msg += f"   Start: ${s['balance']['start']:,.2f}\n"
        msg += f"   End: ${s['balance']['end']:,.2f}\n"
        msg += (
            f"   P&L: ${s['balance']['pnl']:+,.2f} ({s['balance']['pnl_pct']:+.2f}%)\n"
        )
        msg += f"━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"📈 ACTIVITY\n"
        msg += f"   Trades: {s['activity']['trades_executed']}/{s['activity']['signals_generated']} signals\n"
        msg += f"   Win Rate: {s['activity']['win_rate']}% ({s['activity']['wins']}W/{s['activity']['losses']}L)\n"

        if s["best_trade"]:
            msg += f"━━━━━━━━━━━━━━━━━━━━\n"
            msg += f"🏆 BEST/WORST\n"
            msg += (
                f"   Best: {s['best_trade']['symbol']} ${s['best_trade']['pnl']:+.2f}\n"
            )
        if s["worst_trade"]:
            msg += f"   Worst: {s['worst_trade']['symbol']} ${s['worst_trade']['pnl']:+.2f}\n"

        if s["overnight_positions"]:
            msg += f"━━━━━━━━━━━━━━━━━━━━\n"
            msg += f"🌙 OVERNIGHT\n"
            for p in s["overnight_positions"]:
                msg += f"   {p['symbol']}: {p['shares']} @ ${p['entry_price']:.2f}\n"

        if "forex" in s:
            msg += f"━━━━━━━━━━━━━━━━━━━━\n"
            msg += f"💱 FOREX\n"
            msg += f"   Pips: {s['forex']['pips_pnl']:+.1f}\n"
            msg += f"   Margin: {s['forex']['margin_pct']:.1f}% used\n"

        return msg

    def reset(self):
        """Reset for new day."""
        self.date = date.today()
        self.start_balance = None
        self.decisions = []
        self.trades = []
        self.regime_samples = []
        self.sentiment_samples = []
        self.overnight_positions = []
        self.pips_pnl = 0.0
        self.margin_used = 0.0
        self.margin_available = 0.0
