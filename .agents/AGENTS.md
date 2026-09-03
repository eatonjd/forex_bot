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
