# 🤖 USD/JPY Mean Reversion Trading Bot

An automated forex trading bot running on Google Cloud that trades USD/JPY using a mean reversion strategy with Bollinger Bands and RSI indicators.

## 📊 Strategy Overview

| Component | Details |
|-----------|---------|
| **Pair** | USD/JPY |
| **Timeframe** | M15 (15 minutes) |
| **Indicators** | Bollinger Bands (20, 2σ) + RSI (14) |
| **Backtest Return** | +957% over 60 days |
| **Win Rate** | 63.5% |

### Entry Signals

- **BUY** → RSI < 30 (oversold) + price touching lower Bollinger Band
- **SELL** → RSI > 70 (overbought) + price touching upper Bollinger Band

---

## 💰 Risk Management

### Trailing Profit Stop

Instead of taking profit at a fixed level, the bot uses a trailing stop:

1. **Activation**: When unrealized profit reaches **$100**
2. **Tracking**: Records peak profit as it rises
3. **Exit**: Closes position when profit drops **$50** from peak

This allows profits to run during strong moves while protecting gains.

### Pyramiding (Scaling In)

The bot adds to winning positions:

| Parameter | Value |
|-----------|-------|
| Max additions | 3 |
| Minimum profit to add | $25 |
| Addition size | 50% of initial |

**Example progression:**

```
Initial position: 50,000 units
At +$25 profit: Add 25,000 units ← Scale-in #1
At +$50 profit: Add 25,000 units ← Scale-in #2
At +$75 profit: Add 25,000 units ← Scale-in #3
─────────────────────────────────────────────
Maximum position: 125,000 units (2.5x leverage)
```

### Safety Limits

- **Daily loss limit**: -$200 (stops trading for the day)
- **Risk per trade**: 2% of account balance

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Google Cloud Run                    │
│  ┌───────────────────────────────────────────────┐  │
│  │           USD/JPY Mean Reversion Bot          │  │
│  │                                               │  │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────────┐   │  │
│  │  │  OANDA  │  │   RSI   │  │  Bollinger  │   │  │
│  │  │   API   │  │ < 30/>70│  │    Bands    │   │  │
│  │  └────┬────┘  └────┬────┘  └──────┬──────┘   │  │
│  │       │            │              │          │  │
│  │       v            v              v          │  │
│  │  ┌──────────────────────────────────────┐    │  │
│  │  │         Signal Generator             │    │  │
│  │  │    (Buy/Sell/Hold Decision)          │    │  │
│  │  └───────────────┬──────────────────────┘    │  │
│  │                  │                          │  │
│  │                  v                          │  │
│  │  ┌──────────────────────────────────────┐    │  │
│  │  │      Position Management             │    │  │
│  │  │  • Trailing Stop ($100 → $50 trail)  │    │  │
│  │  │  • Pyramiding (up to 3 scale-ins)    │    │  │
│  │  └───────────────┬──────────────────────┘    │  │
│  │                  │                          │  │
│  │                  v                          │  │
│  │  ┌──────────────────────────────────────┐    │  │
│  │  │         Notifications                │    │  │
│  │  │    (Telegram, ntfy.sh, SMS)          │    │  │
│  │  └──────────────────────────────────────┘    │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## 📈 Performance

### Backtest Results (6-Month Historical Data)

| Strategy | Pair | Timeframe | Return | Trades | Win Rate |
|----------|------|-----------|--------|--------|----------|
| Mean Reversion | USD/JPY | M15 | **+957%** | 85 | 63.5% |
| SMC | USD/JPY | H1 | +104% | 29 | 34.5% |
| Buy & Hold | USD/JPY | — | -0.3% | — | — |
| Random | EUR/USD | H1 | +17% | 180 | 50% |

---

## 🔧 Configuration

```python
# Strategy Parameters
bb_period = 20          # Bollinger Band period
bb_std = 2.0            # Standard deviations
rsi_period = 14         # RSI lookback
rsi_oversold = 30       # Buy threshold
rsi_overbought = 70     # Sell threshold

# Risk Management
risk_percent = 0.02     # 2% per trade
daily_target = 100      # Trailing stop activation
trailing_amount = 50    # Trail distance
max_daily_loss = -200   # Stop trading limit

# Pyramiding
max_scale_ins = 3       # Maximum additions
min_profit_to_add = 25  # Required profit to add
scale_in_size_pct = 0.5 # 50% of initial size
```

---

## 🚀 Deployment

The bot runs on **Google Cloud Run** with:

- Automatic scaling
- 24/7 operation
- Health monitoring
- Cost-efficient (scales to zero when idle)

### Commands

```bash
# View live logs
gcloud run services logs tail forex-trading-bot --region us-central1

# Health check
curl https://forex-trading-bot-489986279698.us-central1.run.app/health

# Local testing
python3 usdjpy_mean_reversion.py --mode paper --once
```

---

## 📱 Notifications

The bot sends real-time alerts via:

- **Telegram** — Trade entries, exits, profit targets
- **ntfy.sh** — Push notifications (no account required)
- **SMS** — Critical alerts (optional)

---

## ⚠️ Disclaimer

This bot is for educational purposes and paper trading. Past performance does not guarantee future results. Trading forex involves significant risk of loss. Always use proper risk management and never trade with money you can't afford to lose.

---

## 📁 Project Structure

```
forex_bot/
├── usdjpy_mean_reversion.py  # Main trading bot
├── cloud_run_server.py       # Cloud Run entry point
├── config.py                 # Configuration
├── utils/
│   ├── mean_reversion.py     # Strategy logic
│   ├── notifications.py      # Alert system
│   └── oanda_api.py          # Broker integration
└── deploy_gcloud.sh          # Deployment script
```

---

*Built with Python, OANDA API, and deployed on Google Cloud Run*
