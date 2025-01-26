# src/telegram_notifier.py
import asyncio
import logging
import traceback
from decimal import Decimal
from typing import Optional, Dict, Literal, Any, Union
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field, ConfigDict, model_validator
from aiohttp import ClientSession, ClientError, ClientTimeout
from config.settings import AppSettings
from src.formatters import format_currency

logger = logging.getLogger(__name__)

class NotificationBase(BaseModel):
    """Base model untuk semua notifikasi"""
    priority: Literal['low', 'medium', 'high'] = 'medium'
    parse_mode: Literal['Markdown', 'HTML'] = 'Markdown'
    disable_notification: bool = False
    metadata: Dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def format_message(self) -> str:
        """Method dasar untuk formatting pesan"""
        raise NotImplementedError("Subclasses must implement this method")

class TradeNotification(NotificationBase):
    """Model untuk notifikasi eksekusi trade"""
    trade_type: Literal['buy', 'sell']
    symbol: str
    quantity: Decimal
    price: Decimal
    usdt_balance: Decimal

    @model_validator(mode='before')
    @classmethod
    def truncate_decimals(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """Truncate nilai decimal ke 4 digit"""
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
    """Model untuk notifikasi error"""
    error_type: str
    error_message: str
    context: str = "general"
    stack_trace: Optional[str] = None

    @classmethod
    def from_exception(cls, exc: Exception, context: str = "general") -> 'ErrorNotification':
        """Membuat notifikasi dari exception"""
        return cls(
            error_type=exc.__class__.__name__,
            error_message=str(exc),
            context=context,
            stack_trace=cls._format_stack_trace(exc),
            metadata=getattr(exc, "metadata", {})
        )

    @staticmethod
    def _format_stack_trace(exc: Exception) -> str:
        """Format stack trace exception"""
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
    """Layanan notifikasi Telegram dengan manajemen antrian dan retry"""
    
    MAX_RETRIES: int = 3
    BASE_DELAY: float = 0.5
    TIMEOUT: int = 10

    def __init__(self, settings: AppSettings):
        self._validate_config(settings)
        self.base_url = f"https://api.telegram.org/bot{settings.telegram_token.get_secret_value()}"
        self.chat_id = settings.telegram_chat_id
        self.session: Optional[ClientSession] = None
        self._queue = asyncio.Queue()
        self._active = False
        self._task: Optional[asyncio.Task] = None

    def _validate_config(self, settings: AppSettings):
        """Validasi konfigurasi wajib"""
        if not settings.telegram_token.get_secret_value():
            raise ValueError("Telegram token diperlukan")
        if not settings.telegram_chat_id:
            raise ValueError("Chat ID diperlukan")

    async def __aenter__(self):
        self.session = ClientSession(timeout=ClientTimeout(total=self.TIMEOUT))
        self._active = True
        self._task = asyncio.create_task(self._process_queue())
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._active = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self.session:
            await self.session.close()

    async def send(self, notification: NotificationBase):
        """Menambahkan notifikasi ke antrian"""
        if self._active:
            await self._queue.put(notification)
        else:
            logger.warning("Notifier tidak aktif, notifikasi diabaikan")

    async def notify_error(self, error: Exception, context: str = "general"):
        """Shortcut untuk mengirim notifikasi error"""
        notification = ErrorNotification.from_exception(error, context)
        await self.send(notification)

    async def notify_trade(self, trade_data: Dict[str, Any]):
        """Shortcut untuk mengirim notifikasi trade"""
        notification = TradeNotification(**trade_data)
        await self.send(notification)

    async def _process_queue(self):
        """Memproses antrian notifikasi dengan retry"""
        while self._active or not self._queue.empty():
            try:
                notification = await asyncio.wait_for(
                    self._queue.get(), 
                    timeout=1.0
                )
                await self._send_with_retry(notification)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Gagal memproses notifikasi: {str(e)}")
            finally:
                if not self._queue.empty():
                    self._queue.task_done()

    async def _send_with_retry(self, notification: NotificationBase):
        """Mekanisme retry dengan exponential backoff"""
        delay = self.BASE_DELAY
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                return await self._send_notification(notification)
            except Exception as e:
                if attempt == self.MAX_RETRIES:
                    logger.error(f"Gagal mengirim notifikasi setelah {self.MAX_RETRIES} percobaan")
                    raise
                
                logger.warning(f"Retry {attempt}/{self.MAX_RETRIES} untuk {type(notification).__name__}")
                await asyncio.sleep(delay)
                delay *= 2

    async def _send_notification(self, notification: NotificationBase):
        """Mengirim notifikasi ke API Telegram"""
        if not self.session:
            raise RuntimeError("Session belum diinisialisasi")

        payload = {
            "chat_id": self.chat_id,
            "text": notification.format_message(),
            "parse_mode": notification.parse_mode,
            "disable_notification": notification.disable_notification
        }

        try:
            async with self.session.post(
                f"{self.base_url}/sendMessage",
                json=payload,
                timeout=ClientTimeout(total=5)
            ) as response:
                if response.status != 200:
                    error = await response.text()
                    raise ClientError(f"Telegram API error: {error}")

                logger.debug(f"Notifikasi {type(notification).__name__} terkirim")
                return await response.json()
        except Exception as e:
            logger.error(f"Gagal mengirim notifikasi: {str(e)}")
            raise

@asynccontextmanager
async def get_notifier(settings: AppSettings):
    """Context manager untuk notifier"""
    notifier = TelegramNotifier(settings)
    async with notifier:
        yield notifier

async def send_telegram_alert(
    message: str,
    settings: AppSettings,
    priority: str = 'medium'
):
    """Helper untuk mengirim alert sederhana"""
    async with get_notifier(settings) as notifier:
        await notifier.send(ErrorNotification(
            error_type="Manual Alert",
            error_message=message,
            context="system",
            priority=priority
        ))