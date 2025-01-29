import logging
from typing import Optional
from dataclasses import dataclass
import threading
import time

from binance.client import Client

from config.settings import Settings
from config.validator import validate_settings
from interfaces.market_data import MarketDataProvider
from interfaces.strategy import TradingStrategy
from interfaces.order_manager import OrderManagerInterface
from interfaces.risk_manager import RiskManagerInterface
from services.market_data import MarketData
from services.order_management import OrderManager
from services.risk_management import RiskManager
from strategies.sma_crossover import SMACrossoverStrategy
from utils.logger import configure_logger
from utils.exceptions import (
    TradingBotError,
    MarketDataError,
    OrderExecutionError,
    ConfigurationError
)


@dataclass
class BotComponents:
    """Data class to hold bot dependencies."""
    market_data: MarketDataProvider
    order_manager: OrderManagerInterface
    risk_manager: RiskManagerInterface
    strategy: TradingStrategy


class TradingBot:
    """
    Primary trading bot orchestration class with comprehensive
    dependency injection and modular architecture.
    """

    def __init__(self, settings: Settings, components: BotComponents,
                 logger: Optional[logging.Logger] = None) -> None:
        """
        Initialize trading bot with configurable components.

        Args:
            settings: Validated application configuration settings.
            components: Initialized bot components.
            logger: Optional custom logger.
        """
        self.settings = settings
        self.logger = logger or configure_logger(
            'TradingBot', log_level=settings.log_level
        )
        self.components = components

        self.running = False
        self.thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()

    def start(self) -> None:
        """Initiate trading bot execution in a separate thread."""
        if self.running:
            self.logger.warning("Trading bot is already running.")
            return

        try:
            self._validate_startup()
            self.running = True
            self._shutdown_event.clear()
            self.thread = threading.Thread(target=self._run_loop)
            self.thread.start()
            self.logger.info(f"Trading bot started for {self.settings.symbol}.")
        except Exception as e:
            self.running = False
            raise TradingBotError(f"Failed to start trading bot: {str(e)}", "STARTUP_ERROR")

    def _validate_startup(self) -> None:
        """Validate all components and configurations before startup."""
        try:
            _ = self.components.market_data.get_current_price(self.settings.symbol)
            self.components.order_manager.validate_account_status()
            self.components.risk_manager.validate_risk_parameters()
        except Exception as e:
            raise ConfigurationError(f"Startup validation failed: {str(e)}", "VALIDATION_ERROR")

    def _run_loop(self) -> None:
        """Continuous trading loop with error handling and graceful shutdown."""
        while not self._shutdown_event.is_set() and self.running:
            try:
                self._run_iteration()
                time.sleep(self.settings.interval)  # Configurable interval
            except MarketDataError as mde:
                self.logger.error(f"Market data error: {mde}")
                time.sleep(self.settings.error_retry_interval)
            except OrderExecutionError as oee:
                self.logger.error(f"Order execution error: {oee}")
                time.sleep(self.settings.error_retry_interval)
            except Exception as e:
                self.logger.critical(
                    f"Unexpected error in trading loop: {e}",
                    exc_info=True
                )
                self.stop()  # Graceful shutdown on critical errors

    def _run_iteration(self) -> None:
        """Execute single trading iteration with robust logic."""
        try:
            historical_data = self.components.market_data.get_historical_data(
                symbol=self.settings.symbol
            )
            if historical_data.empty:
                raise MarketDataError("Empty historical data received", "EMPTY_DATA")

            signal = self.components.strategy.generate_signal(historical_data)
            current_price = self.components.market_data.get_current_price(
                self.settings.symbol
            )

            if signal != 0:
                self._execute_trade(signal, current_price)

        except Exception as e:
            raise TradingBotError(f"Iteration error: {str(e)}", "ITERATION_ERROR")

    def _execute_trade(self, signal: int, current_price: float) -> None:
        """
        Execute trade based on strategy signal with pre-trade validations.

        Args:
            signal: Trading signal (-1: sell, 1: buy).
            current_price: Current market price.
        """
        try:
            self.components.risk_manager.validate_trade(
                symbol=self.settings.symbol,
                side="BUY" if signal == 1 else "SELL",
                current_price=current_price
            )

            quantity = self.components.risk_manager.calculate_position_size(
                symbol=self.settings.symbol,
                current_price=current_price,
                stop_loss_percentage=self.settings.strategy.stop_loss
            )

            order_result = self.components.order_manager.create_order(
                symbol=self.settings.symbol,
                side="BUY" if signal == 1 else "SELL",
                quantity=quantity
            )

            self.logger.info(f"Trade executed successfully: {order_result}")

        except Exception as e:
            raise OrderExecutionError(f"Trade execution failed: {str(e)}", "EXECUTION_ERROR")

    def stop(self) -> None:
        """Gracefully stop trading bot execution with proper cleanup."""
        self.logger.info("Initiating trading bot shutdown...")
        self.running = False
        self._shutdown_event.set()

        if self.thread:
            try:
                self.thread.join(timeout=self.settings.shutdown_timeout)
                if self.thread.is_alive():
                    self.logger.warning("Force stopping trading bot after timeout.")
            except Exception as e:
                self.logger.error(f"Error during shutdown: {e}")

        self._cleanup()
        self.logger.info("Trading bot stopped successfully.")

    def _cleanup(self) -> None:
        """Perform cleanup operations during shutdown."""
        try:
            self.components.order_manager.cancel_all_orders(self.settings.symbol)
            self.components.market_data.close()
        except Exception as e:
            self.logger.error(f"Cleanup error: {e}")


def create_bot_components(client: Client, settings: Settings,
                          logger: logging.Logger) -> BotComponents:
    """Factory function to create bot components."""
    return BotComponents(
        market_data=MarketData(client, logger),
        order_manager=OrderManager(client, settings, logger),
        risk_manager=RiskManager(client, settings, logger),
        strategy=SMACrossoverStrategy(
            short_window=settings.strategy.short_window,
            long_window=settings.strategy.long_window
        )
    )


def main() -> None:
    """Application entry point with initialization and error handling."""
    try:
        settings = Settings()
        validate_settings(settings)

        logger = configure_logger('TradingBot', settings.log_level)

        client = Client(
            api_key=settings.exchange.api_key,
            api_secret=settings.exchange.api_secret
        )

        components = create_bot_components(client, settings, logger)

        health_check = HealthCheck(client, settings, logger)
        health_check.start_periodic_health_checks()

        bot = TradingBot(settings, components, logger)
        bot.start()

    except ConfigurationError as ce:
        logging.critical(f"Configuration error: {ce}", exc_info=True)
        raise
    except Exception as e:
        logging.critical(f"Fatal initialization error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
