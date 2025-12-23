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
from stable_baselines3 import PPO
from utils.oanda_connector import OANDAConnector
from utils.feature_engineering import add_all_features
from utils.position_manager import PositionManager
from utils.forex_decision_reasoning import ForexDecisionReasoner
from utils.performance_tracker import PerformanceTracker
from utils.bot_state_manager import BotStateManager
from version import __version__, __commit__, __build_date__

print("=" * 60)
print("OANDA PAPER TRADING BOT")
print(f"Version {__version__} ({__commit__})")
print(f"Build Date: {__build_date__}")
print("RL Model + Position Manager Integration")
print("=" * 60)
print()

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

    def __init__(self):
        print("🤖 Initializing Paper Trading Bot...")

        print("🔌 Connecting to OANDA...", flush=True)
        # Connect to OANDA
        self.oanda = OANDAConnector(environment="practice")
        print(f"✅ OANDA connected - Account: {self.oanda.account_id}", flush=True)

        # Load RL model
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

            print("   → Loading model from models/ppo_improved_final...", flush=True)
            self.model = PPO.load("models/ppo_improved_final", device="cpu")

            elapsed = time.time() - start_time
            print("=" * 60, flush=True)
            print(f"✅ MODEL LOADED! (took {elapsed:.1f} seconds)", flush=True)
            print("=" * 60, flush=True)

        except Exception as e:
            print("=" * 60, flush=True)
            print(f"❌ ERROR LOADING MODEL: {e}", flush=True)
            print("=" * 60, flush=True)
            import traceback

            traceback.print_exc()
            raise

        # Initialize Position Manager
        print("🛡️  Initializing Position Manager...", flush=True)
        self.pm = PositionManager(**PM_CONFIG)
        print("✅ Position Manager ready", flush=True)

        # Initialize Decision Reasoner
        print("🧠 Initializing Decision Reasoning...", flush=True)
        self.reasoner = ForexDecisionReasoner()
        print("✅ Decision Reasoning ready", flush=True)

        # Initialize Performance Tracker
        if ENABLE_PERFORMANCE_TRACKING:
            print("📊 Initializing Performance Tracker...", flush=True)
            self.tracker = PerformanceTracker()
            print("✅ Performance Tracker ready", flush=True)
        else:
            self.tracker = None

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

        print("\n✅ Bot initialized successfully!\n")

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

        current_price = price_data["bid"]

        # Calculate P/L
        entry = pos["entry"]
        pips_profit = (current_price - entry) / 0.0001
        profit_usd = pips_profit * (UNITS_PER_TRADE / 100)  # Approximate

        # Ask Position Manager
        pm_result = self.pm.manage_position(
            position_id=pos["position_id"],
            symbol=instrument,
            direction="BUY",
            entry_price=entry,
            current_price=current_price,
            current_sl=pos["sl"],
            current_profit_usd=profit_usd,
        )

        timestamp = datetime.now().strftime("%H:%M:%S")

        # Print position status with reasoning
        print(f"\n[{timestamp}] {'=' * 60}")
        print(f"📊 POSITION MANAGEMENT: {instrument}")
        print("   Status: MONITORING")
        print(f"   Entry: {entry:.5f} | Current: {current_price:.5f}")
        print(f"   P/L: {pips_profit:+.1f} pips (${profit_usd:+.2f})")
        print(f"   Stop Loss: {pos['sl']:.5f}")

        if pm_result["action"] == "modify_sl":
            new_sl = pm_result["new_sl"]
            print("\n   🔄 ADJUSTING STOP LOSS")
            print(f"   Reason: {pm_result['reason']}")
            print(f"   New SL: {pos['sl']:.5f} → {new_sl:.5f}")
            print(f"   Protection: Locking in {((new_sl - entry) / 0.0001):.1f} pips")
            print("=" * 60)
            pos["sl"] = new_sl
            # Note: OANDA API doesn't easily allow SL modification on position

        elif pm_result["action"] == "close":
            print("\n   💰 CLOSING POSITION")
            print(f"   Reason: {pm_result['reason']}")
            print(f"   Final P/L: {pips_profit:+.1f} pips (${profit_usd:+.2f})")
            print("=" * 60)

            # Close on OANDA
            self.oanda.close_position(instrument)

            # Remove from tracking
            self.pm.remove_position(pos["position_id"])
            del self.positions[instrument]

        else:
            print("   ✅ No action needed - position within parameters")
            print("=" * 60)

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
        print(f"\n{'=' * 60}")
        print(f"🤖 RL MODEL PREDICTION - {instrument}")
        print(f"{'=' * 60}")
        print(
            f"   Action: {model_details['action_name']} (value={model_details['action']})"
        )
        print(f"   Confidence: {model_details['confidence'] * 100:.1f}%")
        print(f"   Probabilities:")
        print(f"      HOLD: {model_details['probabilities']['HOLD'] * 100:.1f}%")
        print(f"      BUY:  {model_details['probabilities']['BUY'] * 100:.1f}%")
        print(f"      SELL: {model_details['probabilities']['SELL'] * 100:.1f}%")
        print(f"   Features: {model_details['feature_count']} inputs")
        print(f"{'=' * 60}\n")

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
        print(f"\n[{timestamp}] {'=' * 60}")
        print(decision["reasoning"])
        print("=" * 60)

        # Execute trade if BUY signal
        if signal == 1:  # BUY signal
            # Got a buy signal - executing trade
            entry_price = price_data["ask"]
            sl_price = entry_price - (INITIAL_SL_PIPS * 0.0001)

            print(
                f"\n             Executing: Entry {entry_price:.5f}, SL {sl_price:.5f}"
            )

            # Place order on OANDA
            result = self.oanda.place_market_order(
                instrument=instrument, units=UNITS_PER_TRADE, stop_loss=sl_price
            )

            if result:
                position_id = f"{instrument}_{int(time.time())}"
                self.positions[instrument] = {
                    "entry": entry_price,
                    "sl": sl_price,
                    "position_id": position_id,
                }
                print(
                    f"             ✅ Order executed! Trade ID: {result.get('order_id', 'N/A')}\n"
                )
            else:
                print(f"             ❌ Order failed!\n")
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
        print("=" * 60)
        print("🚀 STARTING PAPER TRADING")
        print("=" * 60)
        print(f"Pairs in Fleet: {', '.join(PAIR_FLEET)}")
        print(f"Check interval: {CHECK_INTERVAL} seconds")
        print(f"Position size: {UNITS_PER_TRADE} units")
        print()

        # Show account info
        account = self.oanda.get_account_summary()
        if account:
            print(f"💰 Account Balance: ${account['balance']:,.2f}")
            print(f"   NAV: ${account['nav']:,.2f}")
            print(f"   Open Positions: {account['open_positions']}")
        print()
        print("Press Ctrl+C to stop")
        print("=" * 60)
        print()

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

                # Check for daily summary (at midnight)
                if ENABLE_PERFORMANCE_TRACKING and self.tracker:
                    if current_time.strftime("%H:%M") == DAILY_SUMMARY_TIME:
                        if current_time.date() != last_summary_date:
                            print("\n" + "=" * 60)
                            self.tracker.print_summary("daily")
                            self.tracker.save_summary("daily")
                            last_summary_date = current_time.date()

                            # Weekly summary on Friday
                            if current_time.weekday() == WEEKLY_SUMMARY_DAY:
                                self.tracker.print_summary("weekly")
                                self.tracker.save_summary("weekly")

                # Check for pair scanning trigger - REMOVED
                # Now using fleet strategy: check all pairs every iteration

                print(f"\n{'=' * 60}")
                print(f"[{timestamp}] Iteration #{iteration}")
                print(f"Checking {len(self.pair_fleet)} pairs in fleet")
                print("=" * 60)

                # Update dashboard state
                self.state_manager.update_iteration(iteration)

                # Update positions for dashboard
                dashboard_positions = []
                for instr, pos in self.positions.items():
                    current = self.oanda.get_current_price(instr)
                    if current:
                        pips = (current["bid"] - pos["entry"]) / 0.0001
                        pnl_usd = pips * 10  # Approximate for 1000 units
                        dashboard_positions.append(
                            {
                                "symbol": instr,
                                "entry": pos["entry"],
                                "current": current["bid"],
                                "pnl_pips": round(pips, 1),
                                "pnl_usd": round(pnl_usd, 2),
                            }
                        )
                self.state_manager.update_positions(dashboard_positions)

                # Show current positions summary
                if self.positions:
                    print(f"\n📍 Active Positions: {len(self.positions)}")
                    for instr, pos in self.positions.items():
                        current = self.oanda.get_current_price(instr)
                        if current:
                            pips = (current["bid"] - pos["entry"]) / 0.0001
                            print(f"   • {instr}: {pips:+.1f} pips")
                else:
                    print("\n📍 No active positions")

                print(f"\n🔍 Checking {len(self.pair_fleet)} pairs in fleet...\n")

                # Check each symbol
                # Check all pairs in fleet - trade first signal found
                for symbol in self.pair_fleet:
                    try:
                        self.check_symbol(symbol)
                    except Exception as e:
                        print(f"[{timestamp}] ⚠️  Error checking {symbol}: {e}")

                # Wait
                print(f"\n💤 Waiting {CHECK_INTERVAL} seconds until next check...")
                time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\n\n🛑 Stopping paper trading bot...")
            print("\n📊 Final Summary:")

            account = self.oanda.get_account_summary()
            if account:
                print(f"   Balance: ${account['balance']:,.2f}")
                print(f"   Unrealized P/L: ${account['unrealized_pl']:,.2f}")

            positions = self.oanda.get_open_positions()
            if positions:
                print(f"\n📍 Open Positions: {len(positions)}")
                for pos in positions:
                    print(
                        f"   {pos['instrument']}: {pos['long_units']} units, P/L: ${pos['unrealized_pl']:.2f}"
                    )

            print("\n✅ Bot stopped successfully")


if __name__ == "__main__":
    try:
        bot = PaperTradingBot()
        bot.run()
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback

        traceback.print_exc()
