"""
Dual Environment Parity Checker for Forex Bot
Verifies that trades opened in Demo (Paper) are mirrored in Live (or vice versa).
If a parity mismatch occurs, diagnoses the exact reason and sends an instant Telegram alert.
"""

import os
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from dotenv import load_dotenv

load_dotenv()

from oandapyV20 import API
from oandapyV20.endpoints.positions import PositionDetails, OpenPositions
from oandapyV20.endpoints.pricing import PricingInfo
from oandapyV20.endpoints.accounts import AccountSummary
from oandapyV20.endpoints.transactions import TransactionsSinceID


class EnvironmentParityChecker:
    """
    Audits dual-environment execution between Demo and Live OANDA accounts.
    """

    def __init__(self, current_mode: str = "paper"):
        self.current_mode = current_mode.lower()
        self.is_current_live = (self.current_mode == "live")

        # Demo Credentials
        self.demo_key = os.getenv("OANDA_API_KEY") or os.getenv("OANDA_API_KEY_DEMO")
        self.demo_id = os.getenv("OANDA_ACCOUNT_ID") or os.getenv("OANDA_ACCOUNT_ID_DEMO", "101-001-38009813-001")

        # Live Credentials
        self.live_key = os.getenv("OANDA_API_KEY_LIVE") or os.getenv("OANDA_API_KEY")
        self.live_id = os.getenv("OANDA_ACCOUNT_ID_LIVE", "001-001-20048243-002")

        # Setup counterpart API
        self.counterpart_mode = "paper" if self.is_current_live else "live"
        self.counterpart_id = self.demo_id if self.is_current_live else self.live_id
        self.counterpart_key = self.demo_key if self.is_current_live else self.live_key
        self.counterpart_env = "practice" if self.is_current_live else "live"

        self.counterpart_api = None
        if self.counterpart_key and self.counterpart_id:
            try:
                self.counterpart_api = API(access_token=self.counterpart_key, environment=self.counterpart_env)
            except Exception as e:
                print(f"⚠️ Parity checker failed to init counterpart API: {e}", flush=True)

    def check_and_notify_parity(
        self,
        instrument: str,
        direction: str,
        units: int,
        entry_price: float,
        regime: str,
        max_spread: float = 4.0,
        margin_rate: float = 0.02
    ) -> Dict[str, Any]:
        """
        Check if counterpart environment opened a matching position.
        If missing, diagnoses the root cause and sends a Telegram notification.
        """
        if not self.counterpart_api:
            return {"status": "skipped", "reason": "Counterpart API credentials not configured"}

        # 1. Check if counterpart holds a matching position
        matched, pos_details = self._check_counterpart_position(instrument, direction)
        if matched:
            print(f"✅ Dual Environment Parity Verified: {instrument} {direction} open in both Demo and Live", flush=True)
            return {"status": "matched", "details": pos_details}

        # 2. Parity mismatch detected -> Diagnose reasons
        diagnosis = self._diagnose_missing_order(instrument, units, entry_price, max_spread, margin_rate)

        # 3. Format and send Telegram Alert
        self._send_parity_alert(instrument, direction, units, entry_price, regime, diagnosis)

        return {
            "status": "mismatch",
            "primary_env": self.current_mode.upper(),
            "counterpart_env": self.counterpart_mode.upper(),
            "diagnosis": diagnosis
        }

    def _check_counterpart_position(self, instrument: str, direction: str) -> Tuple[bool, Optional[Dict]]:
        """Check if counterpart account has an open position for instrument and direction."""
        try:
            r = PositionDetails(accountID=self.counterpart_id, instrument=instrument)
            self.counterpart_api.request(r)
            pos = r.response.get("position", {})
            long_units = int(float(pos.get("long", {}).get("units", 0)))
            short_units = int(float(pos.get("short", {}).get("units", 0)))

            if direction == "BUY" and long_units > 0:
                return True, {"units": long_units, "avgPrice": pos.get("long", {}).get("averagePrice")}
            elif direction == "SELL" and short_units < 0:
                return True, {"units": abs(short_units), "avgPrice": pos.get("short", {}).get("averagePrice")}
            return False, None
        except Exception as e:
            # 404 means no position exists for this instrument
            return False, None

    def _diagnose_missing_order(
        self,
        instrument: str,
        units: int,
        entry_price: float,
        max_spread: float,
        margin_rate: float
    ) -> Dict[str, Any]:
        """Diagnose why the counterpart account did not open the position."""
        diag = {
            "reasons": [],
            "counterpart_spread": None,
            "counterpart_balance": None,
            "counterpart_margin_available": None,
            "required_margin": None,
            "recent_rejects": []
        }

        # A. Check real-time counterpart spread
        try:
            r_price = PricingInfo(accountID=self.counterpart_id, params={"instruments": instrument})
            self.counterpart_api.request(r_price)
            prices = r_price.response.get("prices", [])
            if prices:
                bids = [float(b["price"]) for b in prices[0].get("bids", [])]
                asks = [float(a["price"]) for a in prices[0].get("asks", [])]
                if bids and asks:
                    spread_raw = max(asks) - min(bids)
                    pip_size = 0.01 if "JPY" in instrument else 0.0001
                    spread_pips = spread_raw / pip_size
                    diag["counterpart_spread"] = round(spread_pips, 2)
                    if spread_pips > max_spread:
                        diag["reasons"].append(
                            f"Spread Gate: {self.counterpart_mode.upper()} spread was {spread_pips:.1f}p (exceeds max {max_spread:.1f}p limit)"
                        )
        except Exception as e:
            diag["reasons"].append(f"Could not fetch counterpart pricing: {e}")

        # B. Check counterpart balance and margin limits
        try:
            r_acc = AccountSummary(accountID=self.counterpart_id)
            self.counterpart_api.request(r_acc)
            acc = r_acc.response.get("account", {})
            balance = float(acc.get("balance", 0))
            margin_avail = float(acc.get("marginAvailable", 0))
            nav = float(acc.get("NAV", balance))
            diag["counterpart_balance"] = round(balance, 2)
            diag["counterpart_margin_available"] = round(margin_avail, 2)

            required_margin = units * entry_price * margin_rate
            if "JPY" in instrument and "USD" in instrument and not instrument.startswith("USD"):
                required_margin = units * margin_rate  # adjust for base currency
            diag["required_margin"] = round(required_margin, 2)

            if margin_avail < required_margin:
                diag["reasons"].append(
                    f"Margin Shortfall: Required ${required_margin:.2f} margin, but {self.counterpart_mode.upper()} free margin is only ${margin_avail:.2f}"
                )
            elif (required_margin / max(1.0, nav)) > 0.50:
                diag["reasons"].append(
                    f"Risk Cap: Order requires {(required_margin/nav)*100:.1f}% of NAV (50% max margin cap policy)"
                )
        except Exception as e:
            diag["reasons"].append(f"Could not fetch account summary: {e}")

        # C. Check recent OANDA transactions for rejections or cancels
        try:
            r_tx = TransactionsSinceID(accountID=self.counterpart_id, params={"id": "1"})
            self.counterpart_api.request(r_tx)
            txs = r_tx.response.get("transactions", [])
            recent_rejections = []
            for tx in txs[-15:]:
                tx_type = tx.get("type", "")
                if "REJECT" in tx_type or "CANCEL" in tx_type:
                    recent_rejections.append(f"{tx_type}: {tx.get('rejectReason') or tx.get('reason') or 'Rejected'}")
            if recent_rejections:
                diag["recent_rejects"] = recent_rejections
                diag["reasons"].append(f"OANDA Rejection: {', '.join(recent_rejections[-2:])}")
        except Exception:
            pass

        # D. If no hard failure detected, note timing/polling jitter
        if not diag["reasons"]:
            diag["reasons"].append(
                "Polling Cycle Jitter: Counterpart bot runs in an independent loop / candle offset and has not triggered or was in active cooldown"
            )

        return diag

    def _send_parity_alert(
        self,
        instrument: str,
        direction: str,
        units: int,
        entry_price: float,
        regime: str,
        diagnosis: Dict[str, Any]
    ) -> None:
        """Send high-priority Telegram parity alert with diagnosis."""
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            return

        reasons_str = "\n".join([f"  • {r}" for r in diagnosis.get("reasons", [])])
        spread_info = f"{diagnosis.get('counterpart_spread')} pips" if diagnosis.get("counterpart_spread") is not None else "N/A"
        margin_info = (
            f"${diagnosis.get('counterpart_margin_available'):,.2f} (Req: ${diagnosis.get('required_margin'):,.2f})"
            if diagnosis.get("counterpart_margin_available") is not None else "N/A"
        )

        msg = (
            f"⚠️ *[PARITY MISMATCH | DEMO vs LIVE]*\n\n"
            f"🚨 Position opened in *{self.current_mode.upper()}*, but *NOT* in *{self.counterpart_mode.upper()}*!\n\n"
            f"📌 *Order Details:*\n"
            f"  • Instrument: `{instrument}`\n"
            f"  • Action: *{direction}* {units:,} units @ {entry_price}\n"
            f"  • Regime: `{regime}`\n"
            f"  • Origin Account: `{self.demo_id if not self.is_current_live else self.live_id}`\n"
            f"  • Missing On: `{self.counterpart_id}`\n\n"
            f"🔍 *Root Cause Diagnosis:*\n"
            f"{reasons_str}\n\n"
            f"📊 *Counterpart Telemetry ({self.counterpart_mode.upper()}):*\n"
            f"  • Spread: {spread_info}\n"
            f"  • Free Margin: {margin_info}\n"
            f"  • Account NAV: ${diagnosis.get('counterpart_balance', 'N/A')}\n"
        )

        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": msg,
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
            print("📲 Parity mismatch Telegram alert dispatched successfully", flush=True)
        except Exception as e:
            print(f"⚠️ Failed to send Telegram parity alert: {e}", flush=True)
