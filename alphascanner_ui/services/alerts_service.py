"""Trade alerts service for Telegram and WhatsApp notifications."""

import re
import requests
from typing import Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class AlertsService:
    """Service to send trade alerts via Telegram and WhatsApp."""
    
    def __init__(
        self,
        telegram_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        whatsapp_webhook_url: Optional[str] = None,
    ):
        """Initialize alerts service.
        
        Args:
            telegram_token: Telegram bot token
            telegram_chat_id: Telegram chat ID for notifications
            whatsapp_webhook_url: Optional webhook that accepts {"message": "..."}
        """
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        self.whatsapp_webhook_url = whatsapp_webhook_url
    
    def send_telegram_alert(self, message: str, parse_mode: str = "HTML") -> bool:
        """Send alert via Telegram.
        
        Args:
            message: Alert message
            parse_mode: HTML or Markdown
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.telegram_token or not self.telegram_chat_id:
            logger.warning("Telegram credentials not configured")
            return False
        
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            payload = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }
            response = requests.post(url, json=payload, timeout=10)
            success = response.status_code == 200
            if success:
                logger.info(f"Telegram alert sent: {message[:50]}")
            else:
                logger.error(f"Telegram alert failed: {response.text}")
            return success
        except Exception as e:
            logger.error(f"Error sending Telegram alert: {e}")
            return False

    def send_whatsapp_alert(self, message: str) -> bool:
        """Send alert via a WhatsApp automation webhook."""
        if not self.whatsapp_webhook_url:
            logger.warning("WhatsApp webhook not configured")
            return False

        plain_message = re.sub(r"<[^>]+>", "", message)
        try:
            response = requests.post(
                self.whatsapp_webhook_url,
                json={"message": plain_message},
                timeout=10,
            )
            success = 200 <= response.status_code < 300
            if success:
                logger.info(f"WhatsApp alert sent: {plain_message[:50]}")
            else:
                logger.error(f"WhatsApp alert failed: {response.text}")
            return success
        except Exception as e:
            logger.error(f"Error sending WhatsApp alert: {e}")
            return False

    def send_alert(self, message: str, parse_mode: str = "HTML") -> bool:
        """Send an alert to every configured channel."""
        sent = False
        if self.telegram_token and self.telegram_chat_id:
            sent = self.send_telegram_alert(message, parse_mode=parse_mode) or sent
        if self.whatsapp_webhook_url:
            sent = self.send_whatsapp_alert(message) or sent
        return sent
    
    def send_breakout_alert(self, ticker: str, price: float, resistance: float, 
                           volume: float, setup_score: float = None) -> bool:
        """Send breakout alert.
        
        Args:
            ticker: Stock ticker
            price: Current price
            resistance: Resistance level broken
            volume: Volume ratio
            setup_score: Setup score (0-10) for pre-breakout
            
        Returns:
            True if sent successfully
        """
        alert_time = datetime.now().strftime("%H:%M:%S")
        
        if setup_score is not None:
            message = (
                f"🎯 <b>PRE-BREAKOUT SETUP</b>\n"
                f"<b>Ticker:</b> {ticker}\n"
                f"<b>Price:</b> ₹{price:.2f}\n"
                f"<b>Resistance:</b> ₹{resistance:.2f}\n"
                f"<b>Volume:</b> {volume:.2f}x\n"
                f"<b>Setup Score:</b> {setup_score}/10\n"
                f"<b>Time:</b> {alert_time}"
            )
        else:
            message = (
                f"⚡ <b>BREAKOUT DETECTED</b>\n"
                f"<b>Ticker:</b> {ticker}\n"
                f"<b>Price:</b> ₹{price:.2f}\n"
                f"<b>Resistance Broken:</b> ₹{resistance:.2f}\n"
                f"<b>Volume Ratio:</b> {volume:.2f}x\n"
                f"<b>Time:</b> {alert_time}"
            )
        
        return self.send_alert(message)
    
    def send_pullback_alert(self, ticker: str, price: float, ema20: float, 
                           support: float, rsi: float) -> bool:
        """Send pullback/reversal alert.
        
        Args:
            ticker: Stock ticker
            price: Current price
            ema20: EMA20 level
            support: Support level
            rsi: Current RSI
            
        Returns:
            True if sent successfully
        """
        alert_time = datetime.now().strftime("%H:%M:%S")
        message = (
            f"📉 <b>PULLBACK OPPORTUNITY</b>\n"
            f"<b>Ticker:</b> {ticker}\n"
            f"<b>Price:</b> ₹{price:.2f}\n"
            f"<b>EMA20:</b> ₹{ema20:.2f}\n"
            f"<b>Support:</b> ₹{support:.2f}\n"
            f"<b>RSI:</b> {rsi:.1f}\n"
            f"<b>Time:</b> {alert_time}"
        )
        
        return self.send_alert(message)
    
    def send_position_alert(self, ticker: str, alert_type: str, price: float, 
                           level: float, details: str = "") -> bool:
        """Send position management alert (stop hit, target reached, etc).
        
        Args:
            ticker: Stock ticker
            alert_type: Type of alert (STOP, TARGET, TRAILING_STOP, etc)
            price: Current price
            level: Target/Stop/Trailing level
            details: Additional details
            
        Returns:
            True if sent successfully
        """
        alert_time = datetime.now().strftime("%H:%M:%S")
        
        icons = {
            "STOP": "🛑",
            "TARGET": "🎯",
            "TRAILING_STOP": "📍",
            "WARNING": "⚠️",
        }
        icon = icons.get(alert_type, "📌")
        
        message = (
            f"{icon} <b>{alert_type} ALERT</b>\n"
            f"<b>Ticker:</b> {ticker}\n"
            f"<b>Price:</b> ₹{price:.2f}\n"
            f"<b>Level:</b> ₹{level:.2f}\n"
        )
        
        if details:
            message += f"<b>Details:</b> {details}\n"
        
        message += f"<b>Time:</b> {alert_time}"
        
        return self.send_alert(message)
    
    def send_test_alert(self) -> bool:
        """Send test alert to verify configuration.
        
        Returns:
            True if sent successfully
        """
        message = (
            "✅ <b>AlphaScanner Test Alert</b>\n"
            f"Connection successful!\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        return self.send_alert(message)


def get_alerts_service(telegram_token: Optional[str] = None, 
                      telegram_chat_id: Optional[str] = None,
                      whatsapp_webhook_url: Optional[str] = None) -> AlertsService:
    """Factory function to get alerts service instance.
    
    Args:
        telegram_token: Telegram bot token
        telegram_chat_id: Telegram chat ID
        
    Returns:
        AlertsService instance
    """
    return AlertsService(telegram_token, telegram_chat_id, whatsapp_webhook_url)
