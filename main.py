import asyncio
import logging
import signal
import os
import platform
import traceback
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Coroutine
from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from config.settings import AppSettings
from src.bot import TradingBot
from src.telegram_notifier import TelegramNotifier, ErrorNotification
from src.utils import (
    configure_logging,
    check_internet_connection,
    check_exchange_status,
    async_retry,
    async_error_handler
)

# Inisialisasi awal
load_dotenv()
settings = AppSettings()
configure_logging(settings)

logger = logging.getLogger(__name__)

def validate_configuration(settings: AppSettings) -> bool:
    """Validasi konfigurasi aplikasi secara menyeluruh"""
    errors = []
    
    # Validasi nested settings
    required_settings = [
        (settings.exchange.api_key, "Exchange API key"),
        (settings.exchange.api_secret, "Exchange API secret"),
        (settings.telegram_token, "Telegram token"),
        (settings.telegram_chat_id, "Telegram chat ID")
    ]
    
    for value, name in required_settings:
        if not value:
            errors.append(f"{name} is required")

    # Validasi risk management
    if not (Decimal('0.01') <= settings.risk_per_trade <= Decimal('0.1')):
        errors.append("Risk per trade harus antara 1% sampai 10%")

    if errors:
        logger.error(
            "Konfigurasi tidak valid",
            extra={
                "errors": errors,
                "environment": settings.environment,
                "system_time": datetime.utcnow().isoformat()
            }
        )
        return False
        
    return True

async def graceful_shutdown(loop: asyncio.AbstractEventLoop):
    """Proses shutdown terurut dengan logging detail"""
    logger.info("🛑 Memulai proses shutdown")
    
    active_tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    logger.debug(f"Task aktif: {len(active_tasks)}", extra={"tasks": [t.get_name() for t in active_tasks]})
    
    # Batalkan semua task
    for task in active_tasks:
        task.cancel()
    
    # Tunggu task selesai
    results = await asyncio.gather(*active_tasks, return_exceptions=True)
    
    # Log hasil shutdown
    for task, result in zip(active_tasks, results):
        if isinstance(result, Exception):
            logger.warning(
                "Task selesai dengan error",
                extra={"task": task.get_name(), "error": str(result)}
            )
    
    await loop.shutdown_asyncgens()
    logger.info("✅ Semua resource dibersihkan")

def handle_signal(sig: signal.Signals, loop: asyncio.AbstractEventLoop):
    """Handler sinyal cross-platform"""
    logger.warning(
        f"⚠️ Menerima sinyal {sig.name}",
        extra={"pid": os.getpid(), "platform": platform.platform()}
    )
    loop.create_task(graceful_shutdown(loop))

async def validate_environment(settings: AppSettings) -> bool:
    """Validasi lingkungan eksekusi secara asynchronous"""
    loop = asyncio.get_running_loop()
    
    async def async_check_internet():
        return await loop.run_in_executor(None, check_internet_connection)
    
    async def async_check_exchange():
        return await loop.run_in_executor(None, check_exchange_status, settings.exchange.base_url)

    checks = {
        "Koneksi Internet": async_check_internet,
        "API Exchange": async_check_exchange,
        "Konfigurasi": lambda: validate_configuration(settings)
    }
    
    results = []
    for name, check in checks.items():
        try:
            result = await check() if asyncio.iscoroutinefunction(check) \
                else await loop.run_in_executor(None, check)
            
            logger.debug(
                "Hasil check lingkungan",
                extra={"check": name, "result": result}
            )
            results.append(result)
        except Exception as e:
            logger.error(
                f"Check {name} gagal",
                exc_info=True,
                extra={"error_type": type(e).__name__}
            )
            results.append(False)
    
    return all(results)

@async_retry(max_retries=3, initial_delay=1.0, handled_errors=(RuntimeError,))
@async_error_handler("Fatal error", notify=True)
async def main_loop(settings: AppSettings):
    """Inti eksekusi trading bot dengan error handling komprehensif"""
    logger.info("🚀 Memulai Trading Bot", extra={"version": "1.0.0"})
    
    async with TelegramNotifier(settings) as notifier:
        try:
            # Validasi environment dengan timeout
            try:
                validation_result = await asyncio.wait_for(
                    validate_environment(settings),
                    timeout=15.0
                )
            except asyncio.TimeoutError as e:
                await notifier.send(
                    ErrorNotification(
                        error_type="EnvironmentError",
                        error_message="Validasi lingkungan timeout",
                        context={"phase": "startup", "timeout": 15}
                    )
                )
                raise RuntimeError("Environment validation timeout") from e

            if not validation_result:
                await notifier.send(
                    ErrorNotification(
                        error_type="EnvironmentError",
                        error_message="Validasi lingkungan gagal",
                        context={"failed_checks": []}
                    )
                )
                raise RuntimeError("Environment validation failed")

            # Inisialisasi komponen utama
            bot = await TradingBot.create(settings)
            observer = setup_file_observer(settings)
            
            try:
                # Eksekusi paralel komponen sistem
                await asyncio.gather(
                    bot.run(),
                    monitor_system_health(bot, notifier),
                    log_performance_metrics()
                )
            except asyncio.CancelledError:
                logger.info("Shutdown diminta")
            finally:
                await shutdown_sequence(observer, bot)

        except Exception as e:
            logger.critical(
                "Error fatal di main loop",
                exc_info=True,
                extra={"stack_trace": traceback.format_exc()}
            )
            await notifier.send(
                ErrorNotification.from_exception(e, context="main-loop")
            )
            raise

def setup_file_observer(settings: AppSettings) -> Observer:
    """Monitor perubahan konfigurasi dengan watchdog"""
    class EnvFileHandler(FileSystemEventHandler):
        def __init__(self, reload_callback: Callable):
            self.reload_callback = reload_callback

        def on_modified(self, event):
            if event.src_path.endswith(".env"):
                logger.info("⏳ Deteksi perubahan .env, reload konfigurasi...")
                try:
                    load_dotenv(override=True)
                    settings.reload()
                    self.reload_callback()
                    logger.info("✅ Konfigurasi diperbarui")
                except Exception as e:
                    logger.error("Gagal reload konfigurasi", exc_info=True)

    observer = Observer()
    event_handler = EnvFileHandler(lambda: logger.info("Konfigurasi diubah"))
    observer.schedule(event_handler, path=".", recursive=False)
    observer.start()
    return observer

async def shutdown_sequence(observer: Observer, bot: TradingBot):
    """Proses shutdown terurut"""
    logger.info("🔌 Memulai shutdown sistem")
    
    # Step 1: Hentikan file observer
    if observer.is_alive():
        observer.stop()
        observer.join()
    
    # Step 2: Hentikan trading bot
    await bot.close()
    
    # Step 3: Bersihkan resource lain
    logger.info("🛑 Sistem berhenti dengan aman")

async def monitor_system_health(bot: TradingBot, notifier: TelegramNotifier):
    """Pemantauan kesehatan sistem berkala"""
    while True:
        try:
            health_status = {
                "memory_usage": os.getpid().memory_info().rss,
                "active_orders": len(bot.active_orders),
                "connection_status": await bot.check_connection()
            }
            
            logger.debug(
                "Status sistem",
                extra=health_status
            )
            
            await asyncio.sleep(60)
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            await notifier.send(
                ErrorNotification.from_exception(e, context="health-check")
            )

if __name__ == "__main__":
    # Konfigurasi event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Penanganan sinyal cross-platform
    if os.name == "nt":
        signals = (signal.SIGINT,)
    else:
        signals = (signal.SIGINT, signal.SIGTERM)
    
    for sig in signals:
        loop.add_signal_handler(sig, lambda s=sig: handle_signal(s, loop))

    try:
        loop.run_until_complete(main_loop(settings))
    except Exception as e:
        logger.critical(
            "💀 Kegagalan sistem",
            extra={
                "error": str(e),
                "stack_trace": traceback.format_exc(),
                "system_info": {
                    "platform": platform.platform(),
                    "python_version": platform.python_version()
                }
            }
        )
        
        # Fallback jika notifikasi gagal
        try:
            loop.run_until_complete(
                TelegramNotifier(settings).send(
                    ErrorNotification.from_exception(e, context="global")
                )
            )
        except Exception as notify_err:
            with open("emergency.log", "a") as f:
                f.write(f"[{datetime.utcnow().isoformat()}] {str(e)}\n")
                f.write(f"Notifikasi gagal: {str(notify_err)}\n")
    finally:
        if not loop.is_closed():
            loop.close()
        logger.info("🎉 Aplikasi berhenti")