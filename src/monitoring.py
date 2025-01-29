#src/monitoring.py
import logging
import schedule
import time
from threading import Thread

from config.settings import Settings
from utils.logger import configure_logger

class HealthCheck:
    def __init__(self, bot_components, settings):
        self.bot_components = bot_components
        self.settings = settings
        self.logger = configure_logger('HealthCheck', settings.log_level)

    def _health_check(self):
        # Pemantauan kesehatan koneksi ke API
        if not self.bot_components.api_connection.is_connected():
            self.logger.error("Koneksi ke API tidak tersedia")
            return False

        # Pemantauan kesehatan ketersediaan data historis
        if not self.bot_components.historical_data.is_available():
            self.logger.error("Data historis tidak tersedia")
            return False

        # Pemantauan kesehatan kinerja komponen
        if not self.bot_components.performance_monitor.is_healthy():
            self.logger.error("Kinerja komponen tidak sehat")
            return False

        return True

    def report_health(self):
        health_status = self._health_check()
        if health_status:
            self.logger.info("Kesehatan komponen: SEHAT")
        else:
            self.logger.error("Kesehatan komponen: TIDAK SEHAT")

    def start_periodic_health_checks(self):
        schedule.every(self.settings.health_check_interval).seconds.do(self.report_health)
        thread = Thread(target=self._run_schedule)
        thread.start()

    def _run_schedule(self):
        while True:
            schedule.run_pending()
            time.sleep(1)