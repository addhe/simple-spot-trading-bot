# main.py
import asyncio
import logging
import signal
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from config.settings import AppSettings
from src.bot import TradingBot
from src.telegram_notifier import TelegramNotifier
from src.utils import (
    configure_logging,
    check_internet_connection,
    check_exchange_status,
    async_retry
)

# Inisialisasi logger
logger = logging.getLogger(__name__)

class BotReloadHandler(FileSystemEventHandler):
    """Handler untuk hot-reload dengan circuit breaker"""
    
    def __init__(self, bot_instance: TradingBot, settings: AppSettings):
        self.bot = bot_instance
        self.settings = settings
        self._cooldown = 2.0
        self._last_event_time = 0.0
        self._failure_count = 0
        self._max_failures = 3

    def on_modified(self, event):
        """Handle modifikasi file dengan debounce"""
        if not event.is_directory and self._should_trigger(event):
            self._last_event_time = time.monotonic()
            asyncio.create_task(self._safe_reload())

    def _should_trigger(self, event) -> bool:
        """Cek apakah event memenuhi syarat trigger"""
        return (
            (time.monotonic() - self._last_event_time) > self._cooldown and
            event.src_path.endswith(('bot.py', 'strategy.py', 'config.py'))
        )

    async def _safe_reload(self):
        """Reload aman dengan circuit breaker"""
        try:
            if self._failure_count >= self._max_failures:
                logger.error("Reload dinonaktifkan karena kegagalan beruntun")
                return
                
            await self.bot.graceful_shutdown()
            self.bot = TradingBot(self.settings)
            await self.bot.initialize()
            asyncio.create_task(self.bot.run())
            self._failure_count = 0
            logger.info("🔄 Bot berhasil di-reload")
        except asyncio.CancelledError:
            logger.info("Reload dibatalkan")
        except Exception as e:
            self._failure_count += 1
            logger.error(
                f"Gagal reload ({self._failure_count}/{self._max_failures}): {e}",
                exc_info=True
            )
            async with TelegramNotifier(self.settings) as notifier:
                await notifier.notify_error(e, context="hot-reload")

async def main_loop(settings: AppSettings):
    """Main workflow aplikasi"""
    logger.info("🚀 Memulai trading bot")
    
    async with TelegramNotifier(settings) as notifier:
        if not await validate_environment(settings):
            await notifier.notify_error(
                RuntimeError("Validasi lingkungan gagal")
            )
            return

        bot = await initialize_bot(settings)
        observer = setup_file_observer(bot, settings)
        
        try:
            await bot.run()
            await monitor_health(bot, notifier, settings)
        except asyncio.CancelledError:
            logger.info("Sinyal shutdown diterima")
        finally:
            await shutdown(observer, bot, notifier)

@async_retry(max_retries=3, initial_delay=1.0)
async def validate_environment(settings: AppSettings) -> bool:
    """Validasi lingkungan runtime"""
    checks = {
        "Koneksi Internet": check_internet_connection,
        "API Exchange": lambda: check_exchange_status(settings.exchange.base_url)
    }

    for nama_check, check_fn in checks.items():
        try:
            success = await check_fn()
            if not success:
                logger.critical(f"Ketergantungan kritis gagal: {nama_check}")
                return False
        except Exception as e:
            logger.error(f"Check {nama_check} gagal: {str(e)}", exc_info=True)
            return False
            
    return True

async def initialize_bot(settings: AppSettings) -> TradingBot:
    """Inisialisasi bot"""
    bot = TradingBot(settings)
    await bot.initialize()
    logger.info("🤖 Bot berhasil diinisialisasi")
    return bot

def setup_file_observer(bot: TradingBot, settings: AppSettings) -> Observer:
    """Konfigurasi file watcher"""
    observer = Observer()
    event_handler = BotReloadHandler(bot, settings)
    observer.schedule(event_handler, path="src", recursive=True)
    observer.start()
    logger.info("👀 File watcher aktif")
    return observer

async def shutdown(
    observer: Observer, 
    bot: TradingBot, 
    notifier: TelegramNotifier
):
    """Proses shutdown graceful"""
    logger.info("🛑 Memulai proses shutdown")
    
    shutdown_tasks = [
        bot.graceful_shutdown(),
        stop_observer(observer),
        notifier.send_alert("🔴 Trading bot dimatikan")
    ]
    
    try:
        await asyncio.wait_for(
            asyncio.gather(*shutdown_tasks),
            timeout=30.0
        )
    except asyncio.TimeoutError:
        logger.error("Timeout saat shutdown")
    
    logger.info("✅ Shutdown berhasil")

async def stop_observer(observer: Observer):
    """Menghentikan observer"""
    observer.stop()
    while observer.is_alive():
        await asyncio.sleep(0.1)
    observer.join()

async def monitor_health(
    bot: TradingBot, 
    notifier: TelegramNotifier,
    settings: AppSettings
):
    """Monitoring kesehatan sistem"""
    while True:
        try:
            health_status = await check_health(bot, settings)
            if not health_status["healthy"]:
                await notifier.notify_error(
                    Exception("Health check gagal"),
                    context=health_status["details"]
                )
            await asyncio.sleep(300)
        except asyncio.CancelledError:
            break

async def check_health(bot: TradingBot, settings: AppSettings) -> dict:
    """Pemeriksaan kesehatan sistem"""
    try:
        return {
            "healthy": True,
            "details": {
                "strategies_aktif": len(bot.strategies),
                "order_pending": len(bot.active_orders),
                "koneksi_exchange": await check_exchange_status(
                    settings.exchange.base_url
                )
            }
        }
    except Exception as e:
        logger.error(f"Health check error: {str(e)}")
        return {
            "healthy": False,
            "details": str(e)
        }

def handle_signal(signal, loop):
    """Handler sinyal shutdown"""
    logger.warning(f"⚠️ Menerima sinyal {signal.name}, memulai shutdown...")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()

if __name__ == "__main__":
    # Inisialisasi utama
    load_dotenv()
    settings = AppSettings()
    
    # Konfigurasi logging
    configure_logging(settings.logs_dir)
    logger.setLevel(settings.log_level)
    
    # Setup event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Registrasi handler sinyal
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal, sig, loop)

    try:
        loop.run_until_complete(main_loop(settings))
    except Exception as e:
        logger.critical(
            f"💀 Kegagalan kritis: {str(e)}", 
            exc_info=True,
            stack_info=True
        )
        loop.run_until_complete(
            TelegramNotifier(settings).notify_error(e, context="main-loop")
        )
    finally:
        if loop.is_running():
            loop.close()
        logger.info("🎉 Aplikasi berhenti dengan sukses")