#!/usr/bin/env python3
"""
Post-Trade Analyzer using Gemini AI.
Reviews completed trades, provides insights on why they won or lost,
identifies primary drivers, and recommends parameters adjustments.
"""

import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import google.generativeai as genai
from utils.trade_logger import TradeLogger
from utils.notifications import TradingNotifier
from utils.reward_engine import ForexRewardEngine

from config import GEMINI_MODEL, GEMINI_API_KEY

from dotenv import load_dotenv
load_dotenv()


class PostTradeAnalyzer:
    """Performs AI-driven post-trade analysis for completed forex trades."""

    def __init__(self):
        self.logger = TradeLogger()
        self.notifier = TradingNotifier()
        self.reward_engine = ForexRewardEngine(log_dir=self.logger.log_dir)
        self.reviews_file = self.logger.log_dir / "reviewed_trade_keys.json"
        self._load_reviewed_keys()

    def _load_reviewed_keys(self):
        """Load keys of already reviewed trades from local storage or GCS."""
        self.reviewed_keys = []
        if self.logger.use_gcs and self.logger.gcs_bucket:
            try:
                blob = self.logger.gcs_bucket.blob("trade_logs/reviewed_trade_keys.json")
                if blob.exists():
                    self.reviewed_keys = json.loads(blob.download_as_text())
                    return
            except Exception as e:
                print(f"⚠️ GCS load reviewed keys error: {e}")

        if self.reviews_file.exists():
            try:
                with open(self.reviews_file, "r") as f:
                    self.reviewed_keys = json.load(f)
            except Exception:
                pass

    def _save_reviewed_keys(self):
        """Save reviewed trade keys to local storage and GCS."""
        content = json.dumps(self.reviewed_keys, indent=2)
        with open(self.reviews_file, "w") as f:
            f.write(content)

        if self.logger.use_gcs and self.logger.gcs_bucket:
            try:
                blob = self.logger.gcs_bucket.blob("trade_logs/reviewed_trade_keys.json")
                blob.upload_from_string(content, content_type="application/json")
            except Exception as e:
                print(f"⚠️ GCS save reviewed keys error: {e}")

    def analyze_new_trades(self, days: int = 3) -> list:
        """
        Scan for newly closed trades and generate Gemini-driven reports.
        
        Args:
            days: Scan window in days
            
        Returns:
            List of generated review summaries
        """
        # Load all forex trades logged from GCS/local, or fallback to OANDA API
        forex_file = self.logger.log_dir / "forex_trades.json"
        trades = []

        if self.logger.use_gcs and self.logger.gcs_bucket:
            try:
                blob = self.logger.gcs_bucket.blob("trade_logs/forex_trades.json")
                if blob.exists():
                    trades = json.loads(blob.download_as_text())
            except Exception as e:
                print(f"⚠️ GCS load forex_trades error: {e}")

        if not trades and forex_file.exists():
            try:
                with open(forex_file, "r") as f:
                    trades = json.load(f)
            except Exception:
                pass

        closed_trades = []
        if trades:
            # Parse and pair OPEN and CLOSE events
            open_trades_map = {}
            for t in trades:
                symbol = t.get("symbol")
                action = t.get("action")
                if action == "OPEN":
                    open_trades_map[symbol] = t
                elif action == "CLOSE":
                    open_trade = open_trades_map.pop(symbol, None)
                    if open_trade:
                        closed_trades.append({
                            "open": open_trade,
                            "close": t
                        })

        # If no paired trades found in log files, pull directly from OANDA API
        if not closed_trades:
            try:
                from oandapyV20 import API
                from oandapyV20.endpoints.trades import TradesList
                
                # Try live account first, then demo
                for env_key, acct_key, env_name, acct_type in [
                    ("OANDA_API_KEY_LIVE", "OANDA_ACCOUNT_ID_LIVE", "live", "LIVE"),
                    ("OANDA_API_KEY", "OANDA_ACCOUNT_ID", "practice", "DEMO"),
                    ("OANDA_API_KEY_DEMO", "OANDA_ACCOUNT_ID_DEMO", "practice", "DEMO"),
                ]:
                    api_k = os.getenv(env_key)
                    acct_id = os.getenv(acct_key)
                    if not api_k or not acct_id:
                        continue
                    try:
                        oanda_api = API(access_token=api_k, environment=env_name)
                        r = TradesList(accountID=acct_id, params={"state": "CLOSED", "count": 20})
                        oanda_api.request(r)
                        raw_list = r.response.get("trades", [])
                        for t in raw_list:
                            units = float(t.get("initialUnits", 0))
                            pnl = float(t.get("realizedPL", 0))
                            price = float(t.get("price", 0))
                            close_price = float(t.get("averageClosePrice", price))
                            ot = t.get("openTime", "")
                            ct = t.get("closeTime", "")
                            closed_trades.append({
                                "open": {
                                    "symbol": t.get("instrument"),
                                    "direction": "LONG" if units > 0 else "SHORT",
                                    "units": abs(units),
                                    "price": price,
                                    "timestamp": ot,
                                    "account_id": acct_id,
                                    "account_type": acct_type,
                                    "signal_reason": "MEAN_REVERSION"
                                },
                                "close": {
                                    "symbol": t.get("instrument"),
                                    "direction": "LONG" if units > 0 else "SHORT",
                                    "units": abs(units),
                                    "price": close_price,
                                    "pnl": pnl,
                                    "timestamp": ct,
                                    "account_id": acct_id,
                                    "account_type": acct_type,
                                }
                            })
                    except Exception as oanda_err:
                        print(f"⚠️ OANDA pull closed trades error for {acct_type}: {oanda_err}")
            except Exception as e:
                print(f"⚠️ Direct OANDA fetch error: {e}")

        if not closed_trades:
            print("⚠️ No closed trades found to review")
            return []

        # Filter for new closed trades that haven't been reviewed
        new_reviews = []
        for ct in closed_trades:
            open_t = ct["open"]
            close_t = ct["close"]
            
            # Generate a unique key for the trade
            trade_key = f"{close_t.get('symbol')}_{open_t.get('timestamp')}_{close_t.get('timestamp')}"
            
            # Skip if already reviewed
            if trade_key in self.reviewed_keys:
                continue
                
            try:
                close_time_str = close_t.get("timestamp", "").replace("Z", "+00:00")
                close_time = datetime.fromisoformat(close_time_str)
                # If timezone aware vs naive
                if close_time.tzinfo:
                    now = datetime.now(close_time.tzinfo)
                else:
                    now = datetime.now()
                if (now - close_time) > timedelta(days=days):
                    continue
            except Exception:
                pass

            # Calculate duration & reward metrics
            try:
                ot_str = open_t.get("timestamp", "").replace("Z", "+00:00")
                ct_str = close_t.get("timestamp", "").replace("Z", "+00:00")
                ot = datetime.fromisoformat(ot_str)
                ct_dt = datetime.fromisoformat(ct_str)
                duration_hrs = (ct_dt - ot).total_seconds() / 3600.0
            except Exception:
                duration_hrs = 0.0

            pnl = float(close_t.get("pnl", 0.0))
            reward_metrics = self.reward_engine.calculate_trade_reward(
                pnl=pnl,
                duration_hrs=duration_hrs,
                atr=open_t.get("atr"),
                units=open_t.get("units", 10000),
                regime=open_t.get("signal_reason", "MEAN_REVERSION")
            )

            # Run Gemini analysis
            report = self._generate_gemini_report(open_t, close_t, reward_metrics=reward_metrics, duration_hrs=duration_hrs)
            if report:
                review_obj = {
                    "trade_key": trade_key,
                    "symbol": close_t.get("symbol"),
                    "direction": open_t.get("direction"),
                    "pnl": pnl,
                    "duration_hrs": round(duration_hrs, 2),
                    "reward_score": reward_metrics.get("reward_score", 0.0),
                    "efficiency_score": reward_metrics.get("efficiency_score", 0.0),
                    "report": report,
                    "timestamp": close_t.get("timestamp")
                }
                new_reviews.append(review_obj)
                self.reviewed_keys.append(trade_key)
                
                # Send notification immediately with account context
                try:
                    acct_id = close_t.get("account_id") or open_t.get("account_id") or ""
                    acct_type = (close_t.get("account_type") or open_t.get("account_type") or "demo").upper()
                    acct_info = f"{acct_id} ({acct_type})" if acct_id else acct_type
                    
                    full_report_msg = f"📌 Account: {acct_info}\n\n{report}"
                    self.notifier._send(full_report_msg, title=f"📊 Trade Review: {close_t.get('symbol')} [{acct_type}]")
                except Exception as e:
                    print(f"⚠️ Failed to send trade review notification: {e}")

        # Save reviewed keys & reports list
        if new_reviews:
            self._save_reviewed_keys()
            self._save_trade_reviews(new_reviews)

        return new_reviews

    def _save_trade_reviews(self, new_reviews: list):
        """Save detailed trade reviews list to JSON and GCS."""
        reviews_path = self.logger.log_dir / "trade_reviews.json"
        existing = []
        if reviews_path.exists():
            try:
                with open(reviews_path, "r") as f:
                    existing = json.load(f)
            except Exception:
                pass
        
        all_reviews = existing + new_reviews
        content = json.dumps(all_reviews, indent=2)
        with open(reviews_path, "w") as f:
            f.write(content)

        if self.logger.use_gcs and self.logger.gcs_bucket:
            try:
                blob = self.logger.gcs_bucket.blob("trade_logs/trade_reviews.json")
                blob.upload_from_string(content, content_type="application/json")
            except Exception as e:
                print(f"⚠️ GCS save trade reviews error: {e}")

        return new_reviews

    def _generate_gemini_report(self, open_t: dict, close_t: dict, reward_metrics: dict = None, duration_hrs: float = None) -> str:
        """Use Gemini to construct a structured post-trade analysis report."""
        pnl = float(close_t.get("pnl", 0.0))
        symbol = close_t.get("symbol")
        direction = close_t.get("direction")
        entry_price = open_t.get("price")
        exit_price = close_t.get("price")
        units = open_t.get("units", 10000)
        atr = open_t.get("atr")
        
        # Calculate duration if not provided
        if duration_hrs is None:
            try:
                ot = datetime.fromisoformat(open_t.get("timestamp", "").replace("Z", "+00:00"))
                ct = datetime.fromisoformat(close_t.get("timestamp", "").replace("Z", "+00:00"))
                duration_hrs = (ct - ot).total_seconds() / 3600.0
            except Exception:
                duration_hrs = 0.0

        # Calculate Quantitative AI Reward Score if not provided
        if reward_metrics is None:
            reward_metrics = self.reward_engine.calculate_trade_reward(
                pnl=pnl,
                duration_hrs=duration_hrs,
                atr=atr,
                units=units,
                regime=open_t.get("signal_reason", "MEAN_REVERSION")
            )
        sortino = self.reward_engine.calculate_rolling_sortino()

        trade_context = {
            "Symbol": symbol,
            "Direction": direction,
            "PnL": f"${pnl:+.2f}",
            "Account": f"{close_t.get('account_id', open_t.get('account_id', 'N/A'))} ({close_t.get('account_type', open_t.get('account_type', 'N/A'))})",
            "AI Reward Score": f"{reward_metrics['reward_score']:+.2f}",
            "Efficiency Score": f"{reward_metrics['efficiency_score']:+.2f}",
            "Rolling Portfolio Sortino": f"{sortino:.2f}",
            "Entry Price": entry_price,
            "Exit Price": exit_price,
            "Duration (Hours)": f"{duration_hrs:.2f}h",
            "Entry RSI": open_t.get("rsi"),
            "Entry BB Position": open_t.get("bb_position"),
            "Entry Confidence": open_t.get("confidence"),
            "Entry Reason": open_t.get("signal_reason"),
            "Entry ATR": open_t.get("atr"),
            "Entry Spread": open_t.get("spread")
        }

        prompt = f"""
You are an expert algorithmic forex trading quantitative analyst.
Please review this completed trade and provide a structured, concise post-trade analysis.

Trade Context Snapshot:
{json.dumps(trade_context, indent=2)}

Format your output exactly in these sections:
1. **Trade Outcome Summary**: Win or Loss details, duration, efficiency.
2. **Primary Driver**: Explain the root cause of the outcome based on indicators, timing, or stale timeouts.
3. **Adjustment Action**: Provide 1-2 highly specific recommendations for optimizing parameter values (e.g. SL/TP width, RSI thresholds, session parameters) based on this result.
"""

        api_key = GEMINI_API_KEY or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            return self._generate_fallback_report(trade_context, "GOOGLE_API_KEY is missing")

        try:
            genai.configure(api_key=api_key)
            model_name = GEMINI_MODEL or "gemini-2.0-flash"
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            print(f"❌ Gemini post-trade analysis request failed: {e}")
            return self._generate_fallback_report(trade_context, str(e))

    def _generate_fallback_report(self, trade_context: dict, error_msg: str) -> str:
        """Rule-based post-trade analysis when Gemini is unavailable."""
        pnl_val = 0.0
        try:
            pnl_val = float(trade_context["PnL"].replace("$", "").replace("+", ""))
        except Exception:
            pass
        is_win = pnl_val > 0
        
        duration_hrs = 0.0
        try:
            duration_hrs = float(trade_context["Duration (Hours)"].replace("h", ""))
        except Exception:
            pass

        # Identify primary drivers and adjustments
        if duration_hrs >= 11.5:
            driver = "Stale Trade Timeout (Positions held over 12 hours decay in efficiency)."
            action = "Ensure stale trade timeout parameter is strictly capped at 12 hours."
        elif is_win:
            driver = f"Mean Reversion Target Achieved (RSI at entry: {trade_context.get('Entry RSI')})."
            action = "No adjustment needed. Trade exited with profit target reached."
        else:
            driver = f"Stop Loss Triggered (High ATR: {trade_context.get('Entry ATR')})."
            action = "Widen stop loss limits using ATR multipliers or suspend trading during high volatility."

        report = f"""### 📊 Post-Trade Analysis (Rule-Based Fallback)
* **Symbol:** {trade_context['Symbol']} ({trade_context['Direction']})
* **PnL:** {trade_context['PnL']}
* **Duration:** {trade_context['Duration (Hours)']}

1. **Trade Outcome Summary**: {"Win" if is_win else "Loss"} completed in {trade_context['Duration (Hours)']}.
2. **Primary Driver**: {driver}
3. **Adjustment Action**: {action}

*(Note: Gemini AI fell back to rule-based parser due to API Key status: {error_msg[:100]})*
"""
        return report

if __name__ == "__main__":
    # Test script run
    analyzer = PostTradeAnalyzer()
    print("Running test scan for new closed trades...")
    reports = analyzer.analyze_new_trades(days=300)
    print(f"Completed. Generated {len(reports)} reviews.")
