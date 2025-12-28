"""
Configuration settings for the Trading Bot.
"""

import os
from datetime import datetime

# Trading Settings
INITIAL_BALANCE = 10000  # Starting cash in USD
TRANSACTION_COST = 0.001  # 0.1% per trade
TRADE_FRACTION = 0.5  # Trade 50% of available cash (more aggressive for daily targets)

# Data Settings
DEFAULT_SYMBOL = "AAPL"
DEFAULT_START_DATE = "2020-01-01"
DEFAULT_END_DATE = datetime.now().strftime("%Y-%m-%d")  # Use today's date!

# Technical Indicator Settings
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_PERIOD = 20
BB_STD = 2

# Training Settings
LEARNING_RATE = 0.0003
BATCH_SIZE = 64
N_STEPS = 2048
GAMMA = 0.99  # Discount factor
GAE_LAMBDA = 0.95  # For PPO
CLIP_RANGE = 0.2  # For PPO
N_EPOCHS = 10  # For PPO
TOTAL_TIMESTEPS = 100000

# Environment Settings
LOOKBACK_WINDOW = 20  # Days of history to include in state
MAX_STEPS_PER_EPISODE = None  # None means use all data

# Evaluation Settings
TEST_SPLIT = 0.2  # 20% of data for testing
VALIDATION_SPLIT = 0.1  # 10% of data for validation

# Paths
MODEL_DIR = "models"
LOG_DIR = "logs"
PLOT_DIR = "plots"

# Reward Shaping
REWARD_SCALING = 1.0
TRANSACTION_PENALTY_MULTIPLIER = 1.0
VOLATILITY_PENALTY = 0.1  # Penalize high-volatility strategies

# Dynamic Position Sizing (from Bot-ForexMT5)
ENABLE_DYNAMIC_LOT_SIZING = True  # Enable risk-based position sizing
RISK_PERCENT_PER_TRADE = (
    2.0  # Risk 2% of balance per trade (more aggressive for daily targets)
)
MIN_LOT_SIZE = 0.01  # Minimum lot size
MAX_LOT_SIZE = 10.0  # Maximum lot size
DEFAULT_PIP_VALUE = 10.0  # Standard pip value for forex pairs

# Multi-Symbol Trading (from Bot-ForexMT5)
ENABLE_MULTI_SYMBOL = False  # Enable multi-symbol trading (Phase 1.2)
RAPID_FIRE_MODE = False  # High-frequency multi-symbol scanning
MAX_TOTAL_POSITIONS = 10  # Maximum total open positions
MAX_POSITIONS_PER_SYMBOL = 3  # Maximum positions per symbol
SYMBOLS_TO_TRADE = ["EURUSD", "GBPUSD", "USDJPY"]  # Symbols for multi-symbol mode
TIMEFRAMES_TO_CHECK = ["M5", "M15", "H1"]  # Timeframes for rapid-fire mode

# ATR-Based Stops (from Bot-ForexMT5)
USE_ATR_STOPS = False  # Enable ATR-based stop loss/take profit (Phase 1.3)
ATR_PERIOD = 14  # Period for ATR calculation
ATR_SL_MULTIPLIER = 1.5  # ATR multiplier for stop loss
ATR_TP_MULTIPLIER = 2.0  # ATR multiplier for take profit

# Advanced Position Management (from Bot-ForexMT5)
AUTO_BREAKEVEN = False  # Auto-move SL to breakeven (Phase 4.1)
BEP_MIN_PROFIT_USD = 0.2  # Minimum profit to trigger breakeven
AUTO_CLOSE_PROFIT = False  # Auto-close at profit target (Phase 4.3)
AUTO_CLOSE_TARGET_USD = 0.5  # Target profit for auto-close
STEP_TRAILING = False  # Step-by-step trailing stops (Phase 4.2)
STEP_LOCK_INIT_USD = 0.3  # Initial profit to start trailing
STEP_SIZE_USD = 0.1  # Step size for trailing

# AI Analysis (from TradingBot_forex)
ENABLE_GEMINI_ANALYSIS = False  # Enable Gemini AI analysis (Phase 2.1)
ENABLE_VISUAL_ANALYSIS = False  # Enable chart image analysis
ENABLE_SMC_ANALYSIS = False  # Smart Money Concepts (Phase 2.2)
ENABLE_WYCKOFF_ANALYSIS = False  # Wyckoff Method (Phase 2.3)

# Multi-Agent RL (from mt5_AI_trading_bot)
ENABLE_MULTI_AGENT = False  # Enable multi-agent RL (Phase 3.2)
MA2C_COOP_GAMMA = 0.9  # Cooperative gamma for MA2C
ENABLE_LSTM_POLICY = False  # Enable LSTM policy (Phase 3.1)

# Telegram Bot Control (from AI-Scalpel-Trading-Bot) - Phase 0
ENABLE_TELEGRAM_BOT = False
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Edge Positioning (from AI-Scalpel-Trading-Bot) - Phase 1.2
ENABLE_EDGE_POSITIONING = False  # Enable after testing
EDGE_CAPITAL_PERCENTAGE = 0.5  # Use 50% of capital for Edge
EDGE_ALLOWED_RISK = 0.01  # Risk 1% per trade
EDGE_MIN_WINRATE = 0.60  # Filter pairs < 60% winrate
EDGE_MIN_EXPECTANCY = 0.20  # Filter pairs < 0.20 expectancy
EDGE_MIN_TRADE_NUMBER = 10  # Minimum trades for statistics
EDGE_STOPLOSS_RANGE_MIN = -0.01  # -1% minimum stoploss
EDGE_STOPLOSS_RANGE_MAX = -0.10  # -10% maximum stoploss
EDGE_STOPLOSS_RANGE_STEP = -0.01  # Test in 1% increments
EDGE_MAX_TRADE_DURATION = 1440  # Max 1 day (1440 minutes)

# Multi-Symbol Configuration (Phase 1.3)
ENABLE_MULTI_SYMBOL_TRADING = False  # Enable multi-symbol trading
SYMBOLS_TO_TRADE = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "EURJPY"]
TIMEFRAMES_TO_ANALYZE = ["M5", "M15", "H1"]  # Multiple timeframes
MULTI_SYMBOL_MAX_WORKERS = 4  # Parallel analysis workers

# ATR-Based Stops (Phase 1.4)
USE_ATR_STOPS = False  # Enable ATR-based dynamic stops
ATR_PERIOD = 14  # Period for ATR calculation
ATR_SL_MULTIPLIER = 2.0  # Stop loss = ATR × multiplier
ATR_TP_MULTIPLIER = 3.0  # Take profit = ATR × multiplier (RR ratio)
ATR_MIN_SL_PIPS = 10.0  # Minimum SL distance in pips
ATR_MAX_SL_PIPS = 100.0  # Maximum SL distance in pips

# Hyperopt Configuration (Phase 2.1)
ENABLE_HYPEROPT = False  # Enable parameter optimization
HYPEROPT_EPOCHS = 50  # Number of optimization iterations
HYPEROPT_N_JOBS = 4  # Parallel workers for optimization
HYPEROPT_OBJECTIVE = "sharpe"  # Loss function: sharpe, sortino, calmar, custom
HYPEROPT_SEARCH_SPACE = "rl"  # What to optimize: rl, indicators, risk, edge, all
HYPEROPT_SAVE_PATH = "experiments/hyperopt_results/"

# LLM Provider Selection
# Options: "none" (disabled), "ollama" (local), "gemini" (cloud API)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "none")

# Ollama Configuration (Local LLM)
OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL", "llama3.2"
)  # Best for Intel Mac (17s, 83% quality)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_TIMEOUT = 30  # Seconds per request
OLLAMA_TEMPERATURE = 0.7  # 0.0-2.0, lower = more deterministic

# Gemini AI Analysis (Cloud API)
ENABLE_GEMINI_ANALYSIS = LLM_PROVIDER == "gemini"  # Auto-set based on provider
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash"  # or 'gemini-2.0-pro'
GEMINI_TEMPERATURE = 0.7  # 0.0-2.0, lower = more deterministic
GEMINI_USE_IN_SCANNER = False  # Integrate with multi-symbol scanner
GEMINI_RATE_LIMIT_SECONDS = 3600  # Minimum seconds between calls per symbol
GEMINI_REQUIRE_CONFIRMATION = False  # Only trade when LLM agrees with RL model
GEMINI_MIN_CONFIDENCE = 60  # Minimum LLM confidence % to confirm a trade

# Shared LLM Settings (apply to both Ollama and Gemini)
LLM_RATE_LIMIT_SECONDS = int(os.getenv("LLM_RATE_LIMIT_SECONDS", "3600"))
LLM_REQUIRE_CONFIRMATION = (
    os.getenv("LLM_REQUIRE_CONFIRMATION", "false").lower() == "true"
)
LLM_MIN_CONFIDENCE = int(os.getenv("LLM_MIN_CONFIDENCE", "60"))


# Position Management (Phase 4)
ENABLE_POSITION_MANAGEMENT = True  # Enable breakeven, trailing, auto-close
# Breakeven
ENABLE_BREAKEVEN = True
BREAKEVEN_PIPS = 20.0  # Move to breakeven after X pips profit
BREAKEVEN_OFFSET = 5.0  # Lock in X pips of profit at breakeven
# Trailing Stop
ENABLE_TRAILING_STOP = True
TRAILING_START_PIPS = 30.0  # Start trailing after X pips profit
TRAILING_STEP_PIPS = 10.0  # Move SL in steps of X pips
TRAILING_DISTANCE_PIPS = 15.0  # Maintain X pips distance from price
# Auto-Close
ENABLE_AUTO_CLOSE = True  # Auto-close at daily profit target
AUTO_CLOSE_PROFIT_USD = 100.0  # Close position at $X profit
