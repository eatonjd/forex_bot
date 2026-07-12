"""
Combined Trading Command Center
Shows all three bot accounts side-by-side:
  1. forex-trading-bot (Mean Reversion, Paper)
  2. forex-bot-live (Mean Reversion, Live)
  3. forex-bot-vol (Volatility Breakout, Paper)
"""

import os
from datetime import datetime

# Live account only counts trades from actual funded deployment
# (Pre-existing test trades from Jan 2026 are excluded)
LIVE_SINCE_DATE = "2026-04-18"

# Vol bot account (-002) had old v1 bot trades; only show vol bot trades
VOL_SINCE_DATE = "2026-04-18"


def fetch_account_data(api, account_id, instrument="USD_JPY", label="Bot"):
    """Fetch account balance, trades, and open positions."""
    from oandapyV20.endpoints.accounts import AccountDetails
    from oandapyV20.endpoints.trades import TradesList

    data = {
        "label": label,
        "account_id": account_id,
        "balance": 0,
        "unrealized_pl": 0,
        "equity": 0,
        "trades": [],
        "open_trades": [],
        "error": None,
    }

    try:
        r = AccountDetails(accountID=account_id)
        api.request(r)
        a = r.response["account"]
        data["balance"] = float(a["balance"])
        data["unrealized_pl"] = float(a["unrealizedPL"])
        data["equity"] = data["balance"] + data["unrealized_pl"]

        # Closed trades
        params = {"state": "CLOSED", "count": 500, "instrument": instrument}
        rt = TradesList(accountID=account_id, params=params)
        api.request(rt)
        data["trades"] = rt.response.get("trades", [])

        # Open trades
        params_open = {"state": "OPEN", "instrument": instrument}
        ro = TradesList(accountID=account_id, params=params_open)
        api.request(ro)
        data["open_trades"] = ro.response.get("trades", [])

    except Exception as e:
        data["error"] = str(e)

    return data


def calc_stats(trades, since_date=None):
    """Calculate win rate, P/L, streaks from trades."""
    if since_date:
        trades = [t for t in trades if t.get("openTime", "")[:10] >= since_date]

    if not trades:
        return {"count": 0, "wins": 0, "losses": 0, "win_rate": 0,
                "pnl": 0, "avg_win": 0, "avg_loss": 0, "best": 0, "worst": 0}

    pnls = [float(t.get("realizedPL", 0)) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    return {
        "count": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(trades) * 100 if trades else 0,
        "pnl": sum(pnls),
        "avg_win": sum(wins) / len(wins) if wins else 0,
        "avg_loss": sum(losses) / len(losses) if losses else 0,
        "best": max(pnls) if pnls else 0,
        "worst": min(pnls) if pnls else 0,
    }


def build_trade_rows(trades, limit=20):
    """Build HTML rows for recent trades."""
    sorted_trades = sorted(trades, key=lambda t: t.get("closeTime", ""), reverse=True)[:limit]
    rows = ""
    for t in sorted_trades:
        ot = t.get("openTime", "")[:16]
        ct = t.get("closeTime", "")[:16]
        units = int(float(t.get("initialUnits", 0)))
        direction = "LONG" if units > 0 else "SHORT"
        dir_class = "long" if units > 0 else "short"
        pnl = float(t.get("realizedPL", 0))
        pnl_class = "positive" if pnl >= 0 else "negative"
        emoji = "✅" if pnl > 0 else "❌"
        entry = float(t.get("price", 0))
        close_price = float(t.get("averageClosePrice", entry))

        # Holding time
        try:
            from datetime import datetime as dt
            open_dt = dt.fromisoformat(t.get("openTime", "").replace("Z", "+00:00"))
            close_dt = dt.fromisoformat(t.get("closeTime", "").replace("Z", "+00:00"))
            hold_sec = (close_dt - open_dt).total_seconds()
            hold_str = f"{int(hold_sec / 60)}m" if hold_sec < 3600 else f"{hold_sec / 3600:.1f}h"
        except:
            hold_str = "-"

        rows += f'''
        <tr>
            <td>{emoji} {ot[5:]}</td>
            <td class="{dir_class}">{direction}</td>
            <td>{abs(units):,}</td>
            <td>{entry:.3f}</td>
            <td>{close_price:.3f}</td>
            <td class="{pnl_class}">${pnl:+.2f}</td>
            <td>{hold_str}</td>
        </tr>'''
    return rows


def build_open_positions(open_trades):
    """Build HTML for open positions."""
    if not open_trades:
        return '<div class="no-positions">No open positions</div>'

    rows = ""
    for t in open_trades:
        units = int(float(t.get("initialUnits", t.get("currentUnits", 0))))
        direction = "LONG" if units > 0 else "SHORT"
        dir_class = "long" if units > 0 else "short"
        upl = float(t.get("unrealizedPL", 0))
        pnl_class = "positive" if upl >= 0 else "negative"
        entry = float(t.get("price", 0))
        ot = t.get("openTime", "")[:16]

        rows += f'''
        <div class="open-position">
            <span class="open-dot"></span>
            <span class="{dir_class}">{direction}</span>
            <span>{abs(units):,}u @ {entry:.3f}</span>
            <span class="{pnl_class}">${upl:+.2f}</span>
        </div>'''
    return rows


def generate_command_center_html():
    """Generate the full combined dashboard HTML."""
    from oandapyV20 import API
    import requests

    # --- Fetch data from all three accounts ---
    practice_api = API(
        access_token=os.getenv("OANDA_API_KEY"),
        environment="practice"
    )

    # 1. Mean Reversion Paper (-001)
    mr_paper = fetch_account_data(
        practice_api,
        os.getenv("OANDA_ACCOUNT_ID", "101-001-38009813-001"),
        instrument="USD_JPY",
        label="Mean Reversion (Paper)"
    )

    # 3. Mean Reversion Live
    live_data = {"label": "Mean Reversion (LIVE)", "balance": 0, "unrealized_pl": 0,
                 "equity": 0, "trades": [], "open_trades": [], "error": None}
    live_key = os.getenv("OANDA_API_KEY_LIVE")
    live_id = os.getenv("OANDA_ACCOUNT_ID_LIVE")
    if live_key and live_id:
        live_api = API(access_token=live_key, environment="live")
        live_data = fetch_account_data(live_api, live_id, instrument="USD_JPY",
                                       label="Mean Reversion (LIVE)")

    # --- Service health checks ---
    services = {
        "forex-trading-bot": "https://forex-trading-bot-489986279698.us-central1.run.app/",
        "forex-bot-live": "https://forex-bot-live-489986279698.us-central1.run.app/",
    }
    health_status = {}
    for name, url in services.items():
        try:
            r = requests.get(url, timeout=8)
            if r.status_code == 200:
                d = r.json()
                uptime_h = d.get("uptime", 0) / 3600
                bot_data = d.get("bot_data", {})
                regime = bot_data.get("regime", "UNKNOWN")
                regime_reason = bot_data.get("regime_reason", "")
                market_open = bot_data.get("market_open", True)
                
                if not market_open:
                    regime = "Markets Closed 🌙"
                
                health_status[name] = {"status": "healthy", "uptime": f"{uptime_h:.0f}h", "regime": regime, "regime_reason": regime_reason}
            else:
                health_status[name] = {"status": "error", "uptime": "-", "regime": "UNKNOWN", "regime_reason": ""}
        except:
            health_status[name] = {"status": "offline", "uptime": "-", "regime": "UNKNOWN"}

    # --- Calculate stats ---
    mr_stats_all = calc_stats(mr_paper["trades"])
    mr_stats_73 = calc_stats(mr_paper["trades"], since_date="2026-02-13")

    # Live: filter out pre-deployment test trades
    live_trades_filtered = [t for t in live_data["trades"] if t.get("openTime", "")[:10] >= LIVE_SINCE_DATE]
    live_stats_all = calc_stats(live_trades_filtered)

    # --- Total portfolio ---
    total_pnl = mr_stats_all["pnl"] + live_stats_all["pnl"]
    total_equity = mr_paper["equity"] + live_data["equity"]

    # Build trade rows (live and vol use filtered trades)
    mr_trade_rows = build_trade_rows(mr_paper["trades"])
    live_trade_rows = build_trade_rows(live_trades_filtered)

    # Open positions
    mr_open_html = build_open_positions(mr_paper["open_trades"])
    live_open_html = build_open_positions(live_data["open_trades"])

    # Health dots
    def health_dot(name):
        h = health_status.get(name, {})
        s = h.get("status", "offline")
        color = "#00ff88" if s == "healthy" else "#ff4757" if s == "error" else "#888"
        return f'<span class="health-dot" style="background:{color}"></span> {s.title()} ({h.get("uptime", "-")})'

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <title>Trading Command Center</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="refresh" content="300">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Inter', -apple-system, sans-serif;
            background: linear-gradient(135deg, #06060f 0%, #0d1117 40%, #161b22 100%);
            color: #e6edf3;
            min-height: 100vh;
            padding: 24px;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}

        /* Header */
        .header {{ text-align: center; margin-bottom: 36px; }}
        h1 {{
            font-size: 2.2rem; font-weight: 800; letter-spacing: -0.5px;
            background: linear-gradient(135deg, #58a6ff, #3fb950, #f0883e);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            margin-bottom: 8px;
        }}
        .subtitle {{ color: #8b949e; font-size: 0.9rem; }}
        .refresh-note {{ color: #484f58; font-size: 0.75rem; margin-top: 4px; }}

        /* Portfolio Summary */
        .portfolio-bar {{
            display: flex; gap: 16px; margin-bottom: 28px; flex-wrap: wrap;
            justify-content: center;
        }}
        .portfolio-stat {{
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px;
            padding: 16px 28px;
            text-align: center;
            min-width: 160px;
        }}
        .portfolio-stat .label {{ color: #8b949e; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; }}
        .portfolio-stat .value {{ font-size: 1.6rem; font-weight: 700; margin-top: 4px; }}

        /* Bot Cards Grid */
        .bots-grid {{
            display: grid;
            grid-template-columns: repeat(2, minmax(320px, 450px));
            justify-content: center;
            gap: 24px;
            margin-bottom: 28px;
        }}
        @media (max-width: 1024px) {{ .bots-grid {{ grid-template-columns: 1fr; }} }}

        .bot-card {{
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 16px;
            padding: 24px;
            position: relative;
            overflow: hidden;
        }}
        .bot-card::before {{
            content: '';
            position: absolute; top: 0; left: 0; right: 0; height: 3px;
        }}
        .bot-card.mr-paper::before {{ background: linear-gradient(90deg, #58a6ff, #388bfd); }}
        .bot-card.live::before {{ background: linear-gradient(90deg, #f0883e, #d29922); }}
        .bot-card.vol::before {{ background: linear-gradient(90deg, #f85149, #da3633); }}

        .bot-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }}
        .bot-name {{ font-size: 1rem; font-weight: 700; }}
        .bot-badge {{
            font-size: 0.65rem; padding: 3px 10px; border-radius: 20px;
            font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;
        }}
        .badge-paper {{ background: rgba(88,166,255,0.15); color: #58a6ff; }}
        .badge-live {{ background: rgba(240,136,62,0.2); color: #f0883e; }}
        .badge-vol {{ background: rgba(248,81,73,0.15); color: #f85149; }}

        .bot-balance {{ font-size: 2rem; font-weight: 800; margin-bottom: 4px; }}
        .bot-upl {{ font-size: 0.85rem; margin-bottom: 16px; }}

        /* Stats Row */
        .stats-row {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px; }}
        .stat-item {{ text-align: center; }}
        .stat-label {{ color: #8b949e; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.5px; }}
        .stat-val {{ font-size: 1.1rem; font-weight: 700; margin-top: 2px; }}

        /* Health */
        .health-row {{ display: flex; align-items: center; gap: 8px; font-size: 0.8rem; color: #8b949e; margin-bottom: 16px; }}
        .health-dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; animation: pulse 2s infinite; }}
        @keyframes pulse {{ 0%,100% {{ opacity:1 }} 50% {{ opacity:0.4 }} }}

        /* Open Positions */
        .open-positions {{ margin-bottom: 16px; }}
        .open-position {{
            display: flex; gap: 10px; align-items: center;
            padding: 8px 12px; background: rgba(255,255,255,0.03);
            border-radius: 8px; font-size: 0.82rem; margin-bottom: 4px;
        }}
        .open-dot {{ width: 8px; height: 8px; border-radius: 50%; background: #3fb950; animation: pulse 1.5s infinite; }}
        .no-positions {{ color: #484f58; font-size: 0.82rem; padding: 8px 0; }}

        /* Trades Table */
        .trades-section {{ margin-top: 8px; }}
        .trades-toggle {{
            background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);
            color: #8b949e; padding: 6px 14px; border-radius: 8px; cursor: pointer;
            font-size: 0.8rem; font-family: inherit; width: 100%;
        }}
        .trades-toggle:hover {{ background: rgba(255,255,255,0.1); color: #e6edf3; }}
        .trades-body {{ max-height: 0; overflow: hidden; transition: max-height 0.3s ease; }}
        .trades-body.open {{ max-height: 600px; overflow-y: auto; }}

        table {{ width: 100%; border-collapse: collapse; font-size: 0.78rem; margin-top: 8px; }}
        th {{ color: #8b949e; font-weight: 500; text-align: left; padding: 6px 8px; border-bottom: 1px solid rgba(255,255,255,0.06); }}
        td {{ padding: 6px 8px; border-bottom: 1px solid rgba(255,255,255,0.03); }}

        /* Colors */
        .positive {{ color: #3fb950; }}
        .negative {{ color: #f85149; }}
        .long {{ color: #58a6ff; }}
        .short {{ color: #f0883e; }}

        /* Service Status Footer */
        .footer {{ text-align: center; color: #484f58; font-size: 0.75rem; margin-top: 32px; padding-top: 16px; border-top: 1px solid rgba(255,255,255,0.05); }}

        /* Scrollbar */
        .trades-body::-webkit-scrollbar {{ width: 6px; }}
        .trades-body::-webkit-scrollbar-track {{ background: transparent; }}
        .trades-body::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.1); border-radius: 3px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎯 Trading Command Center</h1>
            <div class="subtitle">All bots • All accounts • Real-time overview</div>
            <div class="refresh-note">Auto-refreshes every 5 min • Last updated: {now}</div>
        </div>

        <!-- Portfolio Summary -->
        <div class="portfolio-bar">
            <div class="portfolio-stat">
                <div class="label">Combined Equity</div>
                <div class="value">${total_equity:,.2f}</div>
            </div>
            <div class="portfolio-stat">
                <div class="label">Total Realized P/L</div>
                <div class="value {"positive" if total_pnl >= 0 else "negative"}">${total_pnl:+,.2f}</div>
            </div>
            <div class="portfolio-stat">
                <div class="label">Live Balance</div>
                <div class="value" style="color:#f0883e">${live_data["equity"]:,.2f}</div>
            </div>
            <div class="portfolio-stat">
                <div class="label">Active Bots</div>
                <div class="value">3</div>
                <div class="value">2</div>
            </div>
        </div>

        <!-- Bot Cards -->
        <div class="bots-grid">
            <!-- Unified Regime Meta-Bot -->
            <div class="bot-card paper">
                <div class="bot-header">
                    <div>
                        <div class="bot-name">⚙️ Unified Regime Bot</div>
                        <div style="color:#8b949e;font-size:0.75rem;">Regime: <strong style="color:#e6edf3">{health_status.get("forex-trading-bot", {}).get("regime", "UNKNOWN")}</strong></div>
                        <div style="color:#8b949e;font-size:0.65rem;margin-top:2px;">{health_status.get("forex-trading-bot", {}).get("regime_reason", "")}</div>
                    </div>
                    <span class="bot-badge badge-paper">Paper</span>
                </div>
                <div class="bot-balance">${mr_paper["balance"]:,.2f}</div>
                <div class="bot-upl {"positive" if mr_paper["unrealized_pl"] >= 0 else "negative"}">
                    Unrealized: ${mr_paper["unrealized_pl"]:+.2f}
                </div>
                <div class="health-row">{health_dot("forex-trading-bot")}</div>
                <div class="stats-row">
                    <div class="stat-item">
                        <div class="stat-label">Trades</div>
                        <div class="stat-val">{mr_stats_73["count"]}</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Win Rate</div>
                        <div class="stat-val {"positive" if mr_stats_73["win_rate"] >= 55 else "negative"}">{mr_stats_73["win_rate"]:.0f}%</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">P/L (7.3)</div>
                        <div class="stat-val {"positive" if mr_stats_73["pnl"] >= 0 else "negative"}">${mr_stats_73["pnl"]:+,.0f}</div>
                    </div>
                </div>
                <div class="open-positions">{mr_open_html}</div>
                <div class="trades-section">
                    <button class="trades-toggle" onclick="toggleTrades('mr')">▼ Recent Trades ({min(20, mr_stats_all["count"])})</button>
                    <div id="mr-trades" class="trades-body">
                        <table><thead><tr><th>Date</th><th>Dir</th><th>Units</th><th>Entry</th><th>Exit</th><th>P/L</th><th>Hold</th></tr></thead>
                        <tbody>{mr_trade_rows}</tbody></table>
                    </div>
                </div>
            </div>

            <!-- Live Account -->
            <div class="bot-card live">
                <div class="bot-header">
                    <div>
                        <div class="bot-name">💰 Mean Reversion</div>
                        <div style="color:#8b949e;font-size:0.75rem;">USD/JPY • Real Capital</div>
                    </div>
                    <span class="bot-badge badge-live">LIVE</span>
                </div>
                <div class="bot-balance" style="color:#f0883e">${live_data["balance"]:,.2f}</div>
                <div class="bot-upl {"positive" if live_data["unrealized_pl"] >= 0 else "negative"}">
                    Unrealized: ${live_data["unrealized_pl"]:+.2f}
                </div>
                <div class="health-row">{health_dot("forex-bot-live")}</div>
                <div class="stats-row">
                    <div class="stat-item">
                        <div class="stat-label">Trades</div>
                        <div class="stat-val">{live_stats_all["count"]}</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Win Rate</div>
                        <div class="stat-val {"positive" if live_stats_all["win_rate"] >= 55 else "negative"}">{live_stats_all["win_rate"]:.0f}%</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Total P/L</div>
                        <div class="stat-val {"positive" if live_stats_all["pnl"] >= 0 else "negative"}">${live_stats_all["pnl"]:+,.2f}</div>
                    </div>
                </div>
                <div class="open-positions">{live_open_html}</div>
                <div class="trades-section">
                    {f'<button class="trades-toggle" onclick="toggleTrades(\'live\')">▼ Recent Trades ({live_stats_all["count"]})</button><div id="live-trades" class="trades-body"><table><thead><tr><th>Date</th><th>Dir</th><th>Units</th><th>Entry</th><th>Exit</th><th>P/L</th><th>Hold</th></tr></thead><tbody>{live_trade_rows}</tbody></table></div>' if live_stats_all["count"] > 0 else '<div class="no-positions">No trades yet — waiting for first signal</div>'}
                </div>
            </div>

        </div>

        <div class="footer">
            <p>Strategy: Mean Reversion (BB+RSI) • Volatility Breakout (Donchian+ATR+ADX) • Timeframe: M15</p>
            <p style="margin-top:4px">Updated: {now}</p>
        </div>
    </div>

    <script>
    function toggleTrades(id) {{
        const el = document.getElementById(id + '-trades');
        el.classList.toggle('open');
    }}
    </script>
</body>
</html>'''
    return html
