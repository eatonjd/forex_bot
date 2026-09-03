"""
Gemini In-Flight Position Copilot for Forex Trading Bot
Provides real-time AI supervision of active, open OANDA positions.
Monitors price excursion, aging trades, momentum exhaustion, and regime shifts to recommend
dynamic stop tightening, breakeven moves, or early profit exits.
"""

import os
import json
import re
import time
from typing import Dict, Any, Optional
import google.generativeai as genai


class ForexInFlightCopilot:
    """Real-time in-flight position copilot powered by Gemini 3.6 Flash for Forex."""

    def __init__(self, cooldown_minutes: int = 30):
        self.cooldown_seconds = cooldown_minutes * 60
        self.last_evaluation_times: Dict[str, float] = {}  # instrument -> epoch timestamp

        # Configure Gemini API
        self.api_key = os.getenv("GOOGLE_API_KEY", "AIzaSyAt50SSEIqvi-hwlRI8PQNjDW1Y-_bBuv4")
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
        try:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(self.model_name)
            self.enabled = True
            print(f"🤖 Forex In-Flight Copilot initialized ({self.model_name})", flush=True)
        except Exception as e:
            print(f"⚠️ Failed to initialize Forex Gemini Copilot: {e}", flush=True)
            self.model = None
            self.enabled = False

    def should_evaluate(
        self,
        instrument: str,
        pos_dir: int,
        upl: float,
        hold_h: float,
        entry_regime: str,
        current_regime: str,
        peak_profit: float = 0.0,
    ) -> bool:
        """
        Event-Driven Filter:
        Determines whether an open forex trade warrants an in-flight Gemini consultation.
        """
        if not self.enabled or self.model is None or pos_dir == 0:
            return False

        # 1. Cooldown Check
        now = time.time()
        last_eval = self.last_evaluation_times.get(instrument, 0.0)
        if (now - last_eval) < self.cooldown_seconds:
            return False

        # 2. Key Event Triggers:
        # Trigger A: Substantial profit milestone (>= $8 profit)
        is_profit_milestone = upl >= 8.0

        # Trigger B: Trade Aging (held for >= 2.5 hours without exit)
        is_aging_trade = hold_h >= 2.5

        # Trigger C: Regime shift (market regime changed from entry regime)
        is_regime_shift = entry_regime and (entry_regime != current_regime) and (entry_regime != "UNKNOWN")

        # Trigger D: Apex giveback alert (peaked > $12, dropped > 25% from peak)
        is_giveback_alert = peak_profit >= 12.0 and (upl <= peak_profit * 0.75)

        if is_profit_milestone or is_aging_trade or is_regime_shift or is_giveback_alert:
            return True

        return False

    def evaluate_position(
        self,
        instrument: str,
        direction: str,
        units: float,
        entry_price: float,
        current_price: float,
        upl: float,
        hold_h: float,
        entry_regime: str,
        current_regime: str,
        peak_profit: float = 0.0,
        indicators: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Query Gemini 3.6 Flash for in-flight position guidance.
        """
        self.last_evaluation_times[instrument] = time.time()
        indicators = indicators or {}

        prompt = f"""You are the real-time algorithmic execution copilot for an active Forex trade on OANDA.
Analyze the following in-flight position and recommend an immediate adjustment action.

Active Position Snapshot:
- Instrument: {instrument}
- Direction: {direction}
- Units: {units:,.0f}
- Entry Price: {entry_price:.5f}
- Current Market Price: {current_price:.5f}
- Floating Unrealized PnL: ${upl:+,.2f} (Peak floating PnL: ${peak_profit:+,.2f})
- Holding Duration: {hold_h:.1f} hours
- Entry Regime: {entry_regime}
- Current Regime: {current_regime}
- Technical Indicators: {json.dumps(indicators)}

Your goal is to protect capital, prevent profitable trades from turning into losses, and manage exposure during regime transitions.

Respond strictly with a JSON object in this exact format:
{{
  "action": "HOLD" | "TIGHTEN_STOP" | "CLOSE_NOW",
  "new_stop_price": <float or null, tighter stop price if action is TIGHTEN_STOP>,
  "confidence": <float between 0.50 and 1.00>,
  "rationale": "<1-2 concise sentences explaining why>"
}}
"""

        try:
            resp = self.model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"},
                request_options={"timeout": 6}
            )
            text = resp.text.strip()
            text = re.sub(r"^```json\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            data = json.loads(text)

            action = data.get("action", "HOLD").upper()
            confidence = float(data.get("confidence", 0.5))
            rationale = data.get("rationale", "Routine hold.")
            new_sl = data.get("new_stop_price")

            print(f"🤖 [{instrument} Copilot] Action: {action} (Confidence: {confidence:.2f}) | {rationale}", flush=True)

            return {
                "action": action,
                "new_stop_price": float(new_sl) if new_sl is not None else None,
                "confidence": confidence,
                "rationale": rationale,
            }

        except Exception as e:
            print(f"⚠️ Gemini in-flight evaluation error for {instrument}: {e}", flush=True)
            return {
                "action": "HOLD",
                "new_stop_price": None,
                "confidence": 0.5,
                "rationale": f"Fallback to deterministic rules: {e}",
            }
