# Workspace Agent Rules

## User Preferences & Credentials
- **Primary OANDA Live CFD Account (Active):** `001-001-20048243-002` (V20 Primary)
- **Primary OANDA Demo Account (Active):** `101-001-38009813-001` (Primary)
- **Tradier Options Sandbox Account:** `VA35729986`

## Inactive Accounts (Ignore)
- OANDA Live MT4 Subaccount: `001-001-20048243-001`
- OANDA Live Spot Crypto Account: `2721440CPX`
- OANDA Demo v1 Account: `101-001-38009813-002`

## Bot Architectures & Endpoints
- **Forex Bot:** Serverless Cloud Run instance with request-based CPU throttling, triggered every minute via Cloud Scheduler scanning active roster (`USD_CAD`, `EUR_USD`, `AUD_USD`).
  - Webpage: `https://forex-bot-live-489986279698.us-central1.run.app/`
- **Options Bot:** Serverless Cloud Run instance triggered daily via Cloud Scheduler at 3:45 PM EST to trade 18-asset weekly credit spreads / Iron Condors with 50% profit-taking auto-exit.
  - Webpage: `https://options-regime-bot-489986279698.us-central1.run.app/`
- **Crypto Bot:** Serverless Cloud Run instance triggered every 5 minutes via Cloud Scheduler scanning `BTC-USD`, `ETH-USD`, `SOL-USD` with 1.5x ATR hard SL and 25% peak giveback trailing stop.
  - Webpage: `https://crypto-bot-489986279698.us-central1.run.app/`
  - Journey Dashboard: `https://crypto-bot-489986279698.us-central1.run.app/journey`
  - AI Trade Reviews: Automated Gemini 3.6 Flash post-trade analysis triggered daily at 8:00 PM EST (`crypto-trade-review-job`) and via `POST /trade-review`.

## Mandatory Architecture & Risk Safety Rules
- **Broker Ledger as Single Source of Truth:** Never rely on in-memory trade variables (`self.daily_pnl += pnl`) for trade accounting. Always reconcile position state, realized daily P/L, and trade closures directly from the broker's API ledger on every run cycle.
- **Serverless Out-of-Band State Awareness:** Assume broker-side Stop Loss, Take Profit, and liquidation fills happen while the container is idle or asleep. When a position goes flat, query the broker's closed trades endpoint to capture the real exit price, timestamp, and realized P/L before resetting state.
- **Circuit Breakers & Cooldowns:** Every bot must enforce an inviolable daily loss limit from the broker's realized P/L, a minimum 2-hour instrument cooldown after any stopped-out trade, and a consecutive loss circuit breaker (e.g. 3 consecutive losses pauses trading).
- **Hard Notional & Unit Ceilings:** Percentage-based sizing formulas (e.g. 0.75% or 1.0% of NAV) must ALWAYS have a hard ceiling on total units / notional exposure (e.g., max 20,000 units on Forex) so unexpected balance spikes do not cause outsized leverage.
- **Adversarial Code Review Standard:** Never stop at checking indicator math. Audit for out-of-band broker mutations, state leakage on container restarts, and broker-sync blind spots.
