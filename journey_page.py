"""
Enhanced Trading Journey Page
- Bot fix timeline with visual markers
- Candlestick chart with entry/exit points
- Advanced performance metrics (Sharpe, max drawdown, win streak)
- Trade filtering by date, direction, P/L
- Regime analysis showing profitable periods
- Trade annotations (RSI, BB position)
- Mobile-friendly responsive design
"""

import os
from datetime import datetime, timedelta
import json

# Bot fix timeline - key dates when performance fixes were introduced
# Based on git history and trade data analysis
BOT_FIX_TIMELINE = [
    {
        "date": "2026-01-12",
        "title": "Profit Target & Trailing Adjusted",
        "description": "After a -$290 loss on a SHORT trade that erased gains, lowered profit targets and trailing stop amounts.",
        "trigger_trade": "-$290.21 on Jan 12 SHORT",
        "impact": "More conservative profit taking",
        "icon": "📉",
    },
    {
        "date": "2026-01-13",
        "title": "Safety Features Added",
        "description": "Added 50-pip stop loss and daily loss limit to prevent runaway losses.",
        "trigger_trade": "Multiple large losses pattern",
        "impact": "Hard stops on max loss per trade and per day",
        "icon": "🛑",
    },
    {
        "date": "2026-01-14",
        "title": "Probe Entry System",
        "description": "After -$210 loss, implemented probe entry: start with 40% size, scale up only if trade confirms profitable.",
        "trigger_trade": "-$210.45 on Jan 14 LONG",
        "impact": "Smaller initial position size, reduced risk on wrong entries",
        "icon": "🔍",
    },
    {
        "date": "2026-01-23",
        "title": "Regime Filter Added",
        "description": "After Jan 22-23 'death spiral' of 6 consecutive losses totaling -$519, added market regime detection to prevent counter-trend trades.",
        "trigger_trade": "Jan 22-23: -$14, -$84, -$81, -$166, -$103, -$71 = -$519 total",
        "impact": "No more buying in downtrends, selling in uptrends",
        "icon": "🛡️",
    },
    {
        "date": "2026-01-23",
        "title": "Trend-Following Mode",
        "description": "Enabled trading WITH the trend instead of only mean-reversion. Now shorts pullbacks in downtrends, buys dips in uptrends.",
        "trigger_trade": "Same death spiral - needed to profit from trends, not fight them",
        "impact": "Can profit from trending markets instead of sitting out",
        "icon": "📈",
    },
    {
        "date": "2026-01-24",
        "title": "Market Hours Check",
        "description": "Added weekend market closure detection. Orders were failing with MARKET_HALTED during forex closed hours.",
        "trigger_trade": "Multiple MARKET_HALTED order rejections",
        "impact": "No wasted API calls on weekends, cleaner logs",
        "icon": "🌙",
    },
    {
        "date": "2026-01-29",
        "title": "Enhanced Regime Detection",
        "description": "After Jan 26-28 losses ($337 from shorting into uptrends), lowered slope threshold from 0.03 to 0.015 and added price-to-SMA confirmation. Bot was classifying uptrends as RANGING, allowing counter-trend shorts.",
        "trigger_trade": "Jan 26-28: -$157, -$57, -$56, -$52 = -$322 in SHORT losses during uptrends",
        "impact": "More sensitive trend detection, catches moderate uptrends/downtrends",
        "icon": "🎯",
    },
    {
        "date": "2026-02-13",
        "title": "Phase 7.3: Performance Recovery (8 Fixes)",
        "description": "After Feb 8-13 losses (-$123, LONGs 33% WR in downtrend), implemented: widened regime detection (5→20 candles), disabled probe scaling, SMA cross confirmation, server-side OANDA stop losses, narrowed trend RSI windows, 2x ATR volatility pause, short-only mode in downtrend, and BOT_PAUSED env var.",
        "trigger_trade": "Feb 8-13: -$218 from LONGs in confirmed downtrend (9 trades, 33% WR)",
        "impact": "Server-side stop losses prevent gap-through, SMA cross blocks counter-trend entries",
        "icon": "🛡️",
    },
]


def calculate_advanced_metrics(trades, start_balance=5000):
    """Calculate advanced performance metrics"""
    if not trades:
        return {}

    # Sort trades by date (oldest first)
    sorted_trades = sorted(trades, key=lambda t: t.get("openTime", ""))

    # Calculate equity curve
    equity = start_balance
    equity_curve = [equity]
    daily_returns = []
    peak = equity
    max_drawdown = 0
    max_drawdown_pct = 0

    for t in sorted_trades:
        pnl = float(t.get("realizedPL", 0))
        prev_equity = equity
        equity += pnl
        equity_curve.append(equity)

        # Daily return (approximate - using trade-by-trade)
        if prev_equity > 0:
            daily_returns.append(pnl / prev_equity)

        # Track peak and drawdown
        if equity > peak:
            peak = equity
        drawdown = peak - equity
        drawdown_pct = (drawdown / peak * 100) if peak > 0 else 0
        if drawdown_pct > max_drawdown_pct:
            max_drawdown_pct = drawdown_pct
            max_drawdown = drawdown

    # Calculate Sharpe Ratio (annualized, assuming 252 trading days)
    if daily_returns and len(daily_returns) > 1:
        import statistics

        mean_return = statistics.mean(daily_returns)
        std_return = (
            statistics.stdev(daily_returns) if len(daily_returns) > 1 else 0.0001
        )
        sharpe_ratio = (mean_return / std_return) * (252**0.5) if std_return > 0 else 0
    else:
        sharpe_ratio = 0

    # Win/Loss streaks
    current_streak = 0
    max_win_streak = 0
    max_loss_streak = 0
    current_win_streak = 0
    current_loss_streak = 0

    for t in sorted_trades:
        pnl = float(t.get("realizedPL", 0))
        if pnl > 0:
            current_win_streak += 1
            current_loss_streak = 0
            max_win_streak = max(max_win_streak, current_win_streak)
        elif pnl < 0:
            current_loss_streak += 1
            current_win_streak = 0
            max_loss_streak = max(max_loss_streak, current_loss_streak)

    # Best and worst trades
    pnls = [float(t.get("realizedPL", 0)) for t in trades]
    best_trade = max(pnls) if pnls else 0
    worst_trade = min(pnls) if pnls else 0

    # Average holding time
    holding_times = []
    for t in sorted_trades:
        try:
            open_time = datetime.fromisoformat(
                t.get("openTime", "").replace("Z", "+00:00")
            )
            close_time = datetime.fromisoformat(
                t.get("closeTime", "").replace("Z", "+00:00")
            )
            holding_times.append(
                (close_time - open_time).total_seconds() / 3600
            )  # hours
        except:
            pass
    avg_holding_hours = sum(holding_times) / len(holding_times) if holding_times else 0

    return {
        "sharpe_ratio": round(sharpe_ratio, 2),
        "max_drawdown": round(max_drawdown, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 1),
        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,
        "best_trade": round(best_trade, 2),
        "worst_trade": round(worst_trade, 2),
        "avg_holding_hours": round(avg_holding_hours, 1),
        "equity_curve": equity_curve,
    }


def get_trade_phase(trade_date_str):
    """Determine which phase a trade belongs to based on actual bot fix dates"""
    try:
        trade_date = datetime.fromisoformat(
            trade_date_str.replace("Z", "+00:00")
        ).date()
    except Exception:
        return "Unknown", "#888888", "No phase info"

    # Define phases based on actual git commits and fix dates
    # Phase 1: Before any safety features (Dec 23 - Jan 11)
    if trade_date < datetime(2026, 1, 12).date():
        return "Phase 1: Early", "#4caf50", "Original mean-reversion, no safety limits"
    # Phase 2: Safety features added (Jan 12-13)
    elif trade_date < datetime(2026, 1, 14).date():
        return "Phase 2: Safety", "#ffc107", "50-pip stop loss, daily loss limit added"
    # Phase 3: Probe entry added (Jan 14 - Jan 23) - includes the death spiral
    elif trade_date < datetime(2026, 1, 24).date():
        return "Phase 3: Probe", "#2196f3", "40% probe entry, scale on confirmation"
    # Phase 4: Regime filter added (Jan 24 - Jan 28)
    elif trade_date < datetime(2026, 1, 29).date():
        return (
            "Phase 4: Regime",
            "#4ecdc4",
            "Trend detection active - Go-Live Reset started",
        )
    # Phase 5: Enhanced regime detection (Jan 29 - Jan 31)
    elif trade_date < datetime(2026, 2, 1).date():
        return (
            "Phase 5: Enhanced",
            "#9b59b6",
            "Improved regime sensitivity - lower slope threshold",
        )
    # Phase 6: Trailing stop fix preparation (Feb 1)
    elif trade_date < datetime(2026, 2, 2).date():
        return (
            "Phase 6: Pre-Trailing",
            "#e74c3c",
            "Trailing stop threshold lowered to $50",
        )
    # Phase 7: Initial trailing stop deployment (Feb 2 - Feb 5)
    elif trade_date < datetime(2026, 2, 6).date():
        return (
            "Phase 7: Trailing",
            "#f39c12",
            "Trailing $20 activate, $10 trail, profit target disabled",
        )
    # Phase 7.1: Trailing stop optimization (Feb 6 before 21:45 UTC = before position fix)
    elif trade_date == datetime(2026, 2, 6).date():
        # Check time as well for 7.1 vs 7.2 transition
        try:
            trade_dt = datetime.fromisoformat(trade_date_str.replace("Z", "+00:00"))
            if trade_dt.hour < 21 or (trade_dt.hour == 21 and trade_dt.minute < 45):
                return (
                    "Phase 7.1: Trailing Opt",
                    "#3498db",
                    "Trailing stop working: $20 activate, $10 trail",
                )
        except:
            pass
        return (
            "Phase 7.2: Position Fix",
            "#1abc9c",
            "True 2% risk, no daily profit cap",
        )
    # Phase 7.2: Position sizing fix + no profit cap (Feb 6 21:45 UTC+)
    elif trade_date < datetime(2026, 2, 13).date():
        return (
            "Phase 7.2: Position Fix",
            "#1abc9c",
            "True 2% risk, no daily profit cap",
        )
    # Phase 7.3: SMA Cross + regime filter (Feb 13+)
    else:
        return (
            "Phase 7.3: Regime Fix",
            "#4ecdc4",
            "Stronger regime + SMA cross directional filter",
        )


def generate_journey_html(trades, start_balance=5000):
    """Generate the enhanced journey HTML page"""

    # Calculate basic stats
    total_pnl = sum(float(t.get("realizedPL", 0)) for t in trades)
    winners = [t for t in trades if float(t.get("realizedPL", 0)) > 0]
    losers = [t for t in trades if float(t.get("realizedPL", 0)) < 0]
    win_pnl = sum(float(t.get("realizedPL", 0)) for t in winners)
    loss_pnl = sum(float(t.get("realizedPL", 0)) for t in losers)
    win_rate = (len(winners) / len(trades) * 100) if trades else 0
    profit_factor = abs(win_pnl / loss_pnl) if loss_pnl else 0
    avg_winner = win_pnl / len(winners) if winners else 0
    avg_loser = loss_pnl / len(losers) if losers else 0

    # Advanced metrics
    metrics = calculate_advanced_metrics(trades, start_balance)

    # Build equity curve data points with dates
    sorted_trades = sorted(trades, key=lambda t: t.get("openTime", ""))
    equity = start_balance
    equity_points = []

    for i, t in enumerate(sorted_trades):
        date_str = t.get("openTime", "")[:10]
        pnl = float(t.get("realizedPL", 0))
        equity += pnl
        phase, color, desc = get_trade_phase(t.get("openTime", ""))
        equity_points.append(
            {
                "x": date_str,
                "y": round(equity, 2),
                "pnl": round(pnl, 2),
                "phase": phase,
                "desc": desc,
            }
        )

    # Phase analysis by actual phases
    phase1_trades = [
        t for t in trades if "Phase 1" in get_trade_phase(t.get("openTime", ""))[0]
    ]
    phase2_trades = [
        t for t in trades if "Phase 2" in get_trade_phase(t.get("openTime", ""))[0]
    ]
    phase3_trades = [
        t for t in trades if "Phase 3" in get_trade_phase(t.get("openTime", ""))[0]
    ]
    phase4_trades = [
        t for t in trades if "Phase 4" in get_trade_phase(t.get("openTime", ""))[0]
    ]
    phase5_trades = [
        t for t in trades if "Phase 5" in get_trade_phase(t.get("openTime", ""))[0]
    ]
    phase6_trades = [
        t for t in trades if "Phase 6" in get_trade_phase(t.get("openTime", ""))[0]
    ]
    phase7_trades = [
        t for t in trades if "Phase 7:" in get_trade_phase(t.get("openTime", ""))[0]
    ]
    phase71_trades = [
        t for t in trades if "Phase 7.1" in get_trade_phase(t.get("openTime", ""))[0]
    ]
    phase72_trades = [
        t for t in trades if "Phase 7.2" in get_trade_phase(t.get("openTime", ""))[0]
    ]
    phase73_trades = [
        t for t in trades if "Phase 7.3" in get_trade_phase(t.get("openTime", ""))[0]
    ]

    def phase_stats(phase_trades):
        if not phase_trades:
            return 0, 0, 0
        pnl = sum(float(t.get("realizedPL", 0)) for t in phase_trades)
        wins = len([t for t in phase_trades if float(t.get("realizedPL", 0)) > 0])
        wr = wins / len(phase_trades) * 100
        return len(phase_trades), pnl, wr

    p1_count, p1_pnl, p1_wr = phase_stats(phase1_trades)
    p2_count, p2_pnl, p2_wr = phase_stats(phase2_trades)
    p3_count, p3_pnl, p3_wr = phase_stats(phase3_trades)
    p4_count, p4_pnl, p4_wr = phase_stats(phase4_trades)
    p5_count, p5_pnl, p5_wr = phase_stats(phase5_trades)
    p6_count, p6_pnl, p6_wr = phase_stats(phase6_trades)
    p7_count, p7_pnl, p7_wr = phase_stats(phase7_trades)
    p71_count, p71_pnl, p71_wr = phase_stats(phase71_trades)
    p72_count, p72_pnl, p72_wr = phase_stats(phase72_trades)
    p73_count, p73_pnl, p73_wr = phase_stats(phase73_trades)

    # Calculate Phase 7.3 Drawdown specifically
    p73_max_dd = 0
    if phase73_trades:
        # Initial balance for Phase 7.3 is current balance minus Phase 7.3 P/L
        p73_start_bal = (start_balance + total_pnl) - p73_pnl
        p73_bal = p73_start_bal
        p73_peak = p73_bal
        for t in sorted(phase73_trades, key=lambda x: x.get("closeTime", "")):
            p73_bal += float(t.get("realizedPL", 0))
            if p73_bal > p73_peak:
                p73_peak = p73_bal
            dd = (p73_peak - p73_bal) / p73_peak * 100
            if dd > p73_max_dd:
                p73_max_dd = dd

    # Build trade rows with full details
    # Sort trades oldest-first so running balance accumulates correctly
    trades_sorted = sorted(trades, key=lambda t: t.get("openTime", ""))
    trade_rows_list = []
    running_balance = start_balance
    for t in trades_sorted:
        open_time_full = t.get("openTime", "")
        close_time_full = t.get("closeTime", "")
        open_time = open_time_full[:10]
        open_time_short = open_time_full[11:16] if len(open_time_full) > 16 else ""
        close_time_short = close_time_full[11:16] if len(close_time_full) > 16 else ""

        units = int(float(t.get("initialUnits", 0)))
        direction = "LONG" if units > 0 else "SHORT"
        entry = float(t.get("price", 0))

        # Get close price from averageClosePrice
        close_price = float(t.get("averageClosePrice", entry))

        # Calculate pips (for JPY pairs, 1 pip = 0.01)
        pip_size = 0.01
        if direction == "LONG":
            pips = (close_price - entry) / pip_size
        else:
            pips = (entry - close_price) / pip_size

        pnl = float(t.get("realizedPL", 0))
        pnl_class = "positive" if pnl >= 0 else "negative"
        running_balance += pnl

        # Calculate holding time
        try:
            from datetime import datetime as dt

            open_dt = dt.fromisoformat(open_time_full.replace("Z", "+00:00"))
            close_dt = dt.fromisoformat(close_time_full.replace("Z", "+00:00"))
            hold_seconds = (close_dt - open_dt).total_seconds()
            if hold_seconds < 3600:
                hold_str = f"{int(hold_seconds / 60)}m"
            elif hold_seconds < 86400:
                hold_str = f"{hold_seconds / 3600:.1f}h"
            else:
                hold_str = f"{hold_seconds / 86400:.1f}d"
        except:
            hold_str = "-"

        phase, phase_color, phase_desc = get_trade_phase(open_time_full)
        # Phase icons
        if "Phase 1" in phase:
            phase_icon = "🚀"
        elif "Phase 2" in phase:
            phase_icon = "🛑"
        elif "Phase 3" in phase:
            phase_icon = "🔍"
        elif "Phase 4" in phase:
            phase_icon = "🛡️"
        elif "Phase 5" in phase:
            phase_icon = "🎯"
        elif "Phase 6" in phase:
            phase_icon = "📉"
        elif "Phase 7.2" in phase:
            phase_icon = "✨"
        elif "Phase 7.1" in phase:
            phase_icon = "📈"
        elif "Phase 7" in phase:
            phase_icon = "🔄"
        else:
            phase_icon = "❓"

        trade_rows_list.append(f'''
        <tr data-date="{open_time}" data-direction="{direction}" data-pnl="{pnl}" data-phase="{phase}">
            <td><span class="phase-indicator" style="color:{phase_color}" title="{phase_desc}">{phase_icon}</span> {open_time}</td>
            <td class="{direction.lower()}">{direction}</td>
            <td>{abs(units):,}</td>
            <td>{entry:.3f} → {close_price:.3f}</td>
            <td class="{pnl_class}">{pips:+.1f} pips</td>
            <td class="{pnl_class}">${pnl:+,.2f}</td>
            <td>${running_balance:,.0f}</td>
            <td>{hold_str}</td>
            <td class="phase-desc" style="color:{phase_color};font-size:0.75rem;">{phase_desc}</td>
        </tr>''')

    # Reverse so newest trades appear at top of the table
    trade_rows_list.reverse()
    trade_rows = "".join(trade_rows_list)

    # Build fix timeline HTML
    fix_timeline_html = ""
    for fix in BOT_FIX_TIMELINE:
        fix_timeline_html += f"""
        <div class="timeline-item">
            <div class="timeline-icon">{fix["icon"]}</div>
            <div class="timeline-content">
                <div class="timeline-date">{fix["date"]}</div>
                <div class="timeline-title">{fix["title"]}</div>
                <div class="timeline-desc">{fix["description"]}</div>
                <div class="timeline-impact">Impact: {fix["impact"]}</div>
            </div>
        </div>"""

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>USD/JPY Trading Journey</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns"></script>
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{ 
                font-family: 'Inter', -apple-system, sans-serif; 
                background: linear-gradient(135deg, #0a0a1a 0%, #1a1a3e 50%, #0a0a1a 100%);
                color: #e0e0e0;
                min-height: 100vh;
                padding: 20px;
            }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            
            /* Header */
            .header {{ text-align: center; margin-bottom: 40px; }}
            h1 {{ font-size: 2.5rem; margin-bottom: 10px; color: #fff; 
                  background: linear-gradient(135deg, #4ecdc4, #44a08d);
                  -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
            .subtitle {{ color: #888; margin-bottom: 20px; }}
            
            /* Stats Grid */
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                gap: 15px;
                margin-bottom: 30px;
            }}
            .stat-card {{
                background: rgba(255,255,255,0.03);
                border-radius: 12px;
                padding: 20px;
                text-align: center;
                border: 1px solid rgba(255,255,255,0.08);
                transition: transform 0.2s, box-shadow 0.2s;
            }}
            .stat-card:hover {{
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(0,0,0,0.3);
            }}
            .stat-value {{ font-size: 1.6rem; font-weight: 700; color: #4ecdc4; }}
            .stat-value.positive {{ color: #4caf50; }}
            .stat-value.negative {{ color: #f44336; }}
            .stat-label {{ font-size: 0.8rem; color: #888; margin-top: 8px; text-transform: uppercase; letter-spacing: 0.5px; }}
            
            /* Section Headers */
            .section-header {{
                display: flex;
                align-items: center;
                gap: 10px;
                margin: 30px 0 15px 0;
                padding-bottom: 10px;
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }}
            .section-header h2 {{ font-size: 1.2rem; color: #fff; }}
            .section-header .icon {{ font-size: 1.4rem; }}
            
            /* Chart Container */
            .chart-container {{
                background: rgba(255,255,255,0.02);
                border-radius: 16px;
                padding: 25px;
                margin-bottom: 30px;
                border: 1px solid rgba(255,255,255,0.05);
            }}
            
            /* Timeline */
            .timeline {{
                position: relative;
                padding-left: 30px;
            }}
            .timeline::before {{
                content: '';
                position: absolute;
                left: 10px;
                top: 0;
                bottom: 0;
                width: 2px;
                background: linear-gradient(180deg, #4ecdc4, #44a08d);
            }}
            .timeline-item {{
                position: relative;
                margin-bottom: 25px;
                padding-left: 25px;
            }}
            .timeline-icon {{
                position: absolute;
                left: -25px;
                top: 0;
                font-size: 1.2rem;
                background: #1a1a3e;
                padding: 5px;
                border-radius: 50%;
            }}
            .timeline-content {{
                background: rgba(255,255,255,0.03);
                border-radius: 10px;
                padding: 15px 20px;
                border-left: 3px solid #4ecdc4;
            }}
            .timeline-date {{ font-size: 0.8rem; color: #4ecdc4; font-weight: 600; }}
            .timeline-title {{ font-size: 1rem; color: #fff; margin: 5px 0; font-weight: 600; }}
            .timeline-desc {{ font-size: 0.85rem; color: #aaa; margin-bottom: 8px; }}
            .timeline-impact {{ font-size: 0.8rem; color: #4caf50; font-style: italic; }}
            
            /* Phase Comparison */
            .phase-comparison {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 20px;
                margin-bottom: 30px;
            }}
            .phase-card {{
                background: rgba(255,255,255,0.03);
                border-radius: 12px;
                padding: 20px;
                text-align: center;
            }}
            .phase-card.pre-fix {{ border-left: 4px solid #ff6b6b; }}
            .phase-card.post-fix {{ border-left: 4px solid #4ecdc4; }}
            .phase-title {{ font-size: 1rem; color: #fff; margin-bottom: 15px; font-weight: 600; }}
            .phase-stat {{ font-size: 0.9rem; color: #aaa; margin: 8px 0; }}
            .phase-stat strong {{ color: #fff; }}
            
            /* Filters */
            .filters {{
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                margin-bottom: 20px;
                padding: 15px;
                background: rgba(255,255,255,0.02);
                border-radius: 10px;
            }}
            .filter-group {{ display: flex; align-items: center; gap: 8px; }}
            .filter-group label {{ font-size: 0.85rem; color: #888; }}
            .filter-group select, .filter-group input {{
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.1);
                color: #fff;
                padding: 8px 12px;
                border-radius: 6px;
                font-size: 0.85rem;
            }}
            .filter-btn {{
                background: linear-gradient(135deg, #4ecdc4, #44a08d);
                border: none;
                color: #fff;
                padding: 8px 20px;
                border-radius: 6px;
                cursor: pointer;
                font-weight: 600;
                transition: opacity 0.2s;
            }}
            .filter-btn:hover {{ opacity: 0.9; }}
            
            /* Table */
            .table-container {{
                overflow-x: auto;
                background: rgba(255,255,255,0.02);
                border-radius: 12px;
                border: 1px solid rgba(255,255,255,0.05);
            }}
            table {{ width: 100%; border-collapse: collapse; min-width: 500px; }}
            th, td {{ padding: 14px 16px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.05); }}
            th {{ background: rgba(255,255,255,0.03); color: #4ecdc4; font-weight: 600; font-size: 0.85rem; text-transform: uppercase; }}
            td {{ font-size: 0.9rem; }}
            tr:hover {{ background: rgba(255,255,255,0.02); }}
            .positive {{ color: #4caf50; font-weight: 600; }}
            .negative {{ color: #f44336; font-weight: 600; }}
            .long {{ color: #4caf50; }}
            .short {{ color: #f44336; }}
            .phase-indicator {{ margin-right: 5px; }}
            
            /* Footer */
            .footer {{ text-align: center; margin-top: 50px; padding: 20px; color: #555; font-size: 0.85rem; }}
            
            /* Mobile Responsive */
            @media (max-width: 768px) {{
                body {{ padding: 10px; }}
                h1 {{ font-size: 1.8rem; }}
                .stats-grid {{ grid-template-columns: repeat(2, 1fr); gap: 10px; }}
                .stat-card {{ padding: 15px; }}
                .stat-value {{ font-size: 1.3rem; }}
                .phase-comparison {{ grid-template-columns: 1fr; }}
                .filters {{ flex-direction: column; }}
                .filter-group {{ width: 100%; }}
                .filter-group select, .filter-group input {{ flex: 1; }}
                .chart-container {{ padding: 15px; }}
                th, td {{ padding: 10px 8px; font-size: 0.8rem; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📈 USD/JPY Trading Journey</h1>
                <p class="subtitle">Mean Reversion + Trend Following Strategy • Demo Account</p>
            </div>
            
            <!-- Primary Stats -->
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value {"positive" if total_pnl >= 0 else "negative"}">${total_pnl:+,.2f}</div>
                    <div class="stat-label">Total P/L</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{len(trades)}</div>
                    <div class="stat-label">Total Trades</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{win_rate:.1f}%</div>
                    <div class="stat-label">Win Rate</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{profit_factor:.2f}</div>
                    <div class="stat-label">Profit Factor</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{metrics.get("sharpe_ratio", 0):.2f}</div>
                    <div class="stat-label">Sharpe Ratio</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value negative">-{metrics.get("max_drawdown_pct", 0):.1f}%</div>
                    <div class="stat-label">Max Drawdown</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value positive">🔥 {metrics.get("max_win_streak", 0)}</div>
                    <div class="stat-label">Best Streak</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value negative">🚫 {metrics.get("max_loss_streak", 0)}</div>
                    <div class="stat-label">Worst Streak</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{metrics.get("avg_holding_hours", 0):.1f}h</div>
                    <div class="stat-label">Avg Hold Time</div>
                </div>
            </div>
            
            <!-- Go-Live Readiness (Phase 7.3 Reset) -->
            <div class="section-header">
                <span class="icon">🎯</span>
                <h2>Go-Live Readiness (Phase 7.3 Reset)</h2>
            </div>
            <div class="stat-card" style="text-align:left; padding: 25px; margin-bottom: 30px; border-left: 5px solid #4ecdc4;">
                <div style="font-size:0.9rem; color:#888; margin-bottom:15px;">
                    Tracking progress for <strong>Phase 7.3</strong> (Regime + SMA Cross filter deployment) towards live trading qualification.
                </div>
                <div class="stats-grid" style="grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));">
                    <div style="padding: 10px;">
                        <div style="font-size:0.8rem; color:#888;">TOTAL TRADES</div>
                        <div style="font-size:1.5rem; font-weight:bold;">{p73_count} / 50</div>
                        <div style="height:8px; background:rgba(255,255,255,0.1); border-radius:4px; margin-top:8px;">
                            <div style="height:100%; width:{min(p73_count / 50 * 100, 100):.0f}%; background:#4ecdc4; border-radius:4px;"></div>
                        </div>
                    </div>
                    <div style="padding: 10px;">
                        <div style="font-size:0.8rem; color:#888;">WIN RATE (GOAL: >55%)</div>
                        <div style="font-size:1.5rem; font-weight:bold; color:{"#4caf50" if p73_wr >= 55 else "#ffc107" if p73_wr >= 45 else "#f44336"}">{p73_wr:.1f}%</div>
                        <div style="font-size:0.75rem; color:#888; margin-top:4px;">Status: {"✅ REACHED" if p73_wr >= 55 else "🟡 TRACKING" if p73_wr >= 45 else "❌ BELOW GOAL"}</div>
                    </div>
                    <div style="padding: 10px;">
                        <div style="font-size:0.8rem; color:#888;">MAX DRAWDOWN (GOAL: <10%)</div>
                        <div style="font-size:1.5rem; font-weight:bold; color:{"#4caf50" if p73_max_dd < 10 else "#f44336"}">{p73_max_dd:.1f}%</div>
                        <div style="font-size:0.75rem; color:#888; margin-top:4px;">Status: {"✅ SAFE" if p73_max_dd < 10 else "❌ BREACHED"}</div>
                    </div>
                </div>
            </div>
            
            <!-- Trade History with Filters (MOVED UP) -->
            <div class="section-header">
                <span class="icon">📋</span>
                <h2>Trade History</h2>
            </div>
            
            <div class="filters">
                <div class="filter-group">
                    <label>Direction:</label>
                    <select id="filterDirection">
                        <option value="all">All</option>
                        <option value="LONG">Long Only</option>
                        <option value="SHORT">Short Only</option>
                    </select>
                </div>
                <div class="filter-group">
                    <label>Result:</label>
                    <select id="filterResult">
                        <option value="all">All</option>
                        <option value="winners">Winners Only</option>
                        <option value="losers">Losers Only</option>
                    </select>
                </div>
                <div class="filter-group">
                    <label>Phase:</label>
                    <select id="filterPhase">
                        <option value="all">All Phases</option>
                        <option value="Phase 1">Phase 1: Early</option>
                        <option value="Phase 2">Phase 2: Safety</option>
                        <option value="Phase 3">Phase 3: Probe</option>
                        <option value="Phase 4">Phase 4: Regime</option>
                        <option value="Phase 5">Phase 5: Enhanced</option>
                        <option value="Phase 6">Phase 6: Pre-Trailing</option>
                        <option value="Phase 7:">Phase 7: Trailing</option>
                        <option value="Phase 7.1">Phase 7.1: Trailing Opt</option>
                        <option value="Phase 7.2">Phase 7.2: Position Fix</option>
                    </select>
                </div>
                <button class="filter-btn" onclick="applyFilters()">Apply Filters</button>
                <button class="filter-btn" style="background: #666;" onclick="resetFilters()">Reset</button>
            </div>
            
            <div class="table-container">
                <table id="tradesTable">
                    <thead>
                        <tr><th>Date</th><th>Dir</th><th>Units</th><th>Entry → Exit</th><th>Pips</th><th>P/L</th><th>Balance</th><th>Hold</th><th>Bot Phase</th></tr>
                    </thead>
                    <tbody>
                        {trade_rows}
                    </tbody>
                </table>
            </div>
            
            <!-- Equity Curve -->
            <div class="section-header">
                <span class="icon">📈</span>
                <h2>Equity Curve</h2>
            </div>
            <div class="chart-container">
                <canvas id="equityChart" height="300"></canvas>
            </div>
            
            <!-- Phase Comparison (5 PHASES) -->
            <div class="section-header">
                <span class="icon">📊</span>
                <h2>Performance by Phase</h2>
            </div>
            <div class="stats-grid" style="grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));">
                <div class="stat-card" style="border-left: 4px solid #4caf50;">
                    <div class="stat-value">🚀 {p1_count}</div>
                    <div class="stat-label">Phase 1: Early</div>
                    <div style="font-size:0.75rem;color:#888;margin-top:5px;">P/L: <span class="{"positive" if p1_pnl >= 0 else "negative"}">${p1_pnl:+,.0f}</span> | WR: {p1_wr:.0f}%</div>
                </div>
                <div class="stat-card" style="border-left: 4px solid #ffc107;">
                    <div class="stat-value">🛑 {p2_count}</div>
                    <div class="stat-label">Phase 2: Safety</div>
                    <div style="font-size:0.75rem;color:#888;margin-top:5px;">P/L: <span class="{"positive" if p2_pnl >= 0 else "negative"}">${p2_pnl:+,.0f}</span> | WR: {p2_wr:.0f}%</div>
                </div>
                <div class="stat-card" style="border-left: 4px solid #2196f3;">
                    <div class="stat-value">🔍 {p3_count}</div>
                    <div class="stat-label">Phase 3: Probe</div>
                    <div style="font-size:0.75rem;color:#888;margin-top:5px;">P/L: <span class="{"positive" if p3_pnl >= 0 else "negative"}">${p3_pnl:+,.0f}</span> | WR: {p3_wr:.0f}%</div>
                </div>
                <div class="stat-card" style="border-left: 4px solid #4ecdc4;">
                    <div class="stat-value">🛡️ {p4_count}</div>
                    <div class="stat-label">Phase 4: Regime</div>
                    <div style="font-size:0.75rem;color:#888;margin-top:5px;">P/L: <span class="{"positive" if p4_pnl >= 0 else "negative"}">${p4_pnl:+,.0f}</span> | WR: {p4_wr:.0f}%</div>
                </div>
                <div class="stat-card" style="border-left: 4px solid #9b59b6;">
                    <div class="stat-value">🎯 {p5_count}</div>
                    <div class="stat-label">Phase 5: Enhanced</div>
                    <div style="font-size:0.75rem;color:#888;margin-top:5px;">P/L: <span class="{"positive" if p5_pnl >= 0 else "negative"}">${p5_pnl:+,.0f}</span> | WR: {p5_wr:.0f}%</div>
                </div>
                <div class="stat-card" style="border-left: 4px solid #e74c3c;">
                    <div class="stat-value">📉 {p6_count}</div>
                    <div class="stat-label">Phase 6: Pre-Trailing</div>
                    <div style="font-size:0.75rem;color:#888;margin-top:5px;">P/L: <span class="{"positive" if p6_pnl >= 0 else "negative"}">${p6_pnl:+,.0f}</span> | WR: {p6_wr:.0f}%</div>
                </div>
                <div class="stat-card" style="border-left: 4px solid #f39c12;">
                    <div class="stat-value">🔄 {p7_count}</div>
                    <div class="stat-label">Phase 7: Trailing</div>
                    <div style="font-size:0.75rem;color:#888;margin-top:5px;">P/L: <span class="{"positive" if p7_pnl >= 0 else "negative"}">${p7_pnl:+,.0f}</span> | WR: {p7_wr:.0f}%</div>
                </div>
                <div class="stat-card" style="border-left: 4px solid #3498db;">
                    <div class="stat-value">📈 {p71_count}</div>
                    <div class="stat-label">Phase 7.1: Trailing Opt</div>
                    <div style="font-size:0.75rem;color:#888;margin-top:5px;">P/L: <span class="{"positive" if p71_pnl >= 0 else "negative"}">${p71_pnl:+,.0f}</span> | WR: {p71_wr:.0f}%</div>
                </div>
                <div class="stat-card" style="border-left: 4px solid #1abc9c;">
                    <div class="stat-value">✨ {p72_count}</div>
                    <div class="stat-label">Phase 7.2: Position Fix</div>
                    <div style="font-size:0.75rem;color:#888;margin-top:5px;">P/L: <span class="{"positive" if p72_pnl >= 0 else "negative"}">${p72_pnl:+,.0f}</span> | WR: {p72_wr:.0f}%</div>
                </div>
            </div>
            
            <!-- Bot Fix Timeline -->
            <div class="section-header">
                <span class="icon">🔧</span>
                <h2>Bot Improvements Timeline</h2>
            </div>
            <div class="chart-container">
                <div class="timeline">
                    {fix_timeline_html}
                </div>
            </div>
            
            <div class="footer">
                <p>Last Updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} UTC</p>
                <p>Strategy: Mean Reversion + Trend Following (BB + RSI) • Timeframe: M15 • Starting Balance: $5,000</p>
            </div>
        </div>
        
        <script>
            // Equity Chart
            const equityData = {json.dumps(equity_points)};
            const ctx = document.getElementById('equityChart').getContext('2d');
            
            // Create gradient
            const gradient = ctx.createLinearGradient(0, 0, 0, 300);
            gradient.addColorStop(0, 'rgba(78, 205, 196, 0.3)');
            gradient.addColorStop(1, 'rgba(78, 205, 196, 0.0)');
            
            new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: equityData.map(p => p.x),
                    datasets: [{{
                        label: 'Equity',
                        data: equityData.map(p => p.y),
                        borderColor: '#4ecdc4',
                        backgroundColor: gradient,
                        fill: true,
                        tension: 0.2,
                        pointRadius: 4,
                        pointBackgroundColor: equityData.map(p => p.pnl >= 0 ? '#4caf50' : '#f44336'),
                        pointBorderColor: '#fff',
                        pointBorderWidth: 1,
                        pointHoverRadius: 6
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {{
                        intersect: false,
                        mode: 'index'
                    }},
                    plugins: {{
                        legend: {{ display: false }},
                        tooltip: {{
                            backgroundColor: 'rgba(0,0,0,0.8)',
                            titleColor: '#4ecdc4',
                            bodyColor: '#fff',
                            borderColor: '#4ecdc4',
                            borderWidth: 1,
                            callbacks: {{
                                label: function(context) {{
                                    const point = equityData[context.dataIndex];
                                    return [
                                        'Equity: $' + point.y.toLocaleString(),
                                        'Trade P/L: $' + (point.pnl >= 0 ? '+' : '') + point.pnl.toFixed(2),
                                        'Phase: ' + point.phase
                                    ];
                                }}
                            }}
                        }}
                    }},
                    scales: {{
                        x: {{ 
                            display: true,
                            title: {{ display: true, text: 'Trade Date', color: '#888' }},
                            grid: {{ color: 'rgba(255,255,255,0.03)' }},
                            ticks: {{ color: '#888', maxRotation: 45 }}
                        }},
                        y: {{ 
                            display: true,
                            title: {{ display: true, text: 'Equity ($)', color: '#888' }},
                            grid: {{ color: 'rgba(255,255,255,0.05)' }},
                            ticks: {{ color: '#888' }}
                        }}
                    }}
                }}
            }});
            
            // Filter functions
            function applyFilters() {{
                const direction = document.getElementById('filterDirection').value;
                const result = document.getElementById('filterResult').value;
                const phase = document.getElementById('filterPhase').value;
                
                const rows = document.querySelectorAll('#tradesTable tbody tr');
                rows.forEach(row => {{
                    let show = true;
                    
                    if (direction !== 'all' && row.dataset.direction !== direction) show = false;
                    if (result === 'winners' && parseFloat(row.dataset.pnl) <= 0) show = false;
                    if (result === 'losers' && parseFloat(row.dataset.pnl) >= 0) show = false;
                    if (phase !== 'all' && !row.dataset.phase.includes(phase)) show = false;
                    
                    row.style.display = show ? '' : 'none';
                }});
            }}
            
            function resetFilters() {{
                document.getElementById('filterDirection').value = 'all';
                document.getElementById('filterResult').value = 'all';
                document.getElementById('filterPhase').value = 'all';
                const rows = document.querySelectorAll('#tradesTable tbody tr');
                rows.forEach(row => row.style.display = '');
            }}
        </script>
    </body>
    </html>
    """

    return html


# Test function for local development
def test_journey_page():
    """Test the journey page locally"""
    from dotenv import load_dotenv

    load_dotenv()

    from oandapyV20 import API
    from oandapyV20.endpoints.trades import TradesList

    # Fetch trades
    api = API(access_token=os.getenv("OANDA_API_KEY"), environment="practice")
    r = TradesList(
        accountID=os.getenv("OANDA_ACCOUNT_ID"),
        params={"instrument": "USD_JPY", "state": "ALL", "count": 100},
    )
    api.request(r)
    trades = [t for t in r.response.get("trades", []) if t.get("state") == "CLOSED"]

    print(f"Found {len(trades)} closed trades")

    # Generate HTML
    html = generate_journey_html(trades)

    # Save to file for preview
    with open("/tmp/journey_preview.html", "w") as f:
        f.write(html)

    print("Preview saved to /tmp/journey_preview.html")
    print("Open this file in your browser to preview the enhanced journey page")

    return html


if __name__ == "__main__":
    test_journey_page()
