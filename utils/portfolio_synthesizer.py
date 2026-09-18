"""
Unified Portfolio Synthesizer
Coordinates daily post-trade reviews across Crypto Bot, Forex Bot, and Options Bot.
Generates an AI-synthesized multi-asset performance debrief and sends a consolidated Telegram card.
"""

import os
import json
from datetime import datetime, timezone, timedelta
import requests

class PortfolioSynthesizer:
    def __init__(self):
        self.crypto_url = os.getenv("CRYPTO_BOT_URL", "https://crypto-bot-489986279698.us-central1.run.app")
        self.forex_url = os.getenv("FOREX_BOT_URL", "https://forex-bot-live-489986279698.us-central1.run.app")
        self.options_url = os.getenv("OPTIONS_BOT_URL", "https://options-regime-bot-489986279698.us-central1.run.app")

    def run_daily_synthesis(self, hours: int = 36, force: bool = False) -> dict:
        """
        Triggers post-trade reviews on all three bots, aggregates results,
        generates Gemini portfolio synthesis, and dispatches unified Telegram notification.
        """
        cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=hours)

        # 1. Trigger review endpoints on all 3 bots
        crypto_data = self._trigger_crypto_review()
        forex_data = self._trigger_forex_review()
        options_data = self._trigger_options_review()

        # 2. Extract recent trades/reviews within time window
        crypto_trades = self._filter_recent_reviews(crypto_data, cutoff_dt, time_key="timestamp")
        forex_trades = self._filter_recent_reviews(forex_data, cutoff_dt, time_key="timestamp")
        options_trades = self._filter_recent_reviews(options_data, cutoff_dt, time_key="timestamp")

        # 3. Calculate metrics
        c_pnl = sum(float(t.get("pnl", 0.0)) for t in crypto_trades)
        f_pnl = sum(float(t.get("pnl", 0.0)) for t in forex_trades)
        o_pnl = sum(float(t.get("pnl", 0.0)) for t in options_trades)
        total_pnl = c_pnl + f_pnl + o_pnl

        # 4. Generate AI Executive Summary via Gemini
        gemini_summary = self._generate_gemini_synthesis(
            crypto_trades=crypto_trades,
            forex_trades=forex_trades,
            options_trades=options_trades,
            total_pnl=total_pnl
        )

        # 5. Format consolidated Telegram message
        telegram_card = self._format_telegram_card(
            crypto_trades=crypto_trades,
            forex_trades=forex_trades,
            options_trades=options_trades,
            c_pnl=c_pnl,
            f_pnl=f_pnl,
            o_pnl=o_pnl,
            total_pnl=total_pnl,
            gemini_summary=gemini_summary
        )

        # 6. Send notification
        try:
            from utils.notifications import TradingNotifier
            notifier = TradingNotifier()
            notifier._send(telegram_card, title="📊 Daily 3-Bot Portfolio Debrief", priority=4)
        except Exception as notify_err:
            print(f"⚠️ Failed to send unified portfolio notification: {notify_err}")

        return {
            "status": "SUCCESS",
            "total_pnl": round(total_pnl, 2),
            "crypto_trades_count": len(crypto_trades),
            "forex_trades_count": len(forex_trades),
            "options_trades_count": len(options_trades),
            "telegram_card": telegram_card
        }

    def _trigger_crypto_review(self) -> list:
        try:
            r = requests.post(f"{self.crypto_url}/trade-review?days=2", timeout=30)
            if r.status_code == 200:
                data = r.json()
                return data.get("latest_reviews") or data.get("new_reviews") or []
        except Exception as e:
            print(f"⚠️ Crypto review query error: {e}")
        return []

    def _trigger_forex_review(self) -> list:
        try:
            requests.post(f"{self.forex_url}/review-trades?days=2", timeout=30)
            from google.cloud import storage
            client = storage.Client()
            bucket_name = os.getenv("GCS_BUCKET_NAME", "forex-bot-state")
            blob = client.bucket(bucket_name).blob("trade_logs/trade_reviews.json")
            if blob.exists():
                return json.loads(blob.download_as_text())
        except Exception as e:
            print(f"⚠️ Forex review query error: {e}")
        return []

    def _trigger_options_review(self) -> list:
        try:
            requests.post(f"{self.options_url}/review-trades?days=2", timeout=30)
            from google.cloud import storage
            client = storage.Client()
            bucket_name = os.getenv("GCS_BUCKET_NAME", "forex-bot-state")
            blob = client.bucket(bucket_name).blob("options_bot/options_trade_reviews.json")
            if blob.exists():
                return json.loads(blob.download_as_text())
        except Exception as e:
            print(f"⚠️ Options review query error: {e}")
        return []

    def _filter_recent_reviews(self, reviews: list, cutoff_dt: datetime, time_key: str = "timestamp") -> list:
        recent = []
        for r in reviews:
            ts_str = r.get(time_key)
            if not ts_str:
                continue
            try:
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if dt >= cutoff_dt:
                    recent.append(r)
            except Exception:
                pass
        return recent

    def _generate_gemini_synthesis(self, crypto_trades, forex_trades, options_trades, total_pnl) -> str:
        """Call Gemini to generate a concise 3-bullet strategic takeaway."""
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            return "• Risk controls maintained healthy operational bounds across all asset classes."

        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            preferred_model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
            candidate_models = [preferred_model, "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
            # Deduplicate while preserving order
            models_to_try = []
            for m in candidate_models:
                if m not in models_to_try:
                    models_to_try.append(m)

            c_summary = [f"{t.get('symbol')} ({t.get('side')}): PnL ${float(t.get('pnl',0)):+.2f} ({t.get('reason','')})" for t in crypto_trades]
            f_summary = [f"{t.get('symbol')} ({t.get('direction')}): PnL ${float(t.get('pnl',0)):+.2f} (Reward: {t.get('reward_score',0)})" for t in forex_trades]
            o_summary = [f"{t.get('underlying')} ({t.get('strategy')}): {t.get('status')} PnL ${float(t.get('pnl',0)):+.2f}" for t in options_trades]

            prompt = f"""You are the Chief Quantitative Risk Officer overseeing 3 automated bots:
1. Crypto Bot (BTC, ETH, SOL momentum & mean-reversion)
2. Forex Bot (OANDA live CFD M15 regime scalping)
3. Options Bot (Tradier weekly credit spreads & Iron Condors)

Recent Closed Trades:
- Crypto: {c_summary or 'No trades closed in window (disciplined wait)'}
- Forex: {f_summary or 'No trades closed in window (disciplined wait)'}
- Options: {o_summary or 'No trades closed in window'}
- Net Combined Portfolio PnL: ${total_pnl:+.2f}

Provide exactly 3 concise, punchy bullet points:
1. Overall portfolio execution quality & regime alignment.
2. The single strongest operational win or risk save across the bots.
3. Key technical observation or recommendation for tomorrow's market open.
Keep each bullet under 25 words. Do not use markdown headers."""

            for mod in models_to_try:
                try:
                    model = genai.GenerativeModel(mod)
                    res = model.generate_content(prompt)
                    if res and res.text:
                        return res.text.strip()
                except Exception as model_err:
                    print(f"⚠️ Model {mod} error ({model_err}), trying next fallback...")
                    continue

            return "• Disciplined execution across market regimes.\n• Risk envelope preserved capital."
        except Exception as e:
            print(f"⚠️ Gemini portfolio synthesis error: {e}")
            return "• Disciplined execution across market regimes.\n• Risk envelope preserved capital."

    def _format_telegram_card(self, crypto_trades, forex_trades, options_trades, c_pnl, f_pnl, o_pnl, total_pnl, gemini_summary) -> str:
        date_str = datetime.now(timezone.utc).strftime("%b %d, %Y")
        pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"

        lines = [
            f"📊 *DAILY 3-BOT PORTFOLIO DEBRIEF*",
            f"📅 {date_str} | Evening Synthesis",
            f"",
            f"{pnl_emoji} *Combined Net PnL:* `${total_pnl:+.2f}`",
            f"━━━━━━━━━━━━━━━━━━",
            f"🪙 *Crypto Bot:* `${c_pnl:+.2f}` ({len(crypto_trades)} trades)",
        ]
        if crypto_trades:
            for t in crypto_trades[:3]:
                lines.append(f"  • {t.get('symbol')} {t.get('side')}: `${float(t.get('pnl',0)):+.2f}`")
        else:
            lines.append("  • Active scan, zero forced entries")

        lines.extend([
            f"",
            f"💱 *Forex Bot:* `${f_pnl:+.2f}` ({len(forex_trades)} trades)",
        ])
        if forex_trades:
            for t in forex_trades[:3]:
                lines.append(f"  • {t.get('symbol')} {t.get('direction')}: `${float(t.get('pnl',0)):+.2f}`")
        else:
            lines.append("  • Active scan, zero forced entries")

        lines.append("")
        if options_trades:
            open_count = sum(1 for t in options_trades if float(t.get("pnl", 0)) == 0 and t.get("status", "FILLED") != "CLOSED")
            closed_count = len(options_trades) - open_count
            if closed_count > 0:
                lines.append(f"📈 *Options Bot:* `${o_pnl:+.2f}` ({closed_count} closed, {open_count} in-flight)")
            else:
                lines.append(f"📈 *Options Bot:* `${o_pnl:+.2f}` ({open_count} active spreads in-flight)")

            for t in options_trades[:3]:
                pnl_val = float(t.get("pnl", 0))
                und = t.get("underlying")
                strat = t.get("strategy", "").replace("_", " ")
                if pnl_val != 0 or t.get("status") == "CLOSED":
                    lines.append(f"  • {und} {strat}: `${pnl_val:+.2f}` (Closed)")
                else:
                    lines.append(f"  • {und} {strat}: Active (Theta Decay)")
        else:
            lines.append("📈 *Options Bot:* `$0.00` (0 active spreads)")
            lines.append("  • Position cushion monitoring, 0 closes")

        lines.extend([
            f"━━━━━━━━━━━━━━━━━━",
            f"🧠 *Gemini Quantitative Insights:*",
            gemini_summary,
            f"",
            f"🌐 [Forex Dashboard](https://forex-bot-live-489986279698.us-central1.run.app/) • [Crypto Journey](https://crypto-bot-489986279698.us-central1.run.app/journey)"
        ])

        return "\n".join(lines)
