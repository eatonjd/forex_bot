# 🤖 Multi-Symbol Regime Trading Bot

An automated multi-pair forex trading bot running on Google Cloud Run that dynamically switches between **Volatility Breakout**, **Mean Reversion**, and **Range Trading** strategies based on real-time market regimes.

---

## 📊 Strategy & Regime Overview

The bot supports **USD/JPY**, **GBP/USD**, and **USD/CAD** concurrently on the **M15 timeframe**. It continuously analyzes market structure to classify the environment and apply the optimal strategy:

| Regime | Indicator Conditions | Strategy Applied | Exit Mechanism |
| :--- | :--- | :--- | :--- |
| **BREAKOUT** | ATR expanding (> 1.5× avg), ADX > 25 | **Volatility Breakout** (Trade with the trend) | Trailing Stop (15% giveback) |
| **MEAN_REVERSION** | ATR quiet, ADX < 25, RSI overbought/oversold | **Mean Reversion** (Trade counter-trend) | Trailing Stop (USD-based) |
| **MEAN_REVERSION (Fallback)** | ATR quiet, ADX < 20, BB in HOLD | **Range Trading** (Buy/Sell channel bounces) | Fixed Take Profit at opposite boundary |
| **TRANSITIONAL** | Changing dynamics | **No entries** (Cooldown phase) | N/A |

### 🛠️ Sub-Strategies
1. **Volatility Breakout:** Triggers buy/sell orders when price breaks out of the Donchian channel during high-volume ATR expansions.
2. **Mean Reversion:** Enters buy/sell orders on Bollinger Band boundaries with RSI filters (<30 / >70).
3. **Range Trading:** Maps local extrema over a 20-candle lookback to establish horizontal support/resistance boundaries, buying support bounces and selling resistance bounces.

---

## 🛡️ Risk Management & Safety Caps

* **Margin Safety Cap:** Restricts total margin used across all open positions to a maximum of **50% of the account Net Asset Value (NAV)**.
* **Stop Loss Cap:** Dynamically caps maximum stop-loss distances to **40 pips** to prevent excessive risk on highly volatile breakouts.
* **Daily Loss Limit:** Closes all positions and halts trading for the day if realized or unrealized losses exceed **-$200**.
* **Risk Per Position:** Automatically sizes units to risk exactly **2%** of account balance based on the stop-loss distance.

---

## ⏱️ Dynamic 1-Minute Exit Monitoring

To protect profits and exit trades with high resolution, the bot runs on a **1-minute execution frequency**:
* **Active Position:** The bot runs every minute to evaluate trailing stops, time stops, and target exits with high resolution.
* **Flat State:** If no positions are active, the bot throttles execution and skips candle scans unless it is on a 15-minute boundary (`minute % 15 == 0`), conserving API resources.

---

## 🏗️ Deployment

The bot runs on **Google Cloud Run** triggered by **Google Cloud Scheduler** crons.

### Useful CLI Commands

```bash
# Deploy code updates to Cloud Run
gcloud run deploy forex-bot-live --source . --region us-central1 --project big-e-trading-bot --quiet

# View live execution logs
gcloud run services logs tail forex-bot-live --region us-central1 --project big-e-trading-bot

# Run a local paper trading dry-run once
python3 -c "from usdjpy_regime_bot import USDJPYRegimeBot; USDJPYRegimeBot(mode='paper').run_once()"
```

---

## 📱 Notifications & Alerts

Real-time alert integrations dispatch notifications for:
* **Trade Entries & Exits:** Direction, units, entry price, and current profit/loss.
* **OANDA Order Rejections:** Instant alerts with specific cancellation/rejection reasons (e.g. insufficient margin).
* **Execution Exceptions:** Network errors, timeouts, or broker connection failures.
* **Channels Supported:** Telegram, ntfy.sh, and SMS.

---

## 📁 Project Structure

```
forex_bot/
├── usdjpy_regime_bot.py   # Main multi-symbol regime trading bot
├── cloud_run_server.py    # Cloud Run server wrapper
├── command_center.py      # Streamlit/CLI dashboard & control panel
├── utils/
│   ├── regime_detector.py # Regime classification (ATR, ADX, SMA)
│   ├── range_trading.py   # Range strategy (extrema, support/resistance)
│   ├── notifications.py   # Telegram, ntfy, SMS notifications
│   └── oanda_api.py       # V20 broker interface wrapper
└── deploy_gcloud.sh       # Deploy script
```

---

*Built with Python, OANDA v20 API, and deployed on Google Cloud Run*
