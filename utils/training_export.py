"""
Training Data Exporter for Trading Bots.

Captures decision/outcome pairs for model retraining and continuous improvement.
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class Observation:
    """Market observation at decision time."""

    # Technical indicators
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    ema_12: Optional[float] = None
    ema_26: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_lower: Optional[float] = None
    atr: Optional[float] = None

    # Price data
    price: Optional[float] = None
    volume: Optional[float] = None

    # Context
    regime: str = "unknown"
    sentiment: float = 0.0

    # Account state
    balance: Optional[float] = None
    position_size: Optional[float] = None
    position_value: Optional[float] = None


@dataclass
class Outcome:
    """Outcome of a trading decision."""

    exit_price: Optional[float] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    holding_hours: Optional[float] = None
    was_profitable: Optional[bool] = None
    exit_reason: str = ""  # "signal", "stop_loss", "take_profit", "eod"


@dataclass
class TrainingRecord:
    """Complete record for training."""

    # Identification
    timestamp: str
    symbol: str
    bot_name: str
    env_code: str

    # Decision
    action: int  # 0=HOLD, 1=BUY, 2=SELL
    action_name: str
    confidence: float
    model_votes: Dict[str, int] = field(default_factory=dict)

    # Context
    observation: Observation = field(default_factory=Observation)

    # Outcome (filled when position closes)
    outcome: Optional[Outcome] = None

    # Meta
    reasoning: str = ""


class TrainingDataExporter:
    """
    Exports trading decisions and outcomes for model retraining.

    Usage:
        exporter = TrainingDataExporter("stock_bot", "AP", log_dir="training_data")

        # Log a decision
        obs = Observation(rsi=55, macd=0.5, regime="bull")
        exporter.log_decision("GOOGL", 1, 0.78, obs, model_votes={"Model1": 1})

        # Later, log the outcome
        outcome = Outcome(pnl=45.20, pnl_pct=3.2, holding_hours=4.5)
        exporter.log_outcome("GOOGL", outcome)

        # Export for training
        data = exporter.export_for_training()
    """

    def __init__(self, bot_name: str, env_code: str, log_dir: str = "training_data"):
        self.bot_name = bot_name
        self.env_code = env_code
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)

        # Open decisions awaiting outcomes
        self.open_decisions: Dict[str, TrainingRecord] = {}

        # Completed records
        self.completed_records: List[TrainingRecord] = []

        # Load any existing data
        self._load_existing()

    def _get_log_file(self) -> Path:
        """Get current month's log file."""
        return self.log_dir / f"training_{datetime.now().strftime('%Y_%m')}.json"

    def _load_existing(self):
        """Load existing training records."""
        log_file = self._get_log_file()
        if log_file.exists():
            try:
                with open(log_file, "r") as f:
                    data = json.load(f)
                    # Reconstruct records (simplified - just load as dicts)
                    self.completed_records = data.get("completed", [])
            except Exception as e:
                print(f"Warning: Could not load training data: {e}")

    def _save(self):
        """Save training records."""
        log_file = self._get_log_file()
        try:
            data = {
                "bot_name": self.bot_name,
                "env_code": self.env_code,
                "last_updated": datetime.now().isoformat(),
                "completed": [
                    asdict(r) if isinstance(r, TrainingRecord) else r
                    for r in self.completed_records
                ],
            }
            with open(log_file, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            print(f"Warning: Could not save training data: {e}")

    def log_decision(
        self,
        symbol: str,
        action: int,
        confidence: float,
        observation: Observation,
        model_votes: Dict[str, int] = None,
        reasoning: str = "",
    ):
        """
        Log a trading decision.

        Args:
            symbol: Trading symbol
            action: 0=HOLD, 1=BUY, 2=SELL
            confidence: Model confidence
            observation: Market observation at decision time
            model_votes: Individual model predictions
            reasoning: Decision reasoning text
        """
        action_names = {0: "HOLD", 1: "BUY", 2: "SELL"}

        record = TrainingRecord(
            timestamp=datetime.now().isoformat(),
            symbol=symbol,
            bot_name=self.bot_name,
            env_code=self.env_code,
            action=action,
            action_name=action_names.get(action, "UNKNOWN"),
            confidence=confidence,
            model_votes=model_votes or {},
            observation=observation,
            reasoning=reasoning,
        )

        # Store for later outcome matching
        if action in [1, 2]:  # BUY or SELL
            self.open_decisions[symbol] = record
        else:
            # HOLD decisions are immediately complete
            self.completed_records.append(record)
            self._save()

    def log_outcome(
        self,
        symbol: str,
        outcome: Outcome,
    ):
        """
        Log the outcome of a previous decision.

        Args:
            symbol: Trading symbol
            outcome: The outcome of the trade
        """
        if symbol in self.open_decisions:
            record = self.open_decisions.pop(symbol)
            record.outcome = outcome

            # Set was_profitable based on P&L
            if outcome.pnl is not None:
                outcome.was_profitable = outcome.pnl > 0

            self.completed_records.append(record)
            self._save()

    def export_for_training(
        self,
        include_holds: bool = False,
        min_confidence: float = 0.0,
    ) -> List[Dict]:
        """
        Export completed records for model training.

        Args:
            include_holds: Whether to include HOLD decisions
            min_confidence: Minimum confidence threshold

        Returns:
            List of training records as dictionaries
        """
        records = []

        for r in self.completed_records:
            # Convert if needed
            if isinstance(r, TrainingRecord):
                record = asdict(r)
            else:
                record = r

            # Filter
            if not include_holds and record.get("action") == 0:
                continue
            if record.get("confidence", 0) < min_confidence:
                continue

            records.append(record)

        return records

    def export_to_file(
        self, output_file: str = "training_export.json", **kwargs
    ) -> str:
        """Export records to a file."""
        records = self.export_for_training(**kwargs)

        output_path = self.log_dir / output_file
        with open(output_path, "w") as f:
            json.dump(records, f, indent=2, default=str)

        print(f"📊 Exported {len(records)} records to {output_path}")
        return str(output_path)

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about collected training data."""
        total = len(self.completed_records)

        if total == 0:
            return {"total_records": 0}

        # Count by action
        actions = {"HOLD": 0, "BUY": 0, "SELL": 0}
        profitable = 0
        unprofitable = 0

        for r in self.completed_records:
            if isinstance(r, TrainingRecord):
                actions[r.action_name] = actions.get(r.action_name, 0) + 1
                if r.outcome and r.outcome.was_profitable is not None:
                    if r.outcome.was_profitable:
                        profitable += 1
                    else:
                        unprofitable += 1
            else:
                action_name = r.get("action_name", "UNKNOWN")
                actions[action_name] = actions.get(action_name, 0) + 1
                outcome = r.get("outcome", {})
                if outcome and outcome.get("was_profitable") is not None:
                    if outcome["was_profitable"]:
                        profitable += 1
                    else:
                        unprofitable += 1

        return {
            "total_records": total,
            "by_action": actions,
            "profitable": profitable,
            "unprofitable": unprofitable,
            "win_rate": round(profitable / (profitable + unprofitable) * 100, 1)
            if (profitable + unprofitable) > 0
            else 0,
            "open_decisions": len(self.open_decisions),
        }
