# Changelog

All notable changes to the Forex Trading Bot will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2025-12-20

### Added

- **Trade Reasoning System**: Enhanced decision transparency for all trading signals
  - Detailed reasoning for HOLD signals explaining why trades weren't entered
  - Market analysis display (trend, RSI, MACD, volatility)
  - Risk assessment with spread checks and caution warnings
  - Iteration summaries showing active positions and analysis scope
- **Version Management**: Added version tracking with commit info and build dates
- **Health Check Endpoint**: Comprehensive `/health` endpoint for monitoring bot initialization
  - Tracks initialization stages (OANDA, model, position manager, reasoning)
  - Returns HTTP 200 when healthy, 503 when initializing or failed
  - Includes uptime, last iteration timestamp, and error details

### Changed

- Enhanced `ForexDecisionReasoner` to provide detailed HOLD explanations
- Modified `check_symbol()` to generate reasoning for all signals (not just BUY)
- Updated `check_and_manage_position()` with detailed position management logging

### Fixed

- Improved logging clarity with structured output format
- Added flush=True for Cloud Run compatibility

## [1.0.0] - 2025-12-19

### Added

- Initial paper trading bot implementation
- RL model (PPO) integration for trading decisions
- Position Manager with breakeven and trailing stop logic
- OANDA connector for practice account trading
- Support for EUR_USD and GBP_USD pairs
- Risk management (spread checks, position sizing)
- Basic logging and iteration tracking

### Features

- 5-minute trading intervals
- Configurable stop loss (10 pips initial)
- 1000 unit position sizing
- Practice account integration
