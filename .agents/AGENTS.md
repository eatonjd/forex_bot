# Workspace Agent Rules

## User Preferences & Credentials
- **Primary OANDA Live CFD Account (Active):** `001-001-20048243-002` (V20 Primary)
- **OANDA Live MT4 Subaccount (Inactive):** `001-001-20048243-001`
- **OANDA Live Spot Crypto Account (Inactive):** `2721440CPX`
- **Primary OANDA Demo Account (Active):** `101-001-38009813-001` (Primary)
- **OANDA Demo v1 Account (Inactive):** `101-001-38009813-002` (forex_bot_v1)
- **Tradier Options Sandbox Account:** `VA35729986`

## Bot Architectures
- **Forex Bot:** Always-on Cloud Run instance scanning USD/JPY, GBP/USD, and USD/CAD.
- **Options Bot:** Serverless Cloud Run instance triggered daily via Cloud Scheduler at 3:45 PM EST to trade SPY vertical credit spreads.
