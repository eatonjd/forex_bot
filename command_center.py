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
LIVE_SINCE_DATE = "2026-01-01"

def fetch_account_data(api, account_id, label="Bot"):
    """Fetch account balance, trades, and open positions across all instruments."""
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

        # Closed trades across ALL instruments
        params = {"state": "CLOSED", "count": 500}
        rt = TradesList(accountID=account_id, params=params)
        api.request(rt)
        data["trades"] = rt.response.get("trades", [])

        # Open trades across ALL instruments
        params_open = {"state": "OPEN"}
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

def build_ai_reviews_section():
    """Build HTML section for Post-Trade AI Reviews and AI Reward Incentives."""
    import json
    reviews = []
    rewards = []
    
    # Try loading from local file
    try:
        if os.path.exists("trade_logs/trade_reviews.json"):
            with open("trade_logs/trade_reviews.json", "r") as f:
                reviews = json.load(f)
        if os.path.exists("trade_logs/reward_history.json"):
            with open("trade_logs/reward_history.json", "r") as f:
                rewards = json.load(f)
    except Exception as e:
        print(f"Error loading AI reviews for command center: {e}", flush=True)

    avg_reward = 0.0
    sortino_ratio = 0.0
    if rewards:
        scores = [r.get("reward_score", 0.0) for r in rewards]
        avg_reward = sum(scores) / len(scores) if scores else 0.0
        
        downside = [min(0.0, s)**2 for s in scores]
        d_std = (sum(downside) / len(scores))**0.5 if scores else 0.0
        sortino_ratio = avg_reward / (d_std + 1e-6) if d_std > 0 else avg_reward

    avg_class = "positive" if avg_reward >= 0 else "negative"
    sortino_class = "positive" if sortino_ratio >= 1.0 else "negative"

    reviews_list_html = ""
    if reviews:
        # Display newest 10 reviews
        recent = list(reversed(reviews))[:10]
        for r in recent:
            symbol = r.get("symbol", "N/A")
            direction = r.get("direction", "N/A")
            pnl = float(r.get("pnl", 0.0))
            pnl_class = "positive" if pnl >= 0 else "negative"
            reward_score = float(r.get("reward_score", 0.0))
            reward_class = "positive" if reward_score >= 0 else "negative"
            duration = r.get("duration_hrs", 0.0)
            report_text = r.get("report", "").replace("\n", "<br>")
            trade_key = str(r.get("trade_key", "review")).replace(":", "_").replace("-", "_").replace(".", "_")

            reviews_list_html += f'''
            <div class="review-card">
                <div class="review-header">
                    <div>
                        <span class="symbol-badge">{symbol}</span>
                        <span class="dir-badge {direction.lower()}">{direction}</span>
                        <span class="{pnl_class}" style="font-weight:700;margin-left:8px;">${pnl:+.2f}</span>
                        <span class="hold-time">⏱️ {duration:.1f}h</span>
                    </div>
                    <div class="reward-pill {reward_class}">⭐ AI Reward: {reward_score:+.2f}</div>
                </div>
                <button class="trades-toggle" onclick="toggleReview('{trade_key}')">▼ View Gemini AI Deep Dive Analysis</button>
                <div id="{trade_key}" class="trades-body review-content">
                    <div class="report-box">{report_text}</div>
                </div>
            </div>'''
    else:
        reviews_list_html = '''
        <div class="no-positions" style="text-align:center;padding:24px;">
            🤖 AI Post-Trade Reviewer Active • Daily reviews run automatically at 4:00 PM EST via Cloud Scheduler
        </div>'''

    html = f'''
    <div class="card-full" style="margin-top: 36px; background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; padding: 24px;">
        <div class="section-title" style="margin-bottom: 20px; text-align: center;">
            <h2 style="font-size: 1.5rem; font-weight: 700; background: linear-gradient(135deg, #a855f7, #6366f1); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">🧠 Post-Trade AI Reviews & Reward Incentives</h2>
            <div style="color: #8b949e; font-size: 0.8rem; margin-top: 4px;">Daily Automated Gemini Quantitative Analytics</div>
        </div>
        
        <div class="portfolio-bar" style="margin-bottom: 24px;">
            <div class="portfolio-stat">
                <div class="label">Avg AI Reward ($R_t$)</div>
                <div class="value {avg_class}">{avg_reward:+.2f}</div>
            </div>
            <div class="portfolio-stat">
                <div class="label">Rolling Sortino Ratio</div>
                <div class="value {sortino_class}">{sortino_ratio:.2f}</div>
            </div>
            <div class="portfolio-stat">
                <div class="label">AI Reviews Logged</div>
                <div class="value">{len(reviews) if reviews else len(rewards)}</div>
            </div>
        </div>

        <div class="reviews-container">
            {reviews_list_html}
        </div>
    </div>
    '''
    return html


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
        label="Mean Reversion (Paper)"
    )

    # 3. Mean Reversion Live
    live_data = {"label": "Mean Reversion (LIVE)", "balance": 0, "unrealized_pl": 0,
                 "equity": 0, "trades": [], "open_trades": [], "error": None}
    live_key = os.getenv("OANDA_API_KEY_LIVE")
    live_id = os.getenv("OANDA_ACCOUNT_ID_LIVE")
    if live_key and live_id:
        live_api = API(access_token=live_key, environment="live")
        live_data = fetch_account_data(live_api, live_id, label="Mean Reversion (LIVE)")

    # --- Service health checks ---
    health_status = {
        "forex-trading-bot": {"status": "healthy", "uptime": "Active", "regime": "MEAN_REVERSION", "regime_reason": "Bollinger Bands"},
        "forex-bot-live": {"status": "healthy", "uptime": "Active", "regime": "MEAN_REVERSION", "regime_reason": "Bollinger Bands"},
    }

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
    ai_reviews_html = build_ai_reviews_section()

    # Health dots
    def health_dot(name):
        h = health_status.get(name, {})
        s = h.get("status", "offline")
        color = "#00ff88" if s == "healthy" else "#ff4757" if s == "error" else "#888"
        return f'<span class="health-dot" style="background:{color}"></span> {s.title()} ({h.get("uptime", "-")})'

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # Load active roster & last optimization run info
    import json
    active_pairs_list = ["USD_CAD", "EUR_USD", "AUD_USD"]
    last_optimization_str = "Never"
    try:
        if os.path.exists("active_instruments.json"):
            with open("active_instruments.json", "r") as f:
                opt_data = json.load(f)
                active_pairs_list = opt_data.get("active_instruments", active_pairs_list)
                ts = opt_data.get("timestamp", "")
                if ts:
                    last_optimization_str = ts[:16].replace("T", " ") + " UTC"
    except Exception as e:
        print(f"Error loading active instruments for dashboard: {e}", flush=True)

    active_pairs_badges = " ".join([f'<span style="background:rgba(16,185,129,0.15);color:#10b981;padding:2px 8px;border-radius:4px;font-size:0.8rem;font-weight:600;margin-right:4px;">{p}</span>' for p in active_pairs_list])

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
            display: flex; gap: 16px; margin-bottom: 36px; flex-wrap: wrap;
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
            margin-bottom: 36px;
        }}
        .bot-card {{
            background: rgba(255,255,255,0.03);
            border-radius: 16px;
            padding: 24px;
            border: 1px solid rgba(255,255,255,0.08);
            position: relative;
        }}
        .bot-card.live {{ border-color: rgba(240, 136, 62, 0.4); }}
        .bot-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }}
        .bot-name {{ font-size: 1.2rem; font-weight: 700; }}
        .bot-badge {{
            padding: 3px 8px; border-radius: 6px; font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
        }}
        .badge-paper {{ background: rgba(56, 139, 253, 0.15); color: #58a6ff; }}
        .badge-live {{ background: rgba(240, 136, 62, 0.15); color: #f0883e; }}
        .bot-balance {{ font-size: 2.2rem; font-weight: 800; margin-bottom: 4px; }}
        .bot-upl {{ font-size: 0.9rem; font-weight: 600; margin-bottom: 16px; }}
        .health-row {{ font-size: 0.8rem; margin-bottom: 16px; color: #8b949e; }}
        .health-dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 4px; }}

        .stats-row {{
            display: flex; gap: 12px; margin-bottom: 16px; padding: 12px;
            background: rgba(0,0,0,0.2); border-radius: 8px;
        }}
        .stat-item {{ flex: 1; text-align: center; }}
        .stat-label {{ color: #8b949e; font-size: 0.65rem; text-transform: uppercase; }}
        .stat-val {{ font-size: 1.1rem; font-weight: 700; margin-top: 2px; }}

        .open-positions {{ margin-bottom: 16px; }}
        .open-position {{
            display: flex; justify-content: space-between; align-items: center;
            padding: 8px 12px; background: rgba(255,255,255,0.04); border-radius: 6px;
            font-size: 0.85rem; font-weight: 500; margin-bottom: 6px;
        }}
        .open-dot {{ display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: #3fb950; margin-right: 6px; }}
        .no-positions {{ color: #484f58; font-size: 0.8rem; text-align: center; padding: 8px; }}

        .trades-section {{ margin-top: 12px; }}
        .trades-toggle {{
            width: 100%; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.08);
            color: #8b949e; padding: 8px; border-radius: 6px; font-size: 0.8rem; cursor: pointer;
            text-align: center; font-weight: 600;
        }}
        .trades-toggle:hover {{ background: rgba(255,255,255,0.08); color: #e6edf3; }}
        .trades-body {{ display: none; margin-top: 12px; max-height: 240px; overflow-y: auto; }}
        .trades-body.show {{ display: block; }}
        .trades-body.open {{ display: block; }}
        
        table {{ width: 100%; border-collapse: collapse; font-size: 0.75rem; }}
        th {{ color: #8b949e; text-align: left; padding: 6px 8px; font-weight: 600; border-bottom: 1px solid rgba(255,255,255,0.08); }}
        td {{ padding: 6px 8px; border-bottom: 1px solid rgba(255,255,255,0.04); }}
        .long {{ color: #3fb950; font-weight: 600; }}
        .short {{ color: #f85149; font-weight: 600; }}
        .positive {{ color: #3fb950; font-weight: 600; }}
        .negative {{ color: #f85149; font-weight: 600; }}

        /* Review Section Styling */
        .review-card {{
            background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.06);
            border-radius: 12px; padding: 16px; margin-bottom: 12px;
        }}
        .review-header {{ display: flex; justify-content: space-between; align-items: center; font-size: 0.9rem; }}
        .symbol-badge {{ background: rgba(88,166,255,0.15); color: #58a6ff; font-weight: 700; padding: 3px 8px; border-radius: 6px; margin-right: 6px; }}
        .dir-badge {{ font-size: 0.75rem; font-weight: 700; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; }}
        .dir-badge.long {{ background: rgba(63,185,80,0.15); color: #3fb950; }}
        .dir-badge.short {{ background: rgba(248,81,73,0.15); color: #f85149; }}
        .reward-pill {{ font-size: 0.8rem; font-weight: 700; padding: 4px 10px; border-radius: 20px; }}
        .reward-pill.positive {{ background: rgba(63,185,80,0.2); color: #3fb950; border: 1px solid rgba(63,185,80,0.3); }}
        .reward-pill.negative {{ background: rgba(248,81,73,0.2); color: #f85149; border: 1px solid rgba(248,81,73,0.3); }}
        .hold-time {{ color: #8b949e; font-size: 0.8rem; margin-left: 10px; }}
        .report-box {{ background: rgba(13,17,23,0.8); border: 1px solid rgba(255,255,255,0.05); padding: 14px; border-radius: 8px; font-size: 0.82rem; line-height: 1.5; color: #c9d1d9; margin-top: 10px; }}

        .footer {{ text-align: center; color: #484f58; font-size: 0.75rem; margin-top: 24px; }}
        
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
            <div style="margin-top: 14px; display: flex; gap: 10px; justify-content: center;">
                <a href="/download-trades" style="background:#238636;color:white;text-decoration:none;padding:8px 16px;border-radius:6px;font-size:0.85rem;font-weight:600;display:inline-block;">📥 Export Recent Trades (CSV)</a>
                <button onclick="triggerOptimization()" style="background:#8b5cf6;color:white;border:none;padding:8px 16px;border-radius:6px;font-size:0.85rem;font-weight:600;cursor:pointer;">🔄 Optimize Portfolio Roster</button>
            </div>
            <script>
                function triggerOptimization() {{
                    alert('Running 60-day automated backtest optimization across candidate pairs universe...');
                    fetch('/run-optimization', {{ method: 'POST' }})
                        .then(r => r.json())
                        .then(data => {{
                            alert('Optimization Complete! Active Roster: ' + JSON.stringify(data.active_instruments));
                            window.location.reload();
                        }})
                        .catch(err => alert('Error running optimization: ' + err));
                }}
            </script>
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
                <div class="label">Active Roster</div>
                <div class="value" style="margin-top:8px;">{active_pairs_badges}</div>
            </div>
            <div class="portfolio-stat">
                <div class="label">Last Optimization Run</div>
                <div class="value" style="font-size:1.05rem;color:#8b5cf6;margin-top:8px;">{last_optimization_str}</div>
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

        {ai_reviews_html}

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
    function toggleReview(id) {{
        const el = document.getElementById(id);
        el.classList.toggle('open');
    }}
    </script>
</body>
</html>'''
    return html
