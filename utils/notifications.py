#!/usr/bin/env python3
"""
Notification System for Trading Bot.

Uses ntfy.sh for simple, free push notifications.
No account required - just install the app and subscribe to a topic!

Usage:
    from utils.notifications import TradingNotifier

    notifier = TradingNotifier(ntfy_topic="big-e-trading")
    notifier.send_trade_alert("BUY", "QQQ", 10, 520.50, 5205.00)
"""

import os
import requests
import smtplib
from email.mime.text import MIMEText
from datetime import datetime


class NtfyNotifier:
    """
    Send push notifications via ntfy.sh.

    This is the simplest notification method:
    - No account required
    - Just install the app and subscribe to a topic
    - Free forever
    """

    def __init__(self, topic: str = None, server: str = "https://ntfy.sh"):
        """
        Initialize ntfy notifier.

        Args:
            topic: Topic name (e.g., "big-e-trading")
            server: ntfy server URL (default: https://ntfy.sh)
        """
        self.topic = topic or os.environ.get("NTFY_TOPIC", "big-e-trading")
        self.server = server
        self.enabled = bool(self.topic)

        if self.enabled:
            print(f"✅ ntfy.sh notifications enabled (topic: {self.topic})")
        else:
            print("⚠️ ntfy disabled - set NTFY_TOPIC env var or pass topic parameter")

    def send(
        self, message: str, title: str = None, priority: int = 3, tags: list = None
    ) -> bool:
        """
        Send a push notification.

        Args:
            message: Message text
            title: Optional title
            priority: 1-5 (1=min, 3=default, 5=urgent)
            tags: Emoji tags (e.g., ["money_with_wings", "chart"])

        Returns:
            True if sent successfully
        """
        if not self.enabled:
            print(f"📱 [ntfy disabled] {message}")
            return False

        try:
            headers = {}
            if title:
                # Remove emojis/non-ASCII and strip whitespace for ntfy compatibility
                headers["Title"] = (
                    title.encode("ascii", errors="ignore").decode("ascii").strip()
                )
            if priority != 3:
                headers["Priority"] = str(priority)
            if tags:
                headers["Tags"] = ",".join(tags)

            response = requests.post(
                f"{self.server}/{self.topic}",
                data=message.encode("utf-8"),
                headers=headers,
                timeout=10,
            )

            if response.status_code == 200:
                print(f"📱 Notification sent to ntfy topic: {self.topic}")
                return True
            else:
                print(f"❌ ntfy failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            print(f"❌ ntfy error: {e}")
            return False


class SmsNotifier:
    """
    Send SMS via Email-to-SMS Gateway (e.g., AT&T number@txt.att.net).
    """

    def __init__(
        self,
        to_number: str = None,
        smtp_user: str = None,
        smtp_pass: str = None,
        smtp_server: str = "smtp.gmail.com",
        smtp_port: int = 587,
    ):
        self.to_number = to_number or os.environ.get("SMS_PHONE_NUMBER")
        self.smtp_user = smtp_user or os.environ.get("SMTP_USER")
        self.smtp_pass = smtp_pass or os.environ.get("SMTP_PASSWORD")
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port

        # Gateway: AT&T uses [number]@txt.att.net
        self.gateway = "@txt.att.net"
        self.enabled = bool(self.to_number and self.smtp_user and self.smtp_pass)

        if self.enabled:
            # Format number (remove non-digits)
            self.clean_number = "".join(filter(str.isdigit, self.to_number))
            self.to_address = f"{self.clean_number}{self.gateway}"
            print(f"✅ SMS notifications enabled for: {self.clean_number}")
        else:
            print(
                "📱 SMS disabled - set SMS_PHONE_NUMBER, SMTP_USER, and SMTP_PASSWORD"
            )

    def send(self, message: str, title: str = None) -> bool:
        if not self.enabled:
            return False

        try:
            full_msg = f"{title}\n\n{message}" if title else message
            # Shorten for SMS (most gateways wrap/split but let's be concise)
            if len(full_msg) > 160:
                # Still send but maybe trim to be safe or let gateway split
                pass

            msg = MIMEText(full_msg)
            msg["Subject"] = title if title else "Trading Alert"
            msg["From"] = self.smtp_user
            msg["To"] = self.to_address

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_pass)
                server.send_message(msg)

            print(f"📡 SMS sent to {self.to_address}")
            return True
        except smtplib.SMTPAuthenticationError as e:
            error_str = str(e)
            if (
                "Application-specific password required" in error_str
                or "5.7.9" in error_str
            ):
                print("❌ SMS error: Google App Password required.")
                print(
                    "💡 Please generate a 16-character App Password at: https://myaccount.google.com/apppasswords"
                )
                print("💡 Then update your secret using ./deploy_gcloud.sh")
            else:
                print(f"❌ SMS auth error: {e}")
            return False
        except Exception as e:
            print(f"❌ SMS error: {e}")
            return False


class TelegramNotifier:
    """
    Send notifications via Telegram Bot API.

    Requires:
        TELEGRAM_BOT_TOKEN: Bot token from @BotFather
        TELEGRAM_CHAT_ID: Your chat ID from @userinfobot
    """

    def __init__(self, token: str = None, chat_id: str = None):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
        self.enabled = bool(self.token and self.chat_id)
        self.api_url = (
            f"https://api.telegram.org/bot{self.token}/sendMessage"
            if self.token
            else None
        )

        if self.enabled:
            print(f"✅ Telegram notifications enabled (chat: {self.chat_id})")
        else:
            print("📱 Telegram disabled - set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")

    def send(self, message: str, title: str = None) -> bool:
        if not self.enabled:
            return False

        try:
            # Plain text (no Markdown) to avoid issues with underscores in pair names
            full_msg = f"{title}\n\n{message}" if title else message

            response = requests.post(
                self.api_url,
                json={
                    "chat_id": self.chat_id,
                    "text": full_msg,
                },
                timeout=10,
            )

            if response.status_code == 200:
                print(f"📲 Telegram message sent")
                return True
            else:
                print(f"❌ Telegram error: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"❌ Telegram error: {e}")
            return False


class TradingNotifier:
    """
    Central notification manager for trading bot.
    Uses ntfy.sh for simple push notifications.
    """

    def __init__(self, ntfy_topic: str = None):
        """
        Initialize the trading notifier.

        Args:
            ntfy_topic: ntfy.sh topic name (e.g., "big-e-trading")
        """
        self.ntfy = NtfyNotifier(topic=ntfy_topic)
        self.sms = SmsNotifier()
        self.telegram = TelegramNotifier()
        self.daily_trades = []

    def _format_currency(self, amount: float) -> str:
        """Format a number as currency."""
        return f"${amount:,.2f}"

    def _format_shares(self, shares: float) -> str:
        """Format shares count."""
        if shares == int(shares):
            return str(int(shares))
        return f"{shares:.4f}"

    def _send(
        self, message: str, title: str = None, priority: int = 3, tags: list = None
    ) -> bool:
        """Send notification via available channels."""
        result = False

        # Always print to console
        print(f"\n{'=' * 40}")
        if title:
            print(f"📢 {title}")
        print(message)
        print(f"{'=' * 40}\n")

        # Send via ntfy
        if self.ntfy.enabled:
            result = self.ntfy.send(message, title=title, priority=priority, tags=tags)

        # Send via Telegram (preferred)
        if self.telegram.enabled:
            self.telegram.send(message, title=title)
            result = True

        # Send via SMS for high priority alerts (deprecated - carriers discontinued)
        if self.sms.enabled and (priority >= 4 or "DAILY SUMMARY" in message):
            self.sms.send(message, title=title)
            result = True

        return result

    def send_trade_alert(
        self,
        action: str,
        symbol: str,
        shares: float,
        price: float,
        total_value: float,
        portfolio_value: float = None,
        stop_price: float = None,
    ) -> bool:
        """Send a trade execution alert."""
        emoji = "🟢" if action == "BUY" else "🔴"
        tags = (
            ["chart_with_upwards_trend"]
            if action == "BUY"
            else ["chart_with_downwards_trend"]
        )

        message = (
            f"{emoji} {action} {symbol}\n"
            f"Shares: {self._format_shares(shares)}\n"
            f"Price: {self._format_currency(price)}\n"
            f"Total: {self._format_currency(total_value)}"
        )

        if portfolio_value:
            message += f"\nPortfolio: {self._format_currency(portfolio_value)}"

        if stop_price:
            message += f"\n🛑 Stop: {self._format_currency(stop_price)}"

        # Track for daily summary
        self.daily_trades.append(
            {
                "action": action,
                "symbol": symbol,
                "shares": shares,
                "price": price,
                "value": total_value,
                "time": datetime.now(),
            }
        )

        return self._send(message, title=f"{action} {symbol}", priority=4, tags=tags)

    def send_stop_loss_alert(
        self,
        symbol: str,
        shares: float,
        trigger_price: float,
        entry_price: float,
        is_trailing: bool = False,
    ) -> bool:
        """Send a stop-loss trigger alert."""
        stop_type = "TRAILING STOP" if is_trailing else "STOP LOSS"
        pnl = (trigger_price - entry_price) * shares
        pnl_pct = ((trigger_price / entry_price) - 1) * 100
        pnl_emoji = "📈" if pnl > 0 else "📉"

        message = (
            f"🛑 {stop_type} TRIGGERED\n"
            f"Symbol: {symbol}\n"
            f"Shares: {self._format_shares(shares)}\n"
            f"Trigger: {self._format_currency(trigger_price)}\n"
            f"Entry: {self._format_currency(entry_price)}\n"
            f"{pnl_emoji} P&L: {self._format_currency(pnl)} ({pnl_pct:+.2f}%)"
        )

        return self._send(
            message, title=f"🛑 {stop_type}", priority=5, tags=["warning"]
        )

    def send_daily_summary(
        self,
        start_value: float,
        end_value: float,
        trades_count: int = None,
    ) -> bool:
        """Send end-of-day summary."""
        if trades_count is None:
            trades_count = len(self.daily_trades)

        daily_pnl = end_value - start_value
        daily_pct = ((end_value / start_value) - 1) * 100 if start_value > 0 else 0

        emoji = "📈" if daily_pnl >= 0 else "📉"
        tags = ["moneybag"] if daily_pnl >= 0 else ["money_with_wings"]

        message = (
            f"📊 DAILY SUMMARY\n"
            f"Date: {datetime.now().strftime('%Y-%m-%d')}\n"
            f"Trades: {trades_count}\n"
            f"Start: {self._format_currency(start_value)}\n"
            f"End: {self._format_currency(end_value)}\n"
            f"{emoji} P&L: {self._format_currency(daily_pnl)} ({daily_pct:+.2f}%)"
        )

        # Reset daily tracking
        self.daily_trades = []

        return self._send(message, title="📊 Daily Summary", tags=tags)

    def send_enhanced_daily_summary(
        self,
        collector,  # DailySummaryCollector instance
        end_balance: float,
    ) -> bool:
        """
        Send enhanced daily summary using DailySummaryCollector.

        Args:
            collector: DailySummaryCollector with day's data
            end_balance: Ending account balance
        """
        try:
            message = collector.format_telegram_message(end_balance)
            summary = collector.generate_summary(end_balance)

            # Determine emoji based on P&L
            pnl = summary["balance"]["pnl"]
            emoji = "📈" if pnl >= 0 else "📉"
            tags = ["moneybag"] if pnl >= 0 else ["money_with_wings"]

            # Upload to GCS if enabled
            import os

            if os.environ.get("USE_CLOUD_STORAGE", "").lower() == "true":
                try:
                    from utils.gcs_storage import upload_to_gcs

                    upload_to_gcs(summary, f"reports/daily_{summary['date']}.json")
                except ImportError:
                    pass

            # Reset collector for next day
            collector.reset()

            return self._send(message, title=f"{emoji} Daily Summary", tags=tags)
        except Exception as e:
            print(f"❌ Enhanced daily summary failed: {e}")
            # Fallback to basic summary
            return self.send_daily_summary(
                start_value=collector.start_balance or end_balance,
                end_value=end_balance,
            )

    def send_error_alert(self, error_message: str) -> bool:
        """Send an error alert."""
        message = f"⚠️ TRADING BOT ERROR\n{error_message[:200]}"
        return self._send(message, title="⚠️ Error", priority=5, tags=["rotating_light"])

    def send_startup_alert(
        self,
        symbol: str,
        strategy: str,
        models_count: int,
        balance: float,
    ) -> bool:
        """Send a bot startup notification."""
        message = (
            f"🚀 TRADING BOT STARTED\n"
            f"Symbol: {symbol}\n"
            f"Strategy: {strategy}\n"
            f"Models: {models_count}\n"
            f"Balance: {self._format_currency(balance)}"
        )

        return self._send(message, title="🚀 Bot Started", tags=["rocket"])


# Singleton instance
_notifier = None


def get_notifier(ntfy_topic: str = None) -> TradingNotifier:
    """Get or create the global notifier instance."""
    global _notifier
    if _notifier is None:
        _notifier = TradingNotifier(ntfy_topic=ntfy_topic)
    return _notifier


if __name__ == "__main__":
    # Demo / Test
    import sys

    topic = sys.argv[1] if len(sys.argv) > 1 else "big-e-trading"

    print(f"📱 Testing ntfy.sh notifications (topic: {topic})\n")

    notifier = TradingNotifier(ntfy_topic=topic)

    # Send test notification
    notifier.send_trade_alert(
        action="BUY",
        symbol="QQQ",
        shares=2,
        price=520.50,
        total_value=1041.00,
        portfolio_value=5000.00,
        stop_price=494.48,
    )

    print("\n✅ Check your phone for the notification!")
