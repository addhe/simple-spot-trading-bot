# src/telegram_notifier.py
import asyncio
import logging
import traceback
from decimal import Decimal
from typing import Optional, Dict, Literal, Any, ClassVar
from contextlib import asynccontextmanager

from pydantic import BaseModel, Field, ConfigDict, model_validator
from aiohttp import ClientSession, ClientError
from config.settings import AppSettings

logger = logging.getLogger(__name__)

class NotificationBase(BaseModel):
    """Base model for all notifications"""
    priority: Literal['low', 'medium', 'high'] = 'medium'
    parse_mode: Literal['Markdown', 'HTML'] = 'Markdown'
    disable_notification: bool = False

class TradeNotification(NotificationBase):
    """Model for trade execution notifications"""
    trade_type: Literal['buy', 'sell']
    symbol: str
    quantity: Decimal
    price: Decimal
    usdt_balance: Decimal
    metadata: Dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @model_validator(mode='before')
    @classmethod
    def truncate_decimals(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """Truncate decimal values to 4 places"""
        decimal_fields = ['quantity', 'price', 'usdt_balance']
        return {
            k: round(v, 4) if k in decimal_fields and isinstance(v, Decimal) else v
            for k, v in values.items()
        }

    def format_message(self) -> str:
        emoji = "🟢" if self.trade_type == 'buy' else "🔴"
        return (
            f"{emoji} *{self.trade_type.upper()} Executed* {emoji}\n"
            f"• Pair: `{self.symbol}`\n"
            f"• Quantity: `{self.quantity:.6f}`\n"
            f"• Price: {format_currency(self.price)}\n"
            f"• Balance: {format_currency(self.usdt_balance)}"
        )

class ErrorNotification(NotificationBase):
    """Model for error notifications"""
    error_type: str
    error_message: str
    context: str = "general"
    stack_trace: Optional[str] = None
    metadata: Dict[str, str] = Field(default_factory=dict)

    @classmethod
    def from_exception(cls, exc: Exception, context: str = "general") -> 'ErrorNotification':
        """Create notification from exception instance"""
        return cls(
            error_type=exc.__class__.__name__,
            error_message=str(exc),
            context=context,
            stack_trace=cls._format_stack_trace(exc),
            metadata=getattr(exc, "metadata", {})
        )

    @staticmethod
    def _format_stack_trace(exc: Exception) -> str:
        """Format exception stack trace"""
        return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    def format_message(self) -> str:
        message = [
            "🚨 *System Error* 🚨",
            f"• Context: `{self.context}`",
            f"• Type: `{self.error_type}`",
            f"• Message: `{self.error_message}`"
        ]
        
        if self.stack_trace:
            message.append(f"\n```\n{self.stack_trace[:1000]}...\n```")
            
        return "\n".join(message)

class TelegramNotifier:
    """Advanced Telegram notification service with queue management"""
    
    MAX_RETRIES: ClassVar[int] = 3
    BASE_DELAY: ClassVar[float] = 0.5

    def __init__(self, settings: AppSettings):
        self._validate_config(settings)
        self.base_url = f"https://api.telegram.org/bot{settings.telegram_token}"
        self.chat_id = settings.telegram_chat_id
        self.session: Optional[ClientSession] = None
        self._queue = asyncio.Queue()
        self._active = False

    def _validate_config(self, settings: AppSettings):
        """Validate required configuration"""
        if not settings.telegram_token:
            raise ValueError("Telegram token is required")
        if not settings.telegram_chat_id:
            raise ValueError("Chat ID is required")

    async def __aenter__(self):
        self.session = ClientSession()
        self._active = True
        asyncio.create_task(self._process_queue())
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._active = False
        if self.session:
            await self.session.close()

    async def send(self, notification: NotificationBase):
        """Add notification to processing queue"""
        if self._active:
            await self._queue.put(notification)
        else:
            logger.warning("Notifier is closed, dropping notification")

    async def _process_queue(self):
        """Process notifications from queue with retries"""
        while self._active:
            notification = await self._queue.get()
            try:
                await self._send_with_retry(notification)
            except Exception as e:
                logger.error(f"Permanent failure sending notification: {str(e)}")
            finally:
                self._queue.task_done()

    async def _send_with_retry(self, notification: NotificationBase):
        """Retry logic with exponential backoff"""
        delay = self.BASE_DELAY
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                return await self._send_notification(notification)
            except Exception as e:
                if attempt == self.MAX_RETRIES:
                    raise
                
                logger.warning(f"Retry {attempt}/{self.MAX_RETRIES} for {type(notification).__name__}")
                await asyncio.sleep(delay)
                delay *= 2

    async def _send_notification(self, notification: NotificationBase):
        """Internal method to send notification"""
        payload = {
            "chat_id": self.chat_id,
            "text": notification.format_message(),
            "parse_mode": notification.parse_mode,
            "disable_notification": notification.disable_notification
        }

        async with self.session.post(
            f"{self.base_url}/sendMessage",
            json=payload,
            timeout=5
        ) as response:
            if response.status != 200:
                error = await response.text()
                raise ClientError(f"Telegram API error: {error}")

            logger.debug(f"Sent {type(notification).__name__} notification")

async def send_telegram_alert(message: str, priority: str = 'medium'):
    """Quick send helper for simple alerts"""
    async with TelegramNotifier(AppSettings()) as notifier:
        await notifier.send(ErrorNotification(
            error_type="Manual Alert",
            error_message=message,
            context="system",
            priority=priority
        ))