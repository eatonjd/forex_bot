"""
Health Check Server for Cloud Run

Cloud Run requires an HTTP server for health checks.
This runs alongside the trading bot.
"""

from flask import Flask, jsonify
import threading
import time
import os

app = Flask(__name__)

# Bot status tracking
bot_status = {
    "running": True,
    "last_check": time.time(),
    "trades": 0,
    "errors": 0,
    "initialization": {
        "started": False,
        "oanda_connected": False,
        "model_loaded": False,
        "position_manager_ready": False,
        "decision_reasoning_ready": False,
        "trading_loop_started": False,
        "completed": False,
        "error": None,
        "last_iteration": None,
    },
}


@app.route("/")
def health():
    """Health check endpoint"""
    return jsonify(
        {
            "status": "healthy",
            "bot_running": bot_status["running"],
            "uptime": time.time() - bot_status["last_check"],
        }
    )


@app.route("/health")
def health_check():
    """Comprehensive health check endpoint"""
    from version import __version__, __commit__

    init = bot_status["initialization"]

    # Determine overall health status
    if init["error"]:
        status = "unhealthy"
        http_code = 503
    elif not init["started"]:
        status = "starting"
        http_code = 503
    elif not init["completed"]:
        status = "initializing"
        http_code = 503
    elif init["completed"] and bot_status["running"]:
        status = "healthy"
        http_code = 200
    else:
        status = "degraded"
        http_code = 503

    # Calculate uptime if bot is running
    uptime_seconds = None
    if init["completed"]:
        uptime_seconds = int(time.time() - bot_status["last_check"])

    response = {
        "status": status,
        "version": __version__,
        "commit": __commit__,
        "timestamp": time.time(),
        "bot": {
            "initialized": init["completed"],
            "running": bot_status["running"],
            "uptime_seconds": uptime_seconds,
            "last_iteration": init["last_iteration"],
            "total_errors": bot_status["errors"],
        },
        "initialization_stages": {
            "oanda_connected": init["oanda_connected"],
            "model_loaded": init["model_loaded"],
            "position_manager_ready": init["position_manager_ready"],
            "decision_reasoning_ready": init["decision_reasoning_ready"],
            "trading_loop_started": init["trading_loop_started"],
        },
    }

    if init["error"]:
        response["error"] = str(init["error"])

    return jsonify(response), http_code


@app.route("/status")
def status():
    """Detailed status"""
    from utils.oanda_connector import OANDAConnector

    try:
        oanda = OANDAConnector(environment="practice")
        account = oanda.get_account_summary()
        positions = oanda.get_open_positions()

        return jsonify(
            {
                "status": "ok",
                "account": {
                    "balance": account.get("balance", 0),
                    "unrealized_pl": account.get("unrealized_pl", 0),
                    "open_positions": len(positions),
                },
                "bot": bot_status,
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


def run_trading_bot():
    """Run the actual trading bot"""
    from version import __version__, __commit__
    import sys
    from datetime import datetime

    sys.path.insert(0, "/app")
    sys.stdout.flush()
    sys.stderr.flush()

    bot_status["initialization"]["started"] = True

    print("=" * 60, flush=True)
    print(f"🤖 STARTING FOREX TRADING BOT v{__version__}", flush=True)
    print(f"   Commit: {__commit__}", flush=True)
    print("=" * 60, flush=True)

    # DEBUG: Check environment variables in thread context
    print("🔍 DEBUG: Checking environment variables in bot thread...", flush=True)
    import os

    oanda_key = os.getenv("OANDA_API_KEY")
    oanda_account = os.getenv("OANDA_ACCOUNT_ID")
    oanda_env = os.getenv("OANDA_ENVIRONMENT")

    print(
        f"   OANDA_API_KEY: {'SET (len={})'.format(len(oanda_key)) if oanda_key else 'NOT SET'}",
        flush=True,
    )
    print(
        f"   OANDA_ACCOUNT_ID: {oanda_account if oanda_account else 'NOT SET'}",
        flush=True,
    )
    print(f"   OANDA_ENVIRONMENT: {oanda_env if oanda_env else 'NOT SET'}", flush=True)
    print("=" * 60, flush=True)

    try:
        # Import and run bot
        from paper_trading_bot import PaperTradingBot

        # Note: PaperTradingBot will update bot_status during initialization
        # We need to pass bot_status to it or use a shared state mechanism

        bot = PaperTradingBot()

        # Mark as completed (bot's __init__ should have updated intermediate stages)
        bot_status["initialization"]["completed"] = True
        bot_status["initialization"]["trading_loop_started"] = True

        print("✅ Bot initialized, starting trading loop...", flush=True)

        # Override bot's run() to update iteration timestamp
        original_run = bot.run

        def run_with_tracking():
            try:
                original_run()
            except KeyboardInterrupt:
                print("\n\n🛑 Stopping paper trading bot...", flush=True)
            finally:
                bot_status["running"] = False

        # Wrap iteration to track timestamp
        original_check_symbol = bot.check_symbol

        def check_symbol_with_tracking(instrument):
            bot_status["initialization"]["last_iteration"] = datetime.now().isoformat()
            return original_check_symbol(instrument)

        bot.check_symbol = check_symbol_with_tracking

        run_with_tracking()

    except Exception as e:
        print(f"❌ Bot error: {e}", flush=True)
        import traceback

        traceback.print_exc()
        bot_status["running"] = False
        bot_status["errors"] += 1
        bot_status["initialization"]["error"] = str(e)
        bot_status["initialization"]["completed"] = False


if __name__ == "__main__":
    # DEBUG: Check environment variables at startup
    print("=" * 60, flush=True)
    print("🔧 CLOUD RUN SERVER STARTING", flush=True)
    print("=" * 60, flush=True)
    print("🔍 Environment Variables Check:", flush=True)
    oanda_key = os.environ.get("OANDA_API_KEY")
    oanda_account = os.environ.get("OANDA_ACCOUNT_ID")
    oanda_env = os.environ.get("OANDA_ENVIRONMENT")
    print(
        f"   OANDA_API_KEY: {'SET (len={})'.format(len(oanda_key)) if oanda_key else '❌ NOT SET'}",
        flush=True,
    )
    print(
        f"   OANDA_ACCOUNT_ID: {oanda_account if oanda_account else '❌ NOT SET'}",
        flush=True,
    )
    print(
        f"   OANDA_ENVIRONMENT: {oanda_env if oanda_env else '❌ NOT SET'}", flush=True
    )
    print("=" * 60, flush=True)

    # Start trading bot in background thread
    print("🚀 Starting bot thread...", flush=True)
    bot_thread = threading.Thread(target=run_trading_bot, daemon=True)
    bot_thread.start()
    print("✅ Bot thread started", flush=True)

    # Run Flask health check server
    port = int(os.environ.get("PORT", 8080))
    print(f"🌐 Starting Flask server on port {port}...", flush=True)
    app.run(host="0.0.0.0", port=port)
