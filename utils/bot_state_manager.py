"""
Bot State Manager

Writes bot state to JSON file and optionally to Cloud Storage for dashboard consumption.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any


class BotStateManager:
    """Manages bot state persistence for dashboard"""

    def __init__(self, state_file: str = "bot_state.json"):
        self.state_file = Path(state_file)
        self.use_cloud_storage = (
            os.getenv("USE_CLOUD_STORAGE", "false").lower() == "true"
        )
        self.bucket_name = os.getenv("GCS_BUCKET_NAME", "forex-bot-state")

        # Initialize Cloud Storage if enabled
        if self.use_cloud_storage:
            try:
                from google.cloud import storage

                self.storage_client = storage.Client()
                self.bucket = self.storage_client.bucket(self.bucket_name)
                print(f"✅ Cloud Storage enabled: {self.bucket_name}")
            except Exception as e:
                print(f"⚠️  Cloud Storage initialization failed: {e}")
                print("   Falling back to local file only")
                self.use_cloud_storage = False

        self.state = {
            "version": "1.1.0",
            "commit": "enhanced-reasoning",
            "status": "Running",
            "iteration": 0,
            "last_update": datetime.now().isoformat(),
            "positions": [],
            "total_pnl_pips": 0.0,
            "total_pnl_usd": 0.0,
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "symbols": ["EUR_USD", "GBP_USD"],
            "hold_reasons": {},
        }

    def update(self, updates: Dict[str, Any]):
        """Update state and write to file"""
        self.state.update(updates)
        self.state["last_update"] = datetime.now().isoformat()
        self._write()

    def update_iteration(self, iteration: int):
        """Update iteration count"""
        self.state["iteration"] = iteration
        self._write()

    def update_positions(self, positions: list):
        """Update active positions"""
        self.state["positions"] = positions
        self._write()

    def add_hold_reason(self, reason: str):
        """Track HOLD reason"""
        if "hold_reasons" not in self.state:
            self.state["hold_reasons"] = {}
        self.state["hold_reasons"][reason] = (
            self.state["hold_reasons"].get(reason, 0) + 1
        )
        self._write()

    def update_performance(
        self, trades: int, wins: int, losses: int, pnl_pips: float, pnl_usd: float
    ):
        """Update performance metrics"""
        self.state.update(
            {
                "trades": trades,
                "wins": wins,
                "losses": losses,
                "total_pnl_pips": pnl_pips,
                "total_pnl_usd": pnl_usd,
            }
        )
        self._write()

    def update_symbols(self, symbols: list):
        """Update current trading symbols"""
        self.state["symbols"] = symbols
        self._write()

    def _write(self):
        """Write state to JSON file and optionally to Cloud Storage"""
        # Always write to local file
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2)

        # Also write to Cloud Storage if enabled
        if self.use_cloud_storage:
            try:
                blob = self.bucket.blob("bot_state.json")
                blob.upload_from_string(
                    json.dumps(self.state, indent=2), content_type="application/json"
                )
            except Exception as e:
                # Don't crash bot if cloud write fails
                print(f"⚠️  Cloud Storage write failed: {e}")
