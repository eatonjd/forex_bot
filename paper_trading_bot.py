#!/usr/bin/env python3
"""
OANDA Paper Trading Bot with RL + Position Manager

Live paper trading bot that:
1. Fetches real-time OANDA data
2. Uses RL model for entry signals
3. Uses Position Manager for exit optimization
4. Executes trades on OANDA practice account

Author: Forex Bot Team
Created: 2025-12-19
"""

import time
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Any, Dict, List, Optional
from utils.oanda_connector import OANDAConnector
from utils.feature_engineering import add_all_features
from utils.position_manager import PositionManager
from utils.forex_decision_reasoning import ForexDecisionReasoner
from utils.performance_tracker import PerformanceTracker
from utils.bot_state_manager import BotStateManager
from utils.notifications import get_notifier
from utils.daily_summary import DailySummaryCollector
from utils.llm_factory import create_llm_analyzer, get_analyzer_info
from utils.market_calendar import is_forex_market_open, hours_until_market_open
from version import __version__, __commit__, __build_date__
from config import (
    LLM_PROVIDER,
    LLM_RATE_LIMIT_SECONDS,
    LLM_REQUIRE_CONFIRMATION,
    LLM_MIN_CONFIDENCE,
)

print("=" * 60, flush=True)
print("OANDA PAPER TRADING BOT", flush=True)
print(f"Version {__version__} ({__commit__})", flush=True)
print(f"Build Date: {__build_date__}", flush=True)
print("RL Model + Position Manager Integration", flush=True)
print("=" * 60, flush=True)
print("", flush=True)

# Configuration - Multi-Pair Fleet Strategy
# Bot checks ALL pairs every iteration and trades first signal found
PAIR_FLEET = [
    "EUR_USD",  # Major pair - low spread
    "GBP_USD",  # Volatile major
    "USD_JPY",  # Safe haven
    "AUD_USD",  # Commodity currency
    "USD_CAD",  # Oil-correlated
]

CHECK_INTERVAL = 300  # Check every 5 minutes
UNITS_PER_TRADE = 1000  # 1000 units = 0.01 lot (micro lot)
INITIAL_SL_PIPS = 30
MAX_CONCURRENT_POSITIONS = 1  # Trade one pair at a time

# Performance tracking
ENABLE_PERFORMANCE_TRACKING = True
DAILY_SUMMARY_TIME = "00:00"  # Midnight
WEEKLY_SUMMARY_DAY = 4  # Friday (0=Monday, 4=Friday)
SCAN_TOP_N_PAIRS = 2  # Number of pairs to trade

PM_CONFIG = {
    "enable_breakeven": True,
    "breakeven_pips": 20.0,
    "breakeven_offset": 5.0,
    "enable_trailing": True,
    "trailing_start_pips": 30.0,
    "trailing_step_pips": 10.0,
    "trailing_distance_pips": 15.0,
    "enable_auto_close": False,
}


class PaperTradingBot:
    """Paper trading bot with RL + PM"""

    def __init__(self, status_tracker: dict = None):
        print("🤖 Initializing Paper Trading Bot...", flush=True)
        self.status_tracker = status_tracker

        self._update_status("oanda_connected", False)
        print("🔌 Connecting to OANDA...", flush=True)
        # Connect to OANDA
        self.oanda = OANDAConnector(environment="practice")
        print(f"✅ OANDA connected - Account: {self.oanda.account_id}", flush=True)
        self._update_status("oanda_connected", True)

        # Load RL model
        self._update_status("model_loaded", False)
        print("=" * 60, flush=True)
        print("📦 LOADING RL MODEL - This may take 1-2 minutes...", flush=True)
        print("=" * 60, flush=True)

        import time

        start_time = time.time()

        try:
            import torch

            print(f"   → PyTorch version: {torch.__version__}", flush=True)

            # Force CPU (Cloud Run doesn't have GPU)
            torch.set_num_threads(2)  # Limit threads for Cloud Run
            print("   → Set PyTorch to CPU mode (2 threads)", flush=True)

            print("   → Loading Stable Baselines 3...", flush=True)
            from stable_baselines3 import PPO

            print("   → Loading model from models/ppo_improved_final...", flush=True)
            self.model = PPO.load("models/ppo_improved_final", device="cpu")

            elapsed = time.time() - start_time
            print("=" * 60, flush=True)
            print(f"✅ MODEL LOADED! (took {elapsed:.1f} seconds)", flush=True)
            print("=" * 60, flush=True)
            self._update_status("model_loaded", True)

        except Exception as e:
            print("=" * 60, flush=True)
            print(f"❌ ERROR LOADING MODEL: {e}", flush=True)
            print("=" * 60, flush=True)
            import traceback

            traceback.print_exc()
            self._update_status("error", str(e))
            raise

        # Initialize Position Manager
        self._update_status("position_manager_ready", False)
        print("🛡️  Initializing Position Manager...", flush=True)
        self.pm = PositionManager(**PM_CONFIG)
        print("✅ Position Manager ready", flush=True)
        self._update_status("position_manager_ready", True)

        # Initialize Decision Reasoner
        self._update_status("decision_reasoning_ready", False)
        print("🧠 Initializing Decision Reasoning...", flush=True)
        self.reasoner = ForexDecisionReasoner()
        print("✅ Decision Reasoning ready", flush=True)
        self._update_status("decision_reasoning_ready", True)

        # Initialize Performance Tracker
        if ENABLE_PERFORMANCE_TRACKING:
            print("📊 Initializing Performance Tracker...", flush=True)
            self.tracker = PerformanceTracker()
            print("✅ Performance Tracker ready", flush=True)
        else:
            self.tracker = None

        # Initialize notifier for SMS/push notifications
        self.notifier = get_notifier()

        # Track positions
        self.positions = {}  # {instrument: {entry, sl, position_id}}
        self.pair_fleet = PAIR_FLEET.copy()  # List of pairs to check each iteration

        # Initialize state manager for dashboard
        self.state_manager = BotStateManager()
        self.state_manager.update(
            {
                "status": "Running",
                "symbols": self.pair_fleet,
            }
        )

        # Initialize daily summary collector for enhanced EOD reports
        env_code = "OP"  # OANDA Practice
        self.summary_collector = DailySummaryCollector("forex_bot", env_code)

        # Initialize LLM analyzer (Ollama or Gemini based on config)
        self.llm_analyzer = create_llm_analyzer(
            provider=LLM_PROVIDER,
            rate_limit_seconds=LLM_RATE_LIMIT_SECONDS,
        )
        self.llm_enabled = self.llm_analyzer is not None and getattr(
            self.llm_analyzer, "enabled", False
        )

        if self.llm_enabled:
            info = get_analyzer_info(self.llm_analyzer)
            print(f"🧠 LLM analyzer enabled ({info['provider'].upper()})", flush=True)
            print(f"   Model: {info['model']}", flush=True)
            print(f"   Rate limit: {LLM_RATE_LIMIT_SECONDS}s per symbol", flush=True)
            print(f"   Confirmation mode: {LLM_REQUIRE_CONFIRMATION}", flush=True)
        else:
            print(
                f"ℹ️ LLM analyzer disabled (LLM_PROVIDER='{LLM_PROVIDER}')", flush=True
            )

        print("\n✅ Bot initialized successfully!\n", flush=True)
        if self.status_tracker:
            self.status_tracker["initialization"]["completed"] = True

        # Send startup notification
        account = self.oanda.get_account_summary()
        balance = account.get("balance", 0) if account else 0

        # Set collector start balance
        if account:
            self.summary_collector.set_start_balance(balance)

        self.notifier.send_startup_alert(
            symbol=", ".join(self.pair_fleet[:3]) + "...",
            strategy="Forex RL + PM",
            models_count=1,
            balance=balance,
        )

        # Close any existing trades on startup to prevent FIFO issues
        self._close_all_existing_trades()

        # Initial sync with OANDA
        self.sync_positions_with_oanda()

    def sync_positions_with_oanda(self):
        """Sync internal positions with reality on OANDA"""
        print("\n🔍 Syncing positions with OANDA...", flush=True)
        try:
            real_positions = self.oanda.get_open_positions()
            real_instruments = [p["instrument"] for p in real_positions]

            # Check for ghost positions (we think we have them, OANDA doesn't)
            ghosts = []
            for instrument in list(self.positions.keys()):
                if instrument not in real_instruments:
                    ghosts.append(instrument)

            if ghosts:
                print(
                    f"⚠️  Cleaning up {len(ghosts)} ghost positions: {', '.join(ghosts)}",
                    flush=True,
                )
                for instrument in ghosts:
                    if self.tracker:
                        self.tracker.record_exit(
                            instrument, 0.0, 0.0, "Ghost position cleanup"
                        )

                    # Remove from PM and local tracking
                    pos = self.positions[instrument]
                    self.pm.remove_position(pos["position_id"])
                    del self.positions[instrument]

            # Note: We don't automatically add positions found on OANDA that we DON'T track,
            # because we lack the entry_price and sl data for them.

            print(f"✅ Sync complete. Active trades: {len(self.positions)}", flush=True)

        except Exception as e:
            print(f"❌ Error during position sync: {e}", flush=True)

    def _close_all_existing_trades(self):
        """Close all existing trades on OANDA to prevent FIFO issues on startup."""
        print("\n🧹 Checking for orphaned trades on OANDA...", flush=True)
        try:
            import oandapyV20.endpoints.trades as trades_api

            endpoint = trades_api.OpenTrades(accountID=self.oanda.account_id)
            response = self.oanda.api.request(endpoint)
            open_trades = response.get("trades", [])

            if not open_trades:
                print("✅ No orphaned trades found - starting fresh", flush=True)
                return

            print(
                f"⚠️  Found {len(open_trades)} orphaned trades - closing for clean start",
                flush=True,
            )

            for trade in open_trades:
                trade_id = trade["id"]
                instrument = trade["instrument"]
                units = trade["currentUnits"]

                try:
                    close_endpoint = trades_api.TradeClose(
                        accountID=self.oanda.account_id, tradeID=trade_id
                    )
                    self.oanda.api.request(close_endpoint)
                    print(f"   ✅ Closed {instrument} ({units} units)", flush=True)
                except Exception as e:
                    print(f"   ❌ Failed to close {instrument}: {e}", flush=True)

            print("✅ Cleanup complete - ready to trade", flush=True)

        except Exception as e:
            print(f"❌ Error closing orphaned trades: {e}", flush=True)

    def _get_pip_size(self, instrument: str) -> float:
        """Get pip size for instrument (0.01 for JPY, 0.0001 otherwise)"""
        return 0.01 if "JPY" in instrument.upper() else 0.0001

    def _update_status(self, stage: str, value: Any):
        """Update the external status tracker if provided"""
        if self.status_tracker and "initialization" in self.status_tracker:
            if stage in self.status_tracker["initialization"]:
                self.status_tracker["initialization"][stage] = value
            elif stage == "error":
                self.status_tracker["initialization"]["error"] = value

    def get_features_for_symbol(self, instrument: str) -> pd.DataFrame:
        """Fetch and prepare features for a symbol"""
        # Get historical data
        candles = self.oanda.get_candles(instrument, granularity="H1", count=100)

        if not candles:
            return None

        # Convert to DataFrame
        df = pd.DataFrame(candles)
        df.columns = ["time", "Open", "High", "Low", "Close", "Volume"]

        # Add features
        df = add_all_features(df)

        return df

    def get_rl_signal(self, df: pd.DataFrame) -> tuple:
        """Get signal from RL model with verbose output

        Returns:
            tuple: (action, prediction_details)
                action: 0=HOLD, 1=BUY, 2=SELL
                prediction_details: dict with model internals
        """
        if df is None or len(df) == 0:
            return 0, {"error": "No data"}

        # Use last row features
        feature_cols = [
            c for c in df.columns if c not in ["Open", "High", "Low", "Close", "Volume"]
        ]
        features = df[feature_cols].iloc[-1].values.astype(np.float32)

        # Add account features (simplified)
        account_features = np.array([1.0, 0.0, 1.0, 0.0], dtype=np.float32)
        obs = np.concatenate([features, account_features])

        # Ensure we have exactly 29 features (model expects this)
        if len(obs) != 29:
            # Truncate or pad to 29
            if len(obs) > 29:
                obs = obs[:29]
            else:
                obs = np.pad(obs, (0, 29 - len(obs)), mode="constant")

        # Get prediction with probability (no reshape, model expects 1D array)
        action, _states = self.model.predict(obs, deterministic=True)
        action = int(action)

        # Get action probabilities for confidence
        try:
            # Get the policy network's probability distribution
            import torch

            with torch.no_grad():
                obs_tensor = torch.FloatTensor(obs).unsqueeze(0)
                action_probs = self.model.policy.get_distribution(
                    obs_tensor
                ).distribution.probs
                probs = action_probs.cpu().numpy()[0]
        except:
            # Fallback if we can't get probabilities
            probs = [0.33, 0.33, 0.34]  # Assume equal if unavailable

        # Build detailed output
        action_names = {0: "HOLD", 1: "BUY", 2: "SELL"}
        details = {
            "action": action,
            "action_name": action_names.get(action, "UNKNOWN"),
            "probabilities": {
                "HOLD": float(probs[0]),
                "BUY": float(probs[1]),
                "SELL": float(probs[2]) if len(probs) > 2 else 0.0,
            },
            "confidence": float(probs[action]) if action < len(probs) else 0.5,
            "feature_count": len(obs),
        }

        return action, details

    def check_and_manage_position(self, instrument: str):
        """Check if we have a position and manage with PM"""
        if instrument not in self.positions:
            return

        pos = self.positions[instrument]
        price_data = self.oanda.get_current_price(instrument)

        if not price_data:
            return

        direction = pos.get("direction", "BUY")
        current_price = price_data["bid"] if direction == "BUY" else price_data["ask"]

        pip_size = self._get_pip_size(instrument)
        # Calculate P/L
        entry = pos["entry"]
        if direction == "BUY":
            pips_profit = (current_price - entry) / pip_size
        else:
            pips_profit = (entry - current_price) / pip_size

        profit_usd = pips_profit * (UNITS_PER_TRADE / 100)  # Approximate

        # Ask Position Manager
        pm_result = self.pm.manage_position(
            position_id=pos["position_id"],
            symbol=instrument,
            direction=direction,
            entry_price=entry,
            current_price=current_price,
            current_sl=pos["sl"],
            current_profit_usd=profit_usd,
        )

        timestamp = datetime.now().strftime("%H:%M:%S")

        # Print position status with reasoning
        print(f"\n[{timestamp}] {'=' * 60}", flush=True)
        print(f"📊 POSITION MANAGEMENT: {instrument}", flush=True)
        print("   Status: MONITORING", flush=True)
        print(f"   Entry: {entry:.5f} | Current: {current_price:.5f}", flush=True)
        print(f"   P/L: {pips_profit:+.1f} pips (${profit_usd:+.2f})", flush=True)
        print(f"   Stop Loss: {pos['sl']:.5f}", flush=True)

        if pm_result["action"] == "modify_sl":
            new_sl = pm_result["new_sl"]
            print("\n   🔄 ADJUSTING STOP LOSS", flush=True)
            print(f"   Reason: {pm_result['reason']}", flush=True)
            print(f"   New SL: {pos['sl']:.5f} → {new_sl:.5f}", flush=True)
            print(
                f"   Protection: Locking in {((new_sl - entry) / self._get_pip_size(instrument)):.1f} pips",
                flush=True,
            )
            print("=" * 60, flush=True)
            pos["sl"] = new_sl
            # Note: OANDA API doesn't easily allow SL modification on position

        elif pm_result["action"] == "close":
            print("\n   💰 CLOSING POSITION", flush=True)
            print(f"   Reason: {pm_result['reason']}", flush=True)
            print(
                f"   Final P/L: {pips_profit:+.1f} pips (${profit_usd:+.2f})",
                flush=True,
            )
            print("=" * 60, flush=True)

            # Close on OANDA
            self.oanda.close_position(instrument)

            # Remove from tracking
            self.pm.remove_position(pos["position_id"])
            del self.positions[instrument]

        else:
            print("   ✅ No action needed - position within parameters", flush=True)
            print("=" * 60, flush=True)

    def check_symbol(self, instrument: str):
        """Check a symbol for trading signals"""
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Manage existing position first
        if instrument in self.positions:
            self.check_and_manage_position(instrument)
            return

        # Get features and signal from RL model
        df = self.get_features_for_symbol(instrument)
        if df is None:
            print(f"[{timestamp}] ⚠️  {instrument}: Unable to fetch data")
            return

        signal, model_details = self.get_rl_signal(df)

        # Print verbose model output
        print(f"\n{'=' * 60}", flush=True)
        print(f"🤖 RL MODEL PREDICTION - {instrument}", flush=True)
        print(f"{'=' * 60}", flush=True)
        print(
            f"   Action: {model_details['action_name']} (value={model_details['action']})",
            flush=True,
        )
        print(f"   Confidence: {model_details['confidence'] * 100:.1f}%", flush=True)
        print(f"   Probabilities:", flush=True)
        print(
            f"      HOLD: {model_details['probabilities']['HOLD'] * 100:.1f}%",
            flush=True,
        )
        print(
            f"      BUY:  {model_details['probabilities']['BUY'] * 100:.1f}%",
            flush=True,
        )
        print(
            f"      SELL: {model_details['probabilities']['SELL'] * 100:.1f}%",
            flush=True,
        )
        print(f"   Features: {model_details['feature_count']} inputs", flush=True)
        print(f"{'=' * 60}\n", flush=True)

        # Get current price
        price_data = self.oanda.get_current_price(instrument)
        if not price_data:
            print(f"[{timestamp}] ⚠️  {instrument}: Unable to fetch current price")
            return

        current_price = price_data["bid"]

        # Get technical indicators for reasoning
        indicators = {}
        last_row = df.iloc[-1]
        for col in ["rsi", "macd", "sma_20", "sma_50", "atr"]:
            if col in df.columns:
                indicators[col] = float(last_row[col])

        # Get LLM AI analysis (Smart Money Concepts + Wyckoff)
        llm_analysis = None
        if self.llm_enabled and self.llm_analyzer:
            try:
                # Handle both uppercase and lowercase column names
                open_col = "open" if "open" in df.columns else "Open"
                high_col = "high" if "high" in df.columns else "High"
                low_col = "low" if "low" in df.columns else "Low"
                close_col = "close" if "close" in df.columns else "Close"
                vol_col = (
                    "volume"
                    if "volume" in df.columns
                    else "Volume"
                    if "Volume" in df.columns
                    else None
                )

                price_data_for_llm = {
                    "open": df[open_col].tolist()[-50:],
                    "high": df[high_col].tolist()[-50:],
                    "low": df[low_col].tolist()[-50:],
                    "close": df[close_col].tolist()[-50:],
                    "volume": df[vol_col].tolist()[-50:] if vol_col else [0] * 50,
                }
                llm_analysis = self.llm_analyzer.analyze_symbol(
                    instrument, price_data_for_llm, "H1"
                )
                if llm_analysis.get("from_cache"):
                    print(
                        f"   📦 Using cached LLM analysis for {instrument}",
                        flush=True,
                    )
            except Exception as e:
                print(f"   ⚠️ LLM analysis failed: {e}", flush=True)

        # Generate decision reasoning for ALL signals (HOLD, BUY, SELL)
        decision = self.reasoner.analyze_and_decide(
            symbol=instrument,
            rl_action=signal,
            price=current_price,
            indicators=indicators,
            spread=price_data.get("spread"),
            position_manager_state={"active": True} if signal == 1 else None,
        )

        # Print reasoning for ALL decisions
        print(f"\n[{timestamp}] {'=' * 60}", flush=True)
        print(decision["reasoning"], flush=True)

        # Print LLM AI analysis if available
        if llm_analysis and llm_analysis.get("confidence", 0) > 0:
            provider = llm_analysis.get("provider", "LLM").upper()
            print(f"🧠 {provider} AI (SMC + Wyckoff)", flush=True)
            print(f"   Bias: {llm_analysis.get('bias', 'N/A')}", flush=True)
            print(
                f"   Signal: {llm_analysis.get('signal', 'N/A')} ({llm_analysis.get('confidence', 0)}% conf)",
                flush=True,
            )
            print(f"   Reasoning: {llm_analysis.get('reasoning', 'N/A')}", flush=True)
        print("=" * 60, flush=True)

        # Execute trade if BUY or SELL signal
        if signal in [1, 2]:  # 1=BUY, 2=SELL
            # Check LLM confirmation if required
            if LLM_REQUIRE_CONFIRMATION and llm_analysis:
                llm_confidence = llm_analysis.get("confidence", 0)
                llm_bias = llm_analysis.get("bias", "NEUTRAL")

                # Check if LLM agrees with RL model
                rl_direction = "BUY" if signal == 1 else "SELL"
                llm_agrees = False

                if (
                    rl_direction == "BUY"
                    and llm_bias == "BULLISH"
                    and llm_confidence >= LLM_MIN_CONFIDENCE
                ):
                    llm_agrees = True
                elif (
                    rl_direction == "SELL"
                    and llm_bias == "BEARISH"
                    and llm_confidence >= LLM_MIN_CONFIDENCE
                ):
                    llm_agrees = True

                if not llm_agrees:
                    print(
                        f"             ⏸️ LLM confirmation failed for {rl_direction}:",
                        flush=True,
                    )
                    print(
                        f"                LLM bias: {llm_bias}, confidence: {llm_confidence}% (min: {LLM_MIN_CONFIDENCE}%)",
                        flush=True,
                    )
                    print(
                        "                Skipping trade - RL and LLM disagree",
                        flush=True,
                    )
                    return
                else:
                    print(
                        f"             ✅ LLM confirms {rl_direction} ({llm_bias}, {llm_confidence}% confidence)",
                        flush=True,
                    )

            # Check if we're at max positions
            if len(self.positions) >= MAX_CONCURRENT_POSITIONS:
                print(
                    f"             ⏸️ Max positions ({MAX_CONCURRENT_POSITIONS}) reached, skipping {instrument}",
                    flush=True,
                )
                return

            # Check for existing OANDA trade in this instrument (FIFO prevention)
            try:
                import oandapyV20.endpoints.trades as trades_api

                endpoint = trades_api.OpenTrades(accountID=self.oanda.account_id)
                response = self.oanda.api.request(endpoint)
                existing_trades = [
                    t
                    for t in response.get("trades", [])
                    if t["instrument"] == instrument
                ]
                if existing_trades:
                    print(
                        f"             ⏸️ Existing trade in {instrument} detected - skipping to avoid FIFO",
                        flush=True,
                    )
                    return
            except Exception as e:
                print(
                    f"             ⚠️ Could not check existing trades: {e}", flush=True
                )

            # Got a signal - executing trade
            direction = "BUY" if signal == 1 else "SELL"
            entry_price = price_data["ask"] if signal == 1 else price_data["bid"]

            # SL calculation: -pips for BUY, +pips for SELL
            pip_size = self._get_pip_size(instrument)
            sl_offset = INITIAL_SL_PIPS * pip_size
            sl_raw = entry_price - sl_offset if signal == 1 else entry_price + sl_offset

            # Round SL to correct precision for OANDA (3 decimals for JPY, 5 for others)
            precision = 3 if "JPY" in instrument.upper() else 5
            sl_price = round(sl_raw, precision)

            print(
                f"\n             Executing: {direction} | Entry {entry_price:.5f}, SL {sl_price:.5f}",
                flush=True,
            )

            # Place order on OANDA
            # units are positive for Buy, negative for Sell
            trade_units = UNITS_PER_TRADE if signal == 1 else -UNITS_PER_TRADE

            result = self.oanda.place_market_order(
                instrument=instrument, units=trade_units, stop_loss=sl_price
            )

            if result:
                position_id = f"{instrument}_{int(time.time())}"
                self.positions[instrument] = {
                    "entry": entry_price,
                    "sl": sl_price,
                    "position_id": position_id,
                    "direction": direction,
                }
                print(
                    f"             ✅ {direction} Order executed! Trade ID: {result.get('order_id', 'N/A')}\n",
                    flush=True,
                )

                # Send trade notification
                self.notifier.send_trade_alert(
                    action=direction,
                    symbol=instrument,
                    shares=abs(trade_units),
                    price=entry_price,
                    total_value=abs(trade_units),  # Units for forex
                    stop_price=sl_price,
                )
            else:
                print(f"             ❌ {direction} Order failed!\n", flush=True)
                self.notifier.send_error_alert(
                    f"{direction} order failed for {instrument}"
                )
        else:
            # HOLD or SELL - track reason for dashboard
            # Track HOLD reason for performance tracker
            if self.tracker:
                # Extract reason from decision
                if "Wide spread" in decision["reasoning"]:
                    reason = "Wide spread"
                elif "Confidence too low" in decision["reasoning"]:
                    reason = "Low confidence"
                elif (
                    "No clear trend" in decision["reasoning"]
                    or "neutral" in decision["reasoning"].lower()
                ):
                    reason = "Neutral market"
                elif "overbought" in decision["reasoning"].lower():
                    reason = "RSI overbought"
                elif "weak" in decision["reasoning"].lower():
                    reason = "Weak signal"
                else:
                    reason = "Other"

                self.tracker.record_hold(instrument, reason)
                self.state_manager.add_hold_reason(reason)

    def run(self):
        """Main trading loop"""
        print("=" * 60, flush=True)
        print("🚀 STARTING PAPER TRADING", flush=True)
        print("=" * 60, flush=True)
        print(f"Pairs in Fleet: {', '.join(PAIR_FLEET)}", flush=True)
        print(f"Check interval: {CHECK_INTERVAL} seconds", flush=True)
        print(f"Position size: {UNITS_PER_TRADE} units", flush=True)
        print("", flush=True)

        # Show account info
        account = self.oanda.get_account_summary()
        if account:
            print(f"💰 Account Balance: ${account['balance']:,.2f}", flush=True)
            print(f"   NAV: ${account['nav']:,.2f}", flush=True)
            print(f"   Open Positions: {account['open_positions']}", flush=True)
        print("", flush=True)
        print("Press Ctrl+C to stop", flush=True)
        print("=" * 60, flush=True)
        print("", flush=True)

        try:
            iteration = 0
            last_summary_date = datetime.now().date()

            while True:
                iteration += 1
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                current_time = datetime.now()

                # Track iteration
                if self.tracker:
                    self.tracker.record_iteration()

                # Check if forex market is open
                is_open, market_reason = is_forex_market_open()
                if not is_open:
                    print(f"\n🌙 {market_reason}", flush=True)
                    hours_left = hours_until_market_open()
                    if hours_left > 1:
                        # Sleep longer when market is closed for a while
                        sleep_time = min(3600, hours_left * 3600 / 2)  # Max 1 hour
                        print(
                            f"   Sleeping for {sleep_time / 60:.0f} minutes until closer to market open",
                            flush=True,
                        )
                        time.sleep(sleep_time)
                    else:
                        print(
                            f"   Market opens in {hours_left:.1f} hours. Checking again in 5 min.",
                            flush=True,
                        )
                        time.sleep(300)
                    continue  # Skip this iteration

                # Check for daily summary (at midnight)
                if ENABLE_PERFORMANCE_TRACKING and self.tracker:
                    if current_time.strftime("%H:%M") == DAILY_SUMMARY_TIME:
                        if current_time.date() != last_summary_date:
                            print("\n" + "=" * 60, flush=True)
                            self.tracker.print_summary("daily")
                            self.tracker.save_summary("daily")
                            last_summary_date = current_time.date()

                            # Send daily summary notification
                            account = self.oanda.get_account_summary()
                            if account:
                                # Set forex-specific metrics
                                self.summary_collector.set_forex_metrics(
                                    pips_pnl=self.tracker.stats.get(
                                        "total_pnl_pips", 0
                                    ),
                                    margin_used=account.get("margin_used", 0),
                                    margin_available=account.get("margin_available", 0),
                                )
                                # Try enhanced summary first
                                if hasattr(
                                    self.notifier, "send_enhanced_daily_summary"
                                ):
                                    self.notifier.send_enhanced_daily_summary(
                                        collector=self.summary_collector,
                                        end_balance=account.get(
                                            "nav", account.get("balance", 0)
                                        ),
                                    )
                                else:
                                    self.notifier.send_daily_summary(
                                        start_value=account.get("balance", 0),
                                        end_value=account.get(
                                            "nav", account.get("balance", 0)
                                        ),
                                        trades_count=self.tracker.daily_trades
                                        if hasattr(self.tracker, "daily_trades")
                                        else 0,
                                    )

                            # Weekly summary on Friday
                            if current_time.weekday() == WEEKLY_SUMMARY_DAY:
                                self.tracker.print_summary("weekly")
                                self.tracker.save_summary("weekly")

                # Check for pair scanning trigger - REMOVED
                # Now using fleet strategy: check all pairs every iteration

                print(f"\n{'=' * 60}", flush=True)
                print(f"[{timestamp}] Iteration #{iteration}", flush=True)
                print(f"Checking {len(self.pair_fleet)} pairs in fleet", flush=True)
                print("=" * 60, flush=True)

                # Update status tracker heartbeat
                if self.status_tracker:
                    self.status_tracker["last_heartbeat"] = time.time()
                    self.status_tracker["iteration"] = iteration

                # Update dashboard state
                self.state_manager.update_iteration(iteration)

                # Sync positions every 10 iterations to prevent ghosting
                if iteration % 10 == 0:
                    self.sync_positions_with_oanda()

                # Update positions for dashboard
                dashboard_positions = []
                for instr, pos in self.positions.items():
                    current = self.oanda.get_current_price(instr)
                    if current:
                        direction = pos.get("direction", "BUY")
                        price = current["bid"] if direction == "BUY" else current["ask"]

                        pip_size = self._get_pip_size(instr)
                        if direction == "BUY":
                            pips = (price - pos["entry"]) / pip_size
                        else:
                            pips = (pos["entry"] - price) / pip_size

                        pnl_usd = pips * (UNITS_PER_TRADE / 100)
                        dashboard_positions.append(
                            {
                                "symbol": instr,
                                "direction": direction,
                                "entry": pos["entry"],
                                "current": price,
                                "pnl_pips": round(pips, 1),
                                "pnl_usd": round(pnl_usd, 2),
                            }
                        )
                self.state_manager.update_positions(dashboard_positions)

                # Show current positions summary
                if self.positions:
                    print(f"\n📍 Active Positions: {len(self.positions)}", flush=True)
                    for instr, pos in self.positions.items():
                        current = self.oanda.get_current_price(instr)
                        if current:
                            direction = pos.get("direction", "BUY")
                            price = (
                                current["bid"] if direction == "BUY" else current["ask"]
                            )
                            pip_size = self._get_pip_size(instr)
                            if direction == "BUY":
                                pips = (price - pos["entry"]) / pip_size
                            else:
                                pips = (pos["entry"] - price) / pip_size
                            print(
                                f"   • {instr} ({direction}): {pips:+.1f} pips",
                                flush=True,
                            )
                else:
                    print("\n📍 No active positions", flush=True)

                print(
                    f"\n🔍 Checking {len(self.pair_fleet)} pairs in fleet...\n",
                    flush=True,
                )

                # Check each symbol
                # Check all pairs in fleet - trade first signal found
                for symbol in self.pair_fleet:
                    try:
                        self.check_symbol(symbol)
                    except Exception as e:
                        print(f"[{timestamp}] ⚠️  Error checking {symbol}: {e}")

                # Wait
                print(
                    f"\n💤 Waiting {CHECK_INTERVAL} seconds until next check...",
                    flush=True,
                )
                time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\n\n🛑 Stopping paper trading bot...", flush=True)
            print("\n📊 Final Summary:", flush=True)

            account = self.oanda.get_account_summary()
            if account:
                print(f"   Balance: ${account['balance']:,.2f}", flush=True)
                print(
                    f"   Unrealized P/L: ${account['unrealized_pl']:,.2f}", flush=True
                )

            positions = self.oanda.get_open_positions()
            if positions:
                print(f"\n📍 Open Positions: {len(positions)}", flush=True)
                for pos in positions:
                    print(
                        f"   {pos['instrument']}: {pos['long_units']} units, P/L: ${pos['unrealized_pl']:.2f}",
                        flush=True,
                    )

            print("\n✅ Bot stopped successfully", flush=True)


if __name__ == "__main__":
    try:
        bot = PaperTradingBot()
        bot.run()
    except Exception as e:
        print(f"\n❌ Fatal error: {e}", flush=True)
        import traceback

        traceback.print_exc()
