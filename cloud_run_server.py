"""
Health Check Server for Cloud Run

Cloud Run requires an HTTP server for health checks.
This runs alongside the trading bot.
"""

from flask import Flask, jsonify, render_template_string
import threading
import time
import os

app = Flask(__name__)

# Bot status tracking
bot_status = {
    "running": True,
    "last_check": time.time(),
    "last_heartbeat": None,
    "iteration": 0,
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
    },
}


@app.route("/")
def health():
    """Health check endpoint"""
    resp = {
        "status": "healthy",
        "bot_running": bot_status["running"],
        "uptime": time.time() - bot_status["last_check"],
    }
    if "bot_data" in bot_status:
        resp["bot_data"] = bot_status["bot_data"]
    return jsonify(resp)


@app.route("/health")
def health_check():
    """Comprehensive health check endpoint"""
    from version import __version__, __commit__

    init = bot_status["initialization"]

    # Check for heartbeat timeout (e.g., 20 minutes)
    heartbeat_alive = True
    if bot_status["last_heartbeat"]:
        time_since_last = time.time() - bot_status["last_heartbeat"]
        if time_since_last > 1200:  # 20 minutes
            heartbeat_alive = False

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
    elif not heartbeat_alive:
        status = "stalled"
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
            "iteration": bot_status["iteration"],
            "last_heartbeat": bot_status["last_heartbeat"],
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

    if "bot_data" in bot_status:
        response["bot_data"] = bot_status["bot_data"]

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


def _generate_live_trades_html(live_trades):
    """Helper to generate HTML for live trades table"""
    if not live_trades:
        return """
            <div class="section">
                <div class="section-title">🔴 Live Account Status</div>
                <p style="text-align:center; color:#888; padding: 20px;">No live trades yet</p>
            </div>
        """

    live_wins = len([t for t in live_trades if float(t.get("realizedPL", 0)) > 0])
    live_losses = (
        len([t for t in live_trades if t.get("state") == "CLOSED"]) - live_wins
    )

    rows_html = ""
    for trade in live_trades:
        open_time = trade.get("openTime", "")[:10]
        units = int(float(trade.get("initialUnits", trade.get("currentUnits", 0))))
        direction = "LONG" if units > 0 else "SHORT"
        units = abs(units)
        entry = float(trade.get("price", 0))
        state = trade.get("state", "")

        if state == "CLOSED":
            pnl = float(trade.get("realizedPL", 0))
            pnl_class = "positive" if pnl >= 0 else "negative"
            badge = "badge-win" if pnl >= 0 else "badge-loss"
            row_class = "winner" if pnl >= 0 else "loser"
        else:
            pnl = float(trade.get("unrealizedPL", 0))
            pnl_class = "positive" if pnl >= 0 else "negative"
            badge = "badge-open"
            row_class = "open"

        rows_html += f'''
            <tr class="live-trade-row {row_class}">
                <td>{open_time}</td>
                <td>{direction}</td>
                <td>{units:,}</td>
                <td>{entry:.3f}</td>
                <td class="{pnl_class}">${pnl:+.2f}</td>
                <td><span class="badge {badge}">{state}</span></td>
            </tr>
        '''

    return f"""
            <div class="section">
                <div class="section-header">
                    <div class="section-title">🔴 Live Account Activity</div>
                    <select id="liveTradeFilter" onchange="filterLiveTrades()" class="filter-select">
                        <option value="all">All ({len(live_trades)})</option>
                        <option value="winners">Winners ({live_wins})</option>
                        <option value="losers">Losers ({live_losses})</option>
                        <option value="open">Open</option>
                    </select>
                </div>
                <div class="trades-scroll">
                    <table>
                        <thead>
                            <tr><th>Date</th><th>Dir</th><th>Units</th><th>Entry</th><th>P/L</th><th>Status</th></tr>
                        </thead>
                        <tbody>
                            {rows_html}
                        </tbody>
                    </table>
                </div>
            </div>
            
            <script>
            function filterLiveTrades() {{
                const filter = document.getElementById('liveTradeFilter').value;
                const rows = document.querySelectorAll('.live-trade-row');
                rows.forEach(row => {{
                    if (filter === 'all') {{
                        row.style.display = '';
                    }} else if (filter === 'winners' && row.classList.contains('winner')) {{
                        row.style.display = '';
                    }} else if (filter === 'losers' && row.classList.contains('loser')) {{
                        row.style.display = '';
                    }} else if (filter === 'open' && row.classList.contains('open')) {{
                        row.style.display = '';
                    }} else {{
                        row.style.display = 'none';
                    }}
                }});
            }}
            </script>
    """


@app.route("/dashboard")
def dashboard():
    """Redirect to journey page (now the combined dashboard)"""
    from flask import redirect

    return redirect("/journey")


@app.route("/dashboard_old")
def dashboard_old():
    """Public trading dashboard - shareable web page"""
    from oandapyV20 import API
    from oandapyV20.endpoints.accounts import AccountSummary
    from oandapyV20.endpoints.trades import TradesList
    from datetime import datetime

    # Fetch demo account data
    demo_data = {"balance": 0, "nav": 0, "unrealized_pl": 0, "trades": []}
    live_data = {"balance": 0, "nav": 0, "unrealized_pl": 0, "trades": []}

    try:
        # Demo account
        demo_api = API(access_token=os.getenv("OANDA_API_KEY"), environment="practice")
        demo_r = AccountSummary(accountID=os.getenv("OANDA_ACCOUNT_ID"))
        demo_api.request(demo_r)
        demo_acc = demo_r.response["account"]
        demo_data["balance"] = float(demo_acc["balance"])
        demo_data["nav"] = float(demo_acc["NAV"])
        demo_data["unrealized_pl"] = float(demo_acc["unrealizedPL"])

        # Demo trades
        trades_r = TradesList(
            accountID=os.getenv("OANDA_ACCOUNT_ID"),
            params={"instrument": "USD_JPY", "state": "ALL", "count": 500},
        )
        demo_api.request(trades_r)
        demo_data["trades"] = trades_r.response.get("trades", [])
    except Exception as e:
        demo_data["error"] = str(e)

    try:
        # Live account
        live_key = os.getenv("OANDA_API_KEY_LIVE")
        live_id = os.getenv("OANDA_ACCOUNT_ID_LIVE")
        if live_key and live_id:
            live_api = API(access_token=live_key, environment="live")
            live_r = AccountSummary(accountID=live_id)
            live_api.request(live_r)
            live_acc = live_r.response["account"]
            live_data["balance"] = float(live_acc["balance"])
            live_data["unrealized_pl"] = float(live_acc["unrealizedPL"])

            # Live trades
            trades_r = TradesList(
                accountID=live_id,
                params={"instrument": "USD_JPY", "state": "ALL", "count": 20},
            )
            live_api.request(trades_r)
            live_data["trades"] = trades_r.response.get("trades", [])
    except Exception as e:
        live_data["error"] = str(e)

    # Load trades from logger for summary stats
    try:
        from utils.trade_logger import TradeLogger

        logger = TradeLogger()
        all_trades = logger.get_all_trades()
        closed_trades = [t for t in all_trades if t.get("action") == "CLOSE"]
        wins = len([t for t in closed_trades if (t.get("pnl") or 0) > 0])
        win_rate = (wins / len(closed_trades) * 100) if closed_trades else 0
    except:
        closed_trades = []
        wins = 0
        win_rate = 0

    losses = len(closed_trades) - wins
    start_balance = 5000
    # Total P/L from actual balance change (most accurate)
    total_pl = demo_data["balance"] - start_balance
    pct_return = (total_pl / start_balance) * 100

    # Phase 4 Metrics (The 'Reset' clock)
    phase4_start = "2026-01-24"  # Date of Regime Filter deployment
    p4_trades = [
        t
        for t in demo_data.get("trades", [])
        if t.get("state") == "CLOSED" and t.get("openTime", "")[:10] >= phase4_start
    ]
    p4_count = len(p4_trades)
    p4_wins = len([t for t in p4_trades if float(t.get("realizedPL", 0)) > 0])
    p4_wr = (p4_wins / p4_count * 100) if p4_count else 0
    # Calculate Phase 4 drawdown
    p4_peak = demo_data["balance"] - sum(
        float(t.get("realizedPL", 0)) for t in p4_trades
    )  # Start of phase 4 balance
    p4_bal = p4_peak
    p4_max_dd = 0
    p4_peak_running = p4_bal
    for t in sorted(p4_trades, key=lambda x: x.get("closeTime", "")):
        p4_bal += float(t.get("realizedPL", 0))
        if p4_bal > p4_peak_running:
            p4_peak_running = p4_bal
        dd = (p4_peak_running - p4_bal) / p4_peak_running * 100
        if dd > p4_max_dd:
            p4_max_dd = dd

    # Pre-render demo trades rows
    demo_trades_rows = ""
    demo_trades = demo_data.get("trades", [])
    for trade in demo_trades:
        open_time = trade.get("openTime", "")[:10]
        units_val = int(float(trade.get("initialUnits", trade.get("currentUnits", 0))))
        direction = "LONG" if units_val > 0 else "SHORT"
        entry_price = float(trade.get("price", 0))
        state = trade.get("state", "")

        if state == "CLOSED":
            pnl_val = float(trade.get("realizedPL", 0))
            pnl_class = "positive" if pnl_val >= 0 else "negative"
            badge = "badge-win" if pnl_val >= 0 else "badge-loss"
            row_class = "winner" if pnl_val >= 0 else "loser"
        else:
            pnl_val = float(trade.get("unrealizedPL", 0))
            pnl_class = "positive" if pnl_val >= 0 else "negative"
            badge = "badge-open"
            row_class = "open"

        demo_trades_rows += f'''
            <tr class="trade-row {row_class}">
                <td>{open_time}</td>
                <td>{direction}</td>
                <td>{abs(units_val):,}</td>
                <td>{entry_price:.3f}</td>
                <td class="{pnl_class}">${pnl_val:+.2f}</td>
                <td><span class="badge {badge}">{state}</span></td>
            </tr>
        '''

    live_trades_html = _generate_live_trades_html(live_data.get("trades", []))

    # Final HTML template
    html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>USD/JPY Trading Bot Dashboard</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <meta http-equiv="refresh" content="300">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                color: #e4e4e4;
                min-height: 10vh;
                padding: 20px;
            }}
            .container {{ max-width: 900px; margin: 0 auto; }}
            h1 {{
                text-align: center;
                font-size: 2rem;
                margin-bottom: 10px;
                background: linear-gradient(90deg, #00d9ff, #00ff88);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }}
            .subtitle {{ text-align: center; color: #888; margin-bottom: 30px; }}
            .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }}
            .card {{
                background: rgba(255,255,255,0.05);
                border-radius: 15px;
                padding: 20px;
                border: 1px solid rgba(255,255,255,0.1);
            }}
            .card-label {{ color: #888; font-size: 0.85rem; margin-bottom: 5px; }}
            .card-value {{ font-size: 1.8rem; font-weight: 700; }}
            .positive {{ color: #00ff88; }}
            .negative {{ color: #ff4757; }}
            .section {{ background: rgba(255,255,255,0.05); border-radius: 15px; padding: 20px; margin-bottom: 20px; border: 1px solid rgba(255,255,255,0.1); }}
            .section-title {{ font-size: 1.2rem; margin-bottom: 15px; color: #00d9ff; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1); }}
            th {{ color: #888; font-weight: 500; }}
            .badge {{ padding: 3px 8px; border-radius: 5px; font-size: 0.8rem; }}
            .badge-win {{ background: rgba(0,255,136,0.2); color: #00ff88; }}
            .badge-loss {{ background: rgba(255,71,87,0.2); color: #ff4757; }}
            .badge-open {{ background: rgba(0,217,255,0.2); color: #00d9ff; }}
            .live-indicator {{ display: inline-block; width: 8px; height: 8px; background: #00ff88; border-radius: 50%; margin-right: 5px; animation: pulse 2s infinite; }}
            @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.5; }} }}
            .footer {{ text-align: center; color: #666; margin-top: 30px; font-size: 0.85rem; }}
            .dual-account {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
            @media (max-width: 600px) {{ .dual-account {{ grid-template-columns: 1fr; }} }}
            .section-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }}
            .filter-select {{ background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); color: #e4e4e4; padding: 8px 12px; border-radius: 8px; font-size: 0.9rem; cursor: pointer; }}
            .filter-select:focus {{ outline: none; border-color: #00d9ff; }}
            .trades-scroll {{ max-height: 400px; overflow-y: auto; }}
            .trades-scroll::-webkit-scrollbar {{ width: 8px; }}
            .trades-scroll::-webkit-scrollbar-track {{ background: rgba(255,255,255,0.05); border-radius: 4px; }}
            .trades-scroll::-webkit-scrollbar-thumb {{ background: rgba(0,217,255,0.3); border-radius: 4px; }}
            .trades-scroll::-webkit-scrollbar-thumb:hover {{ background: rgba(0,217,255,0.5); }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📈 USD/JPY Trading Bot</h1>
            <p class="subtitle"><span class="live-indicator"></span>Live Dashboard • Auto-refreshes every 5 min</p>
            
            <div class="cards">
                <div class="card">
                    <div class="card-label">Demo Balance</div>
                    <div class="card-value">${demo_data["balance"]:,.2f}</div>
                </div>
                <div class="card">
                    <div class="card-label">Total P/L</div>
                    <div class="card-value {"positive" if total_pl >= 0 else "negative"}">${total_pl:+,.2f}</div>
                </div>
                <div class="card">
                    <div class="card-label">Return</div>
                    <div class="card-value {"positive" if pct_return >= 0 else "negative"}">{pct_return:+.1f}%</div>
                </div>
                <div class="card">
                    <div class="card-label">Win Rate</div>
                    <div class="card-value">{win_rate:.1f}%</div>
                </div>
            </div>
            
            <div class="dual-account">
                <div class="section">
                    <div class="section-title">📊 Demo Status</div>
                    <table>
                        <tr><td>NAV</td><td>${demo_data["nav"]:,.2f}</td></tr>
                        <tr><td>Unrealized P/L</td><td class="{"positive" if demo_data["unrealized_pl"] >= 0 else "negative"}">${demo_data["unrealized_pl"]:+,.2f}</td></tr>
                    </table>
                </div>
                <div class="section">
                    <div class="section-title">💵 Live Status</div>
                    <table>
                        <tr><td>Balance</td><td>${live_data["balance"]:,.2f}</td></tr>
                        <tr><td>Unrealized P/L</td><td class="{"positive" if live_data["unrealized_pl"] >= 0 else "negative"}">${live_data["unrealized_pl"]:+,.2f}</td></tr>
                    </table>
                </div>
            </div>

            <div class="section">
                <div class="section-header">
                    <div class="section-title">📋 All Demo Trades</div>
                    <select id="tradeFilter" onchange="filterTrades()" class="filter-select">
                        <option value="all">All Trades ({len(demo_trades)})</option>
                        <option value="winners">Winners ({wins})</option>
                        <option value="losers">Losers ({losses})</option>
                        <option value="open">Open</option>
                    </select>
                </div>
                <div class="trades-scroll">
                    <table id="tradesTable">
                        <thead>
                            <tr><th>Date</th><th>Direction</th><th>Units</th><th>Entry</th><th>P/L</th><th>Status</th></tr>
                        </thead>
                        <tbody>
                            {demo_trades_rows}
                        </tbody>
                    </table>
                </div>
            </div>

            {live_trades_html}

            <div class="section">
                <div class="section-title">🎯 Go-Live Criteria (Phase 4 Reset)</div>
                <div style="font-size:0.8rem;color:#888;margin-bottom:10px;">Tracking starts from Jan 24 (Regime Filter deployment)</div>
                <table>
                    <thead>
                        <tr><th>Metric</th><th>Progress</th><th>Goal</th><th>Status</th></tr>
                    </thead>
                    <tr><td>Total Trades</td><td>{p4_count}/30</td><td>30</td><td>{"✅" if p4_count >= 30 else "🟡"}</td></tr>
                    <tr><td>Win Rate</td><td>{p4_wr:.1f}%</td><td>>55%</td><td>{"✅" if p4_wr >= 55 else "🟡" if p4_wr >= 45 else "❌"}</td></tr>
                    <tr><td>Max Drawdown</td><td>{p4_max_dd:.1f}%</td><td><10%</td><td>{"✅" if p4_max_dd < 10 else "❌"}</td></tr>
                    <tr><td>Profitable Weeks</td><td>1/3</td><td>3</td><td>🟡</td></tr>
                    <tr><td>NFP Survived</td><td>Jan 9</td><td>-</td><td>✅</td></tr>
                </table>
            </div>

            <script>
            function filterTrades() {{
                const filter = document.getElementById('tradeFilter').value;
                const rows = document.querySelectorAll('.trade-row');
                rows.forEach(row => {{
                    if (filter === 'all') {{
                        row.style.display = '';
                    }} else if (filter === 'winners' && row.classList.contains('winner')) {{
                        row.style.display = '';
                    }} else if (filter === 'losers' && row.classList.contains('loser')) {{
                        row.style.display = '';
                    }} else if (filter === 'open' && row.classList.contains('open')) {{
                        row.style.display = '';
                    }} else {{
                        row.style.display = 'none';
                    }}
                }});
            }}
            </script>

            <div class="footer">
                <p>Updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} UTC</p>
                <p>Strategy: Mean Reversion (Bollinger Bands + RSI) • Timeframe: M15</p>
            </div>
        </div>
    </body>
    </html>
    '''

    return html


@app.route("/journey")
def journey():
    """Enhanced public trading journey page with phase tracking and trade details"""
    from oandapyV20 import API
    from oandapyV20.endpoints.trades import TradesList
    from journey_page import generate_journey_html

    # Fetch trade history from OANDA
    trades = []
    try:
        api = API(access_token=os.getenv("OANDA_API_KEY"), environment="practice")
        r = TradesList(
            accountID=os.getenv("OANDA_ACCOUNT_ID"),
            params={"instrument": "USD_JPY", "state": "ALL", "count": 500},
        )
        api.request(r)
        trades = [t for t in r.response.get("trades", []) if t.get("state") == "CLOSED"]
    except Exception as e:
        print(f"Journey error: {e}")

    # Generate enhanced HTML from journey_page module
    html = generate_journey_html(trades, start_balance=5000)
    return html


@app.route("/command-center")
def command_center():
    """Combined dashboard showing all three bot accounts"""
    from command_center import generate_command_center_html

    try:
        html = generate_command_center_html()
        return html
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"<h1>Command Center Error</h1><pre>{e}</pre>", 500



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
        bot_type = os.getenv("BOT_TYPE", "mean_reversion").lower()
        live_key = os.getenv("OANDA_API_KEY_LIVE")
        live_account = os.getenv("OANDA_ACCOUNT_ID_LIVE")

        if bot_type == "regime":
            print("📦 Importing USD/JPY Regime Bot...", flush=True)
            from usdjpy_regime_bot import USDJPYRegimeBot

            print("🏗️  Instantiating USD/JPY Regime Bot...", flush=True)
            bot = USDJPYRegimeBot(mode=os.getenv("BOT_MODE", "paper"))

            bot_status["initialization"]["oanda_connected"] = True
            bot_status["initialization"]["model_loaded"] = True
            bot_status["initialization"]["position_manager_ready"] = True
            bot_status["initialization"]["decision_reasoning_ready"] = True
            bot_status["initialization"]["trading_loop_started"] = True
            bot_status["initialization"]["completed"] = True

            print("✅ Regime bot initialized, starting trading loop...", flush=True)

            try:
                while True:
                    # Let the bot itself handle market open/close checks to keep logic unified
                    bot.run_once()
                    bot_status["iteration"] += 1
                    bot_status["last_heartbeat"] = time.time()
                    if hasattr(bot, 'get_health_data'):
                        bot_status["bot_data"] = bot.get_health_data()
                    time.sleep(15 * 60)  # 15 minutes
            except KeyboardInterrupt:
                print("\n\n🛑 Stopping Regime Bot...", flush=True)
            finally:
                bot_status["running"] = False

        elif live_key and live_account and bot_type == "parallel":
            # Use Parallel Trading Bot for slippage testing
            print("📦 Importing Parallel Trading Bot (Demo + Live)...", flush=True)
            from parallel_trading_bot import ParallelTradingBot

            print("🏗️  Instantiating Parallel Trading Bot...", flush=True)
            bot = ParallelTradingBot()

            # Mark initialization stages
            bot_status["initialization"]["oanda_connected"] = True
            bot_status["initialization"]["model_loaded"] = True
            bot_status["initialization"]["position_manager_ready"] = True
            bot_status["initialization"]["decision_reasoning_ready"] = True
            bot_status["initialization"]["trading_loop_started"] = True
            bot_status["initialization"]["completed"] = True

            print("✅ Parallel bot initialized, starting trading loop...", flush=True)

            try:
                # Run with 15 minute intervals
                while True:
                    bot.run_once()
                    bot_status["iteration"] += 1
                    bot_status["last_heartbeat"] = time.time()
                    time.sleep(15 * 60)  # 15 minutes for M15 timeframe
            except KeyboardInterrupt:
                print("\n\n🛑 Stopping Parallel Trading bot...", flush=True)
                bot.print_slippage_report()
            finally:
                bot_status["running"] = False
        else:
            # Fallback to demo-only mode
            print("📦 Importing USD/JPY Mean Reversion Bot (Demo only)...", flush=True)
            from usdjpy_mean_reversion import USDJPYMeanReversionBot

            # If live credentials exist but parallel not explicitly set, run live if mode demands,
            # otherwise just run whatever BOT_MODE specifies (usually paper by default).
            if live_key and live_account and os.getenv("BOT_MODE", "paper") != "paper":
                 # Fallback code path to avoid crashing
                 pass

            print("🏗️  Instantiating USD/JPY Mean Reversion Bot...", flush=True)
            bot = USDJPYMeanReversionBot(mode=os.getenv("BOT_MODE", "paper"))

            # Mark initialization stages
            bot_status["initialization"]["oanda_connected"] = True
            bot_status["initialization"]["model_loaded"] = True
            bot_status["initialization"]["position_manager_ready"] = True
            bot_status["initialization"]["decision_reasoning_ready"] = True
            bot_status["initialization"]["trading_loop_started"] = True
            bot_status["initialization"]["completed"] = True

            print("✅ Bot initialized, starting trading loop...", flush=True)

            try:
                # Import market hours check
                from usdjpy_mean_reversion import is_forex_market_open

                # Run with 15 minute intervals
                while True:
                    # Check if forex market is open
                    market_open, reason = is_forex_market_open()
                    if not market_open:
                        print(f"🌙 {reason} - sleeping 30 min", flush=True)
                        time.sleep(30 * 60)  # Sleep 30 min when market closed
                        continue

                    bot.run_once()
                    bot_status["iteration"] += 1
                    bot_status["last_heartbeat"] = time.time()
                    time.sleep(15 * 60)  # 15 minutes for M15 timeframe
            except KeyboardInterrupt:
                print("\n\n🛑 Stopping USD/JPY Mean Reversion bot...", flush=True)
            finally:
                bot_status["running"] = False

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
# Deployed at Mon Jan 12 08:47:59 CST 2026
