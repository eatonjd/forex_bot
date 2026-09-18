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

try:
    from dotenv import load_dotenv
    if os.path.exists(".env"):
        load_dotenv()
except ImportError:
    pass


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

    def get_trade_reviews(self) -> list:
        """Load trade reviews list from GCS or local file."""
        if self.logger.use_gcs and self.logger.gcs_bucket:
            try:
                blob = self.logger.gcs_bucket.blob("trade_logs/trade_reviews.json")
                if blob.exists():
                    return json.loads(blob.download_as_text())
            except Exception as e:
                print(f"⚠️ GCS load trade reviews error: {e}")
        p = self.logger.log_dir / "trade_reviews.json"
        if p.exists():
            try:
                with open(p, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

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

        # Always query OANDA API directly for closed trades (both live and demo)
        try:
            from oandapyV20 import API
            from oandapyV20.endpoints.trades import TradesList
            
            # Prioritize configured environment mode
            current_mode = os.getenv("BOT_MODE", "live").lower()
            if current_mode == "live":
                account_configs = [
                    ("OANDA_API_KEY_LIVE", "OANDA_ACCOUNT_ID_LIVE", "live", "LIVE"),
                    ("OANDA_API_KEY", "OANDA_ACCOUNT_ID", "practice", "DEMO"),
                    ("OANDA_API_KEY_DEMO", "OANDA_ACCOUNT_ID_DEMO", "practice", "DEMO"),
                ]
            else:
                account_configs = [
                    ("OANDA_API_KEY", "OANDA_ACCOUNT_ID", "practice", "DEMO"),
                    ("OANDA_API_KEY_DEMO", "OANDA_ACCOUNT_ID_DEMO", "practice", "DEMO"),
                    ("OANDA_API_KEY_LIVE", "OANDA_ACCOUNT_ID_LIVE", "live", "LIVE"),
                ]

            for env_key, acct_key, env_name, acct_type in account_configs:
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
                        dir_str = "LONG" if units > 0 else "SHORT"

                        # Match against logged trades to hydrate rich telemetry context
                        matched_log = None
                        for l_t in reversed(trades):
                            if l_t.get("action") == "OPEN" and l_t.get("symbol") == t.get("instrument"):
                                if l_t.get("direction") == dir_str:
                                    matched_log = l_t
                                    break

                        open_dict = {
                            "symbol": t.get("instrument"),
                            "direction": dir_str,
                            "units": abs(units),
                            "price": price,
                            "timestamp": ot,
                            "account_id": acct_id,
                            "account_type": acct_type,
                            "signal_reason": matched_log.get("signal_reason", "MEAN_REVERSION") if matched_log else "MEAN_REVERSION",
                            "rsi": matched_log.get("rsi") if matched_log else None,
                            "bb_position": matched_log.get("bb_position") if matched_log else None,
                            "confidence": matched_log.get("confidence") if matched_log else None,
                            "atr": matched_log.get("atr") if matched_log else None,
                            "spread": matched_log.get("spread") if matched_log else None,
                        }

                        closed_trades.append({
                            "open": open_dict,
                            "close": {
                                "symbol": t.get("instrument"),
                                "direction": dir_str,
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
        seen_keys = set()
        for ct in closed_trades:
            open_t = ct["open"]
            close_t = ct["close"]
            
            # Generate a unique key for the trade
            trade_key = f"{close_t.get('symbol')}_{open_t.get('timestamp')}_{close_t.get('timestamp')}"
            
            # Skip if already reviewed or duplicate in batch
            if trade_key in seen_keys or trade_key in self.reviewed_keys:
                continue
            seen_keys.add(trade_key)
                
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

        # Extract and persist reward history
        rewards_path = self.logger.log_dir / "reward_history.json"
        all_rewards = [
            {
                "trade_key": r.get("trade_key"),
                "symbol": r.get("symbol"),
                "direction": r.get("direction"),
                "pnl": r.get("pnl"),
                "reward_score": r.get("reward_score", 0.0),
                "efficiency_score": r.get("efficiency_score", 0.0),
                "timestamp": r.get("timestamp"),
            }
            for r in all_reviews
        ]
        rew_content = json.dumps(all_rewards, indent=2)
        with open(rewards_path, "w") as f:
            f.write(rew_content)

        if self.logger.use_gcs and self.logger.gcs_bucket:
            try:
                blob = self.logger.gcs_bucket.blob("trade_logs/trade_reviews.json")
                blob.upload_from_string(content, content_type="application/json")
                rew_blob = self.logger.gcs_bucket.blob("trade_logs/reward_history.json")
                rew_blob.upload_from_string(rew_content, content_type="application/json")
            except Exception as e:
                print(f"⚠️ GCS save trade reviews/rewards error: {e}")

        return new_reviews

    def _hydrate_missing_telemetry(self, open_t: dict) -> dict:
        """Hydrate missing indicators (RSI, ATR, BB Position, Spread) using OANDA candle history or log matching."""
        if open_t.get("rsi") is not None and open_t.get("atr") is not None and open_t.get("bb_position") is not None:
            return open_t

        symbol = open_t.get("symbol")
        if not symbol:
            return open_t

        # 1. Attempt fallback to OANDA API historical M15 candles if missing
        api_k = os.getenv("OANDA_API_KEY_LIVE") or os.getenv("OANDA_API_KEY") or os.getenv("OANDA_API_KEY_DEMO")
        env_name = "live" if os.getenv("OANDA_API_KEY_LIVE") else "practice"
        if api_k:
            try:
                from oandapyV20 import API
                from oandapyV20.endpoints.instruments import InstrumentsCandles
                import numpy as np
                oanda_api = API(access_token=api_k, environment=env_name)
                params = {"granularity": "M15", "count": 40}
                ts = open_t.get("timestamp")
                if ts:
                    params["to"] = ts
                r = InstrumentsCandles(instrument=symbol, params=params)
                oanda_api.request(r)
                candles = r.response.get("candles", [])
                if len(candles) >= 15:
                    closes = [float(c["mid"]["c"]) for c in candles]
                    highs = [float(c["mid"]["h"]) for c in candles]
                    lows = [float(c["mid"]["l"]) for c in candles]
                    
                    # RSI 14
                    deltas = np.diff(closes)
                    seed = deltas[:14]
                    up = seed[seed >= 0].sum() / 14.0
                    down = -seed[seed < 0].sum() / 14.0
                    rs = up / down if down != 0 else 0.0
                    rsi = 100.0 - (100.0 / (1.0 + rs))
                    for i in range(14, len(deltas)):
                        delta = deltas[i]
                        upval = delta if delta > 0 else 0.0
                        downval = -delta if delta < 0 else 0.0
                        up = (up * 13.0 + upval) / 14.0
                        down = (down * 13.0 + downval) / 14.0
                        rs = up / down if down != 0 else 0.0
                        rsi = 100.0 - (100.0 / (1.0 + rs)) if down != 0 else 100.0
                    
                    # ATR 14
                    tr_list = []
                    for i in range(1, len(closes)):
                        tr_list.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))
                    atr = np.mean(tr_list[-14:]) if tr_list else 0.0010

                    # Bollinger Bands 20
                    sub_closes = closes[-20:]
                    sma = float(np.mean(sub_closes))
                    std = float(np.std(sub_closes))
                    upper = sma + 2.0 * std
                    lower = sma - 2.0 * std
                    last_c = closes[-1]
                    bb_pos = (last_c - lower) / (upper - lower) if (upper - lower) > 0 else 0.5

                    if open_t.get("rsi") is None:
                        open_t["rsi"] = round(float(rsi), 2)
                    if open_t.get("atr") is None:
                        open_t["atr"] = round(float(atr), 5)
                    if open_t.get("bb_position") is None:
                        open_t["bb_position"] = round(float(bb_pos), 3)
                    if open_t.get("confidence") is None:
                        open_t["confidence"] = 70
                    if open_t.get("spread") is None:
                        open_t["spread"] = 1.4 if "AUD" in symbol else 1.2
            except Exception as e:
                print(f"⚠️ Could not backfill telemetry via OANDA candles: {e}")

        # 2. Final sensible defaults if API candle fetch unavailable
        if open_t.get("rsi") is None:
            open_t["rsi"] = 48.5 if open_t.get("direction") == "LONG" else 52.5
        if open_t.get("atr") is None:
            open_t["atr"] = 0.00120
        if open_t.get("bb_position") is None:
            open_t["bb_position"] = 0.25 if open_t.get("direction") == "LONG" else 0.75
        if open_t.get("confidence") is None:
            open_t["confidence"] = 65
        if open_t.get("spread") is None:
            open_t["spread"] = 1.4 if "AUD" in symbol else 1.2

        return open_t

    def _generate_gemini_report(self, open_t: dict, close_t: dict, reward_metrics: dict = None, duration_hrs: float = None) -> str:
        """Use Gemini to construct a structured post-trade analysis report."""
        open_t = self._hydrate_missing_telemetry(open_t)
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

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or GEMINI_API_KEY
        if not api_key:
            return self._generate_fallback_report(trade_context, "GOOGLE_API_KEY is missing")

        model_name = os.getenv("GEMINI_MODEL") or GEMINI_MODEL or "gemini-3.8-flash"

        try:
            from utils.gemini_health import check_gemini_health
            h = check_gemini_health(model_name=model_name, bot_name="Forex Bot")
            if not h.get("healthy"):
                return self._generate_fallback_report(trade_context, f"{h.get('status')}: {h.get('error')}")

            genai.configure(api_key=api_key)
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
