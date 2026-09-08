"""
Gemini API Key Pre-Flight Health Checker.
Performs live network probes against Google Generative AI API to verify
key status, detect leaked/revoked keys (HTTP 403), quota limits (HTTP 429),
and alert via Telegram before trading sessions or analytical evaluations begin.
"""

import os
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import google.generativeai as genai

_HEALTH_CACHE: Dict[str, Any] = {
    "last_checked": 0.0,
    "healthy": False,
    "status": "UNCHECKED",
    "details": {},
}
CACHE_TTL_SECONDS = 1800  # 30 minutes cache


def check_gemini_health(
    model_name: Optional[str] = None,
    force: bool = False,
    send_alert: bool = True,
    bot_name: str = "Forex Bot"
) -> Dict[str, Any]:
    """
    Perform a pre-flight probe on the Gemini API key.
    
    Args:
        model_name: Model identifier (defaults to GEMINI_MODEL env or gemini-3.8-flash)
        force: Force live check ignoring cache
        send_alert: Dispatches Telegram alert if check fails
        bot_name: Identifier for alert notifications
        
    Returns:
        Dict with status, healthy bool, latency_ms, error message
    """
    global _HEALTH_CACHE

    now = time.time()
    if not force and _HEALTH_CACHE["status"] != "UNCHECKED":
        if (now - _HEALTH_CACHE["last_checked"]) < CACHE_TTL_SECONDS:
            return _HEALTH_CACHE["details"]

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    target_model = model_name or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    if not api_key:
        result = {
            "healthy": False,
            "status": "MISSING_KEY",
            "model": target_model,
            "error": "No API key configured in GEMINI_API_KEY or GOOGLE_API_KEY",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        _update_cache(result)
        if send_alert:
            _dispatch_alert(bot_name, result)
        return result

    # Perform live probe
    t0 = time.time()
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(target_model)
        # Ultra-lightweight probe
        response = model.generate_content(
            "ping",
            generation_config={"max_output_tokens": 1}
        )
        latency_ms = round((time.time() - t0) * 1000, 1)

        result = {
            "healthy": True,
            "status": "HEALTHY",
            "model": target_model,
            "latency_ms": latency_ms,
            "probe_response": response.text.strip() if response and response.text else "OK",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        print(f"✅ [Gemini Pre-Flight] Key verified active ({target_model}, {latency_ms}ms)", flush=True)
        _update_cache(result)
        return result

    except Exception as e:
        err_str = str(e)
        latency_ms = round((time.time() - t0) * 1000, 1)

        # Classify failure
        if "403" in err_str and "leaked" in err_str.lower():
            status_code = "KEY_LEAKED_REVOKED"
        elif "403" in err_str:
            status_code = "FORBIDDEN_403"
        elif "401" in err_str or "API_KEY_INVALID" in err_str:
            status_code = "INVALID_API_KEY"
        elif "429" in err_str:
            status_code = "QUOTA_EXCEEDED"
        elif "404" in err_str:
            status_code = "MODEL_NOT_FOUND"
        else:
            status_code = "API_ERROR"

        result = {
            "healthy": False,
            "status": status_code,
            "model": target_model,
            "latency_ms": latency_ms,
            "error": err_str,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        print(f"🚨 [Gemini Pre-Flight] Key check failed [{status_code}]: {err_str}", flush=True)
        _update_cache(result)

        if send_alert:
            _dispatch_alert(bot_name, result)

        return result


def _update_cache(result: Dict[str, Any]):
    global _HEALTH_CACHE
    _HEALTH_CACHE["last_checked"] = time.time()
    _HEALTH_CACHE["healthy"] = result.get("healthy", False)
    _HEALTH_CACHE["status"] = result.get("status", "UNKNOWN")
    _HEALTH_CACHE["details"] = result


def _dispatch_alert(bot_name: str, result: Dict[str, Any]):
    """Send immediate high-priority alert via Telegram."""
    msg = (
        f"🚨 *[{bot_name.upper()} PRE-FLIGHT ALERT]*\n\n"
        f"⚠️ *Gemini AI Pre-Flight Verification Failed!*\n"
        f"• **Status**: `{result.get('status')}`\n"
        f"• **Model**: `{result.get('model')}`\n"
        f"• **Error**: {result.get('error')}\n\n"
        f"👉 *Impact*: AI Copilot and Post-Trade Review are falling back to rule-based parser until the key is updated in Secret Manager."
    )
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if token and chat_id:
        try:
            import requests
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
                timeout=5,
            )
        except Exception as e:
            print(f"⚠️ Failed to send Gemini alert Telegram: {e}", flush=True)
