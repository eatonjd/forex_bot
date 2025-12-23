#!/usr/bin/env python3
"""
Telegram Bot Controller for Forex Trading Bot

Remote control and monitoring via Telegram messaging.
Based on Freqtrade's Telegram implementation from AI-Scalpel-Trading-Bot.

Features:
- /status - View open positions
- /profit - Show P&L summary
- /balance - Display account balance
- /performance - Trading statistics
- /stop - Emergency stop (close all positions)
- /start - Resume trading
- /help - Command list

Author: Forex Bot Team
Created: 2025-12-18
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import os

# Telegram imports with graceful fallback
try:
    from telegram import Update, Bot
    from telegram.ext import Updater, CommandHandler, CallbackContext

    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logging.warning("python-telegram-bot not installed. Telegram features disabled.")

logger = logging.getLogger(__name__)


class TelegramBotController:
    """
    Remote control trading bot via Telegram.

    Provides real-time monitoring and emergency controls through
    Telegram messaging interface.
    """

    def __init__(
        self,
        token: str,
        chat_id: str,
        trading_bot_instance: Optional[Any] = None,
        enabled: bool = True,
    ):
        """
        Initialize Telegram bot controller.

        Args:
            token: Telegram bot token from @BotFather
            chat_id: Your Telegram chat ID
            trading_bot_instance: Reference to the trading bot
            enabled: Enable/disable telegram functionality
        """
        if not TELEGRAM_AVAILABLE:
            logger.error(
                "Telegram library not available. Please install python-telegram-bot"
            )
            self.enabled = False
            return

        if not enabled:
            logger.info("Telegram bot disabled in configuration")
            self.enabled = False
            return

        if not token or not chat_id:
            logger.error("Telegram token or chat_id not provided")
            self.enabled = False
            return

        self.token = token
        self.chat_id = chat_id
        self.trading_bot = trading_bot_instance
        self.enabled = True

        # Initialize bot and updater
        try:
            self.bot = Bot(token=token)
            self.updater = Updater(token=token, use_context=True)
            self._setup_handlers()
            logger.info("✅ Telegram bot initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Telegram bot: {e}")
            self.enabled = False

    def _setup_handlers(self):
        """Register command handlers"""
        if not self.enabled:
            return

        dp = self.updater.dispatcher

        # Register commands
        dp.add_handler(CommandHandler("start", self.cmd_start))
        dp.add_handler(CommandHandler("stop", self.cmd_stop))
        dp.add_handler(CommandHandler("status", self.cmd_status))
        dp.add_handler(CommandHandler("profit", self.cmd_profit))
        dp.add_handler(CommandHandler("balance", self.cmd_balance))
        dp.add_handler(CommandHandler("performance", self.cmd_performance))
        dp.add_handler(CommandHandler("help", self.cmd_help))

        logger.info("Telegram command handlers registered")

    def cmd_start(self, update: Update, context: CallbackContext):
        """Start/resume trading"""
        try:
            if self.trading_bot and hasattr(self.trading_bot, "resume_trading"):
                self.trading_bot.resume_trading()
                msg = "✅ *Trading Resumed*\n\nBot is now actively trading."
            else:
                msg = "⚠️ Trading bot instance not connected"

            self._send_message(msg)
            logger.info("Trading resumed via Telegram")
        except Exception as e:
            self._send_message(f"❌ Error: {str(e)}")
            logger.error(f"Error in cmd_start: {e}")

    def cmd_stop(self, update: Update, context: CallbackContext):
        """Emergency stop - halt all trading"""
        try:
            if self.trading_bot and hasattr(self.trading_bot, "stop_trading"):
                self.trading_bot.stop_trading()
                msg = "🛑 *EMERGENCY STOP ACTIVATED*\n\nAll trading halted.\nPositions remain open.\nUse /status to monitor."
            else:
                msg = "⚠️ Trading bot instance not connected"

            self._send_message(msg)
            logger.warning("⚠️ EMERGENCY STOP triggered via Telegram")
        except Exception as e:
            self._send_message(f"❌ Error: {str(e)}")
            logger.error(f"Error in cmd_stop: {e}")

    def cmd_status(self, update: Update, context: CallbackContext):
        """Show current open positions"""
        try:
            if not self.trading_bot:
                self._send_message("⚠️ Trading bot instance not connected")
                return

            positions = self._get_open_positions()

            if not positions:
                msg = "📊 *Position Status*\n\n✅ No open positions"
            else:
                msg = "📊 *Open Positions*\n\n"
                total_pnl = 0

                for i, pos in enumerate(positions, 1):
                    symbol = pos.get("symbol", "Unknown")
                    pnl = pos.get("unrealized_pnl", 0)
                    pnl_pct = pos.get("pnl_percent", 0)
                    entry = pos.get("entry_price", 0)
                    current = pos.get("current_price", 0)
                    size = pos.get("quantity", 0)

                    emoji = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"

                    msg += f"{emoji} *{symbol}*\n"
                    msg += f"   Entry: ${entry:.4f} | Now: ${current:.4f}\n"
                    msg += f"   Size: {size} | P&L: ${pnl:+.2f} ({pnl_pct:+.2f}%)\n\n"

                    total_pnl += pnl

                msg += f"💰 *Total Unrealized P&L: ${total_pnl:+.2f}*"

            self._send_message(msg)
        except Exception as e:
            self._send_message(f"❌ Error fetching status: {str(e)}")
            logger.error(f"Error in cmd_status: {e}")

    def cmd_profit(self, update: Update, context: CallbackContext):
        """Show profit/loss summary"""
        try:
            if not self.trading_bot:
                self._send_message("⚠️ Trading bot instance not connected")
                return

            stats = self._get_statistics()

            msg = f"""
💰 *Profit/Loss Summary*

📅 *Today*
   P&L: ${stats.get("daily_pnl", 0):+,.2f}
   Trades: {stats.get("daily_trades", 0)}

📆 *This Week*
   P&L: ${stats.get("weekly_pnl", 0):+,.2f}
   Trades: {stats.get("weekly_trades", 0)}

📊 *All Time*
   Total P&L: ${stats.get("total_pnl", 0):+,.2f}
   Win Rate: {stats.get("win_rate", 0):.1f}%
   Profit Factor: {stats.get("profit_factor", 0):.2f}
   Sharpe Ratio: {stats.get("sharpe_ratio", 0):.2f}
   
🎯 *Best Trade: ${stats.get("best_trade", 0):+,.2f}*
📉 *Worst Trade: ${stats.get("worst_trade", 0):+,.2f}*
            """

            self._send_message(msg)
        except Exception as e:
            self._send_message(f"❌ Error fetching profit data: {str(e)}")
            logger.error(f"Error in cmd_profit: {e}")

    def cmd_balance(self, update: Update, context: CallbackContext):
        """Show account balance"""
        try:
            if not self.trading_bot:
                self._send_message("⚠️ Trading bot instance not connected")
                return

            balance_info = self._get_balance()

            msg = f"""
💳 *Account Balance*

💵 Total Equity: ${balance_info.get("equity", 0):,.2f}
💰 Cash: ${balance_info.get("cash", 0):,.2f}
📊 Positions Value: ${balance_info.get("positions_value", 0):,.2f}
🔒 Margin Used: ${balance_info.get("margin_used", 0):,.2f}
✅ Buying Power: ${balance_info.get("buying_power", 0):,.2f}

📈 Day Change: ${balance_info.get("day_change", 0):+,.2f} ({balance_info.get("day_change_pct", 0):+.2f}%)
            """

            self._send_message(msg)
        except Exception as e:
            self._send_message(f"❌ Error fetching balance: {str(e)}")
            logger.error(f"Error in cmd_balance: {e}")

    def cmd_performance(self, update: Update, context: CallbackContext):
        """Show performance statistics"""
        try:
            if not self.trading_bot:
                self._send_message("⚠️ Trading bot instance not connected")
                return

            perf = self._get_performance()

            msg = f"""
📊 *Performance Metrics*

🎯 *Risk Metrics*
   Max Drawdown: {perf.get("max_drawdown", 0):.2f}%
   Volatility: {perf.get("volatility", 0):.2f}%
   Sharpe Ratio: {perf.get("sharpe", 0):.2f}
   Sortino Ratio: {perf.get("sortino", 0):.2f}

📈 *Trading Stats*
   Total Trades: {perf.get("total_trades", 0)}
   Win Rate: {perf.get("win_rate", 0):.1f}%
   Avg Win: ${perf.get("avg_win", 0):.2f}
   Avg Loss: ${perf.get("avg_loss", 0):.2f}
   Profit Factor: {perf.get("profit_factor", 0):.2f}

⏱️ *Timing*
   Avg Trade Duration: {perf.get("avg_duration", 0):.1f} min
   Avg Win Duration: {perf.get("avg_win_duration", 0):.1f} min
   Avg Loss Duration: {perf.get("avg_loss_duration", 0):.1f} min
            """

            self._send_message(msg)
        except Exception as e:
            self._send_message(f"❌ Error fetching performance: {str(e)}")
            logger.error(f"Error in cmd_performance: {e}")

    def cmd_help(self, update: Update, context: CallbackContext):
        """Show help message with available commands"""
        msg = """
🤖 *Forex Trading Bot - Command List*

📊 *Monitoring*
/status - View open positions
/profit - P&L summary
/balance - Account balance
/performance - Trading statistics

🎮 *Control*
/start - Resume trading
/stop - Emergency stop (halt trading)

ℹ️ *Info*
/help - Show this message

💡 *Tips*
• Use /stop for emergency situations
• Check /status regularly to monitor positions
• /profit shows daily, weekly, and all-time results
        """

        self._send_message(msg)

    def _send_message(self, text: str):
        """Send message to configured chat"""
        if not self.enabled:
            return

        try:
            self.bot.send_message(
                chat_id=self.chat_id, text=text, parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")

    def send_notification(self, message: str, emoji: str = "ℹ️"):
        """Send notification message (called by trading bot)"""
        if not self.enabled:
            return

        msg = f"{emoji} {message}"
        self._send_message(msg)

    def send_trade_notification(self, trade_info: Dict):
        """Send notification when trade is opened/closed"""
        if not self.enabled:
            return

        action = trade_info.get("action", "Unknown")
        symbol = trade_info.get("symbol", "Unknown")
        price = trade_info.get("price", 0)
        quantity = trade_info.get("quantity", 0)
        pnl = trade_info.get("pnl", 0)

        if action == "BUY":
            emoji = "🟢"
            msg = f"{emoji} *BOUGHT {symbol}*\n\n"
            msg += f"Price: ${price:.4f}\n"
            msg += f"Quantity: {quantity}\n"
            msg += f"Value: ${price * quantity:.2f}"
        elif action == "SELL":
            emoji = "🔴" if pnl < 0 else "✅"
            msg = f"{emoji} *SOLD {symbol}*\n\n"
            msg += f"Price: ${price:.4f}\n"
            msg += f"Quantity: {quantity}\n"
            msg += f"P&L: ${pnl:+.2f}"
        else:
            msg = f"ℹ️ Trade: {action} {symbol}"

        self._send_message(msg)

    def _get_open_positions(self) -> List[Dict]:
        """Get open positions from trading bot"""
        if self.trading_bot and hasattr(self.trading_bot, "get_open_positions"):
            return self.trading_bot.get_open_positions()
        return []

    def _get_statistics(self) -> Dict:
        """Get trading statistics from trading bot"""
        if self.trading_bot and hasattr(self.trading_bot, "get_statistics"):
            return self.trading_bot.get_statistics()
        return {}

    def _get_balance(self) -> Dict:
        """Get account balance from trading bot"""
        if self.trading_bot and hasattr(self.trading_bot, "get_balance"):
            return self.trading_bot.get_balance()
        return {}

    def _get_performance(self) -> Dict:
        """Get performance metrics from trading bot"""
        if self.trading_bot and hasattr(self.trading_bot, "get_performance"):
            return self.trading_bot.get_performance()
        return {}

    def start_polling(self):
        """Start the Telegram bot (blocking)"""
        if not self.enabled:
            logger.warning("Telegram bot not enabled, skipping polling")
            return

        logger.info("🚀 Starting Telegram bot polling...")
        self.updater.start_polling()
        logger.info("✅ Telegram bot is running")

    def start_webhook(
        self, listen: str = "0.0.0.0", port: int = 8443, url_path: str = ""
    ):
        """Start the Telegram bot with webhook (for deployment)"""
        if not self.enabled:
            logger.warning("Telegram bot not enabled, skipping webhook")
            return

        logger.info(f"🚀 Starting Telegram bot webhook on {listen}:{port}")
        self.updater.start_webhook(listen=listen, port=port, url_path=url_path)
        logger.info("✅ Telegram bot webhook is running")

    def stop(self):
        """Stop the Telegram bot"""
        if self.enabled and self.updater:
            logger.info("Stopping Telegram bot...")
            self.updater.stop()
            logger.info("Telegram bot stopped")


# Demo/testing
if __name__ == "__main__":
    # Mock trading bot for testing
    class MockTradingBot:
        def get_open_positions(self):
            return [
                {
                    "symbol": "EURUSD",
                    "entry_price": 1.1000,
                    "current_price": 1.1050,
                    "quantity": 0.5,
                    "unrealized_pnl": 25.00,
                    "pnl_percent": 0.45,
                }
            ]

        def get_statistics(self):
            return {
                "daily_pnl": 150.50,
                "daily_trades": 5,
                "weekly_pnl": 890.25,
                "weekly_trades": 23,
                "total_pnl": 4523.75,
                "win_rate": 62.5,
                "profit_factor": 1.85,
                "sharpe_ratio": 1.75,
                "best_trade": 285.40,
                "worst_trade": -95.20,
            }

        def get_balance(self):
            return {
                "equity": 15234.56,
                "cash": 12500.00,
                "positions_value": 2734.56,
                "margin_used": 1234.56,
                "buying_power": 45000.00,
                "day_change": 234.56,
                "day_change_pct": 1.56,
            }

        def get_performance(self):
            return {
                "max_drawdown": 12.5,
                "volatility": 18.3,
                "sharpe": 1.75,
                "sortino": 2.15,
                "total_trades": 142,
                "win_rate": 62.5,
                "avg_win": 125.50,
                "avg_loss": -68.30,
                "profit_factor": 1.85,
                "avg_duration": 245.0,
                "avg_win_duration": 320.0,
                "avg_loss_duration": 180.0,
            }

    # Test mode
    print("🤖 Telegram Bot Controller - Test Mode")
    print("\nTo test with real Telegram:")
    print("1. Get token from @BotFather on Telegram")
    print("2. Get your chat_id from @userinfobot")
    print("3. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables")
    print("4. Run this script again")
    print("\nCommands available: /status, /profit, /balance, /performance, /help")

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if token and chat_id:
        mock_bot = MockTradingBot()
        telegram = TelegramBotController(token, chat_id, mock_bot)

        if telegram.enabled:
            print("\n✅ Telegram bot initialized!")
            print(f"Chat ID: {chat_id}")
            print("\nSend /help to your bot to see available commands")
            print("\nPress Ctrl+C to stop\n")

            try:
                telegram.start_polling()
                telegram.updater.idle()
            except KeyboardInterrupt:
                print("\n\nStopping...")
                telegram.stop()
        else:
            print("\n❌ Failed to initialize Telegram bot")
    else:
        print("\n⚠️ TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        print("Skipping real Telegram test")
