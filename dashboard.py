"""
Forex Trading Bot - Streamlit Dashboard

Real-time monitoring and control interface for the forex trading bot.

Features:
- Live status and metrics
- Active positions with P&L
- Performance charts
- Pair scanner results
- Manual controls
- Logs viewer

Run: streamlit run dashboard.py
"""

import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
import time
import plotly.graph_objects as go
from pathlib import Path

# Page config
st.set_page_config(
    page_title="Forex Bot Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown(
    """
<style>
    .big-metric {
        font-size: 2rem;
        font-weight: bold;
    }
    .status-running {
        color: #00ff00;
    }
    .status-stopped {
        color: #ff0000;
    }
    .profit {
        color: #00ff00;
    }
    .loss {
        color: #ff0000;
    }
</style>
""",
    unsafe_allow_html=True,
)

# Initialize session state
if "auto_refresh" not in st.session_state:
    st.session_state.auto_refresh = True


def load_bot_status():
    """Load bot status from Cloud Storage or local file"""
    use_cloud = os.getenv("USE_CLOUD_STORAGE", "false").lower() == "true"
    bucket_name = os.getenv("GCS_BUCKET_NAME", "forex-bot-state")

    # Try Cloud Storage first if enabled
    if use_cloud:
        try:
            from google.cloud import storage

            client = storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob("bot_state.json")
            data = blob.download_as_string()
            return json.loads(data)
        except Exception as e:
            st.warning(f"Cloud Storage read failed, using local fallback: {e}")

    # Fallback to local file
    status_file = Path("bot_state.json")
    if status_file.exists():
        with open(status_file, "r") as f:
            return json.load(f)

    # Return default if nothing works
    return {
        "version": "1.1.0",
        "status": "Unknown",
        "iteration": 0,
        "last_update": datetime.now().isoformat(),
        "positions": [],
        "total_pnl_pips": 0.0,
        "total_pnl_usd": 0.0,
        "trades": 0,
        "wins": 0,
        "losses": 0,
    }


def load_performance_data():
    """Load performance tracker data"""
    reports_dir = Path("reports")
    if reports_dir.exists():
        # Load latest daily summary
        summaries = list(reports_dir.glob("daily_summary_*.txt"))
        if summaries:
            latest = max(summaries, key=os.path.getctime)
            with open(latest, "r") as f:
                return f.read()
    return "No performance data available yet."


def load_pair_scanner_results():
    """Load latest pair scanner results"""
    scanner_file = Path("pair_scanner_results.json")
    if scanner_file.exists():
        with open(scanner_file, "r") as f:
            return json.load(f)
    return None


# Header
st.title("🤖 Forex Trading Bot Dashboard")

# Sidebar
with st.sidebar:
    st.header("⚙️ Controls")

    # Auto-refresh toggle
    auto_refresh = st.toggle("Auto-refresh (30s)", value=st.session_state.auto_refresh)
    st.session_state.auto_refresh = auto_refresh

    st.divider()

    # Bot controls
    st.subheader("Bot Controls")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("▶️ Start", use_container_width=True):
            st.info("Start bot via terminal: `python paper_trading_bot.py`")
    with col2:
        if st.button("⏹️ Stop", use_container_width=True):
            st.warning("Stop bot with Ctrl+C in terminal")

    st.divider()

    # Pair scanner controls
    st.subheader("Pair Scanner")
    if st.button("🔍 Trigger Scan", use_container_width=True):
        st.info("Pair scan will trigger automatically after 24 iterations without buy")

    st.divider()

    # Summary controls
    st.subheader("Reports")
    if st.button("📊 Generate Summary", use_container_width=True):
        st.info("Daily summaries generated at midnight, Weekly on Friday")

    st.divider()
    st.caption(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")

# Load data
bot_status = load_bot_status()

# Top metrics row
col1, col2, col3, col4 = st.columns(4)

with col1:
    status_color = "🟢" if bot_status["status"] == "Running" else "🔴"
    st.metric(
        "Status", f"{status_color} {bot_status['status']}", f"v{bot_status['version']}"
    )

with col2:
    st.metric("Iteration", f"#{bot_status['iteration']}", None)

with col3:
    pnl_pips = bot_status.get("total_pnl_pips", 0.0)
    pnl_color = "🟢" if pnl_pips >= 0 else "🔴"
    st.metric(
        "Total P&L",
        f"{pnl_color} {pnl_pips:+.1f} pips",
        f"${bot_status.get('total_pnl_usd', 0.0):+.2f}",
    )

with col4:
    total_trades = bot_status.get("wins", 0) + bot_status.get("losses", 0)
    win_rate = (
        (bot_status.get("wins", 0) / total_trades * 100) if total_trades > 0 else 0
    )
    st.metric(
        "Win Rate",
        f"{win_rate:.1f}%",
        f"{bot_status.get('wins', 0)}W / {bot_status.get('losses', 0)}L",
    )

st.divider()

# Main content area
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["📊 Overview", "📍 Positions", "📈 Performance", "🔍 Pair Scanner", "📋 Logs"]
)

with tab1:
    st.subheader("Trading Overview")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Current Status")
        st.json(
            {
                "Version": bot_status.get("version", "1.1.0"),
                "Status": bot_status.get("status", "Unknown"),
                "Iteration": bot_status.get("iteration", 0),
                "Active Positions": len(bot_status.get("positions", [])),
                "Current Symbols": bot_status.get("symbols", ["EUR_USD", "GBP_USD"]),
            }
        )

    with col2:
        st.markdown("### Performance Summary")
        st.json(
            {
                "Total Trades": bot_status.get("trades", 0),
                "Wins": bot_status.get("wins", 0),
                "Losses": bot_status.get("losses", 0),
                "Total P&L (pips)": round(bot_status.get("total_pnl_pips", 0.0), 2),
                "Total P&L (USD)": round(bot_status.get("total_pnl_usd", 0.0), 2),
            }
        )

    # HOLD reasons chart
    st.markdown("### Reasons for Not Trading")
    hold_reasons = bot_status.get("hold_reasons", {})

    if hold_reasons and len(hold_reasons) > 0:
        # Show as table (always works)
        import pandas as pd

        df_reasons = pd.DataFrame(
            [
                {
                    "Reason": reason,
                    "Count": count,
                    "Percentage": f"{count / sum(hold_reasons.values()) * 100:.1f}%",
                }
                for reason, count in sorted(
                    hold_reasons.items(), key=lambda x: x[1], reverse=True
                )
            ]
        )
        st.dataframe(df_reasons, use_container_width=True, hide_index=True)

        # Also try pie chart
        fig = go.Figure(
            data=[
                go.Pie(
                    labels=list(hold_reasons.keys()),
                    values=list(hold_reasons.values()),
                    hole=0.3,
                )
            ]
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No HOLD signals recorded yet. Bot will track reasons for not trading.")

with tab2:
    st.subheader("Active Positions")

    positions = bot_status.get("positions", [])

    if positions:
        df = pd.DataFrame(positions)
        st.dataframe(
            df,
            use_container_width=True,
            column_config={
                "symbol": "Symbol",
                "entry": st.column_config.NumberColumn("Entry", format="%.5f"),
                "current": st.column_config.NumberColumn("Current", format="%.5f"),
                "pnl_pips": st.column_config.NumberColumn("P&L (pips)", format="%.1f"),
                "pnl_usd": st.column_config.NumberColumn("P&L (USD)", format="$%.2f"),
            },
        )
    else:
        st.info("No active positions")

with tab3:
    st.subheader("Performance Charts")

    # P&L over time (mock data for now)
    st.markdown("### Cumulative P&L")

    # Mock data - in real implementation, load from tracker
    dates = pd.date_range(start="2025-12-19", periods=20, freq="5min")
    pnl = [0]
    for i in range(19):
        pnl.append(pnl[-1] + (5 if i % 3 == 0 else -2))

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=pnl,
            mode="lines",
            name="P&L (pips)",
            line=dict(color="#00ff00" if pnl[-1] > 0 else "#ff0000", width=2),
        )
    )
    fig.update_layout(
        xaxis_title="Time", yaxis_title="P&L (pips)", height=400, hovermode="x unified"
    )
    st.plotly_chart(fig, use_container_width=True)

    # Performance summary text
    st.markdown("### Latest Daily Summary")
    perf_data = load_performance_data()
    st.text(perf_data)

with tab4:
    st.subheader("Pair Scanner Results")

    scanner_results = load_pair_scanner_results()

    if scanner_results:
        st.success(f"Last scan: {scanner_results.get('timestamp', 'Unknown')}")

        pairs = scanner_results.get("pairs", [])
        if pairs:
            df = pd.DataFrame(pairs)
            st.dataframe(
                df,
                use_container_width=True,
                column_config={
                    "symbol": "Symbol",
                    "score": st.column_config.ProgressColumn(
                        "Score",
                        format="%.1f/10",
                        min_value=0,
                        max_value=10,
                    ),
                    "spread": st.column_config.NumberColumn(
                        "Spread (pips)", format="%.1f"
                    ),
                    "trend": "Trend",
                },
            )
        else:
            st.info("No pairs scanned yet")
    else:
        st.info(
            "Pair scanner hasn't run yet. Will trigger after 24 iterations without buy."
        )

with tab5:
    st.subheader("Bot Decision Output")

    st.markdown("""This shows the actual reasoning from the bot for each trading decision.  
    You'll see why trades are being held (neutral market, wide spread, etc.)""")

    # Read recent bot output from state
    recent_decisions_file = Path("recent_decisions.log")
    if recent_decisions_file.exists():
        with open(recent_decisions_file, "r") as f:
            recent_output = f.read()
        st.text_area("Recent Bot Decisions (Last 10)", value=recent_output, height=500)
    else:
        st.info("Bot decision output will appear here once trading starts.")

    st.divider()

    st.subheader("Why isn't the bot trading?")

    hold_reasons = bot_status.get("hold_reasons", {})
    if hold_reasons:
        st.markdown("**Current HOLD Reasons:**")
        for reason, count in hold_reasons.items():
            st.markdown(f"- **{reason}**: {count} times")

        st.markdown("""  
        **Common Reasons Explained:**
        - **Neutral market**: No clear trend direction (price near SMAs, indecisive indicators)
        - **Wide spread**: Spread > 3.0 pips makes entry/exit costs too high
        - **Low confidence**: RL model prediction confidence below threshold
        - **Weak signal**: Technical indicators not aligned for clear buy/sell
        
        **Example**: AUD/USD showing 0.1 pip spread (excellent!) but score 7.35/10 because:
        - Trend: Neutral (not bullish or bearish)
        - RL Model probably giving HOLD signal
        - Even with low spread, no clear trading opportunity
        """)
    else:
        st.info("No HOLD reasons tracked yet - bot may not have run iterations.")

# Auto-refresh
if st.session_state.auto_refresh:
    time.sleep(30)
    st.rerun()
