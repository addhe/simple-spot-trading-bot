# src/bot.py
"""
Main trading bot module with enterprise-grade error handling and structured logging.
"""

import asyncio
import logging
from decimal import Decimal
from typing import Dict, Optional, List, Any

from aiohttp import ClientSession
from binance import AsyncClient, BinanceSocketManager
from binance.exceptions import BinanceAPIException

from config.settings import AppSettings
from src.strategy import TradingStrategy, StrategyFactory
from src.telegram_notifier import TelegramNotifier
from src.storage import DataStorage
from src.market_data import MarketData
from src.decorators import (
    AsyncRetry,
    AsyncErrorHandler,
    CircuitBreakerOpenError,
    MaxRetriesExceededError
)
from src.formatters import (
    format_currency,
    truncate_decimal,
    format_percentage
)
from src.models import OrderActivity

logger = logging.getLogger(__name__)

class OrderExecutor:
    """Handles order execution with advanced validation and circuit breaker"""
    
    def __init__(self, exchange, storage, notifier):
        self.exchange = exchange
        self.storage = storage
        self.notifier = notifier
        self.pending_orders: Dict[str, OrderActivity] = {}
        self.circuit_breaker_states: Dict[str, bool] = {}

    @AsyncErrorHandler(
        context="Order Execution",
        notify=True,
        log_level=logging.CRITICAL
    )
    @AsyncRetry(
        retries=3,
        delay=1.0,
        backoff_factor=1.5,
        exceptions=(BinanceAPIException, TimeoutError),
        circuit_breaker=True
    )
    async def execute_order(self, order: OrderActivity):
        """Execute and track an order with full validation"""
        if self.circuit_breaker_states.get(order.symbol, False):
            logger.warning(
                "Circuit breaker active for %s, skipping execution",
                order.symbol,
                extra={"symbol": order.symbol, "circuit_state": True}
            )
            return

        self.pending_orders[order.symbol] = order
        
        try:
            await self._validate_order(order)
            result = await self.exchange.create_order(order)
            await self.storage.save_activity(order)
            await self._send_order_notification(order, "executed")
            return result
        except BinanceAPIException as e:
            await self._handle_exchange_error(e, order)
            raise
        finally:
            self.pending_orders.pop(order.symbol, None)

    async def _validate_order(self, order: OrderActivity):
        """Comprehensive order validation with precision formatting"""
        base_asset = order.symbol.replace('USDT', '')
        balance = await self.exchange.get_balance(
            'USDT' if order.side == 'BUY' else base_asset
        )
        
        required = order.quantity * order.price if order.side == 'BUY' else order.quantity
        formatted_required = format_currency(required, precision=4, symbol=False)
        formatted_balance = format_currency(balance, precision=4, symbol=False)
        
        if balance < required:
            raise ValueError(
                f"Insufficient balance: Required {formatted_required}, Available {formatted_balance}"
            )

        symbol_info = self.exchange.symbol_info_cache[order.symbol]
        self._validate_quantity(order.quantity, symbol_info)
        self._validate_notional(order.quantity * order.price, symbol_info)

    def _validate_quantity(self, quantity: Decimal, symbol_info: Dict[str, Any]):
        """Validate order quantity against exchange limits"""
        min_qty = Decimal(symbol_info['min_quantity'])
        max_qty = Decimal(symbol_info['max_quantity'])
        
        if not (min_qty <= quantity <= max_qty):
            raise ValueError(
                f"Quantity {truncate_decimal(quantity, 6)} out of range "
                f"({format_decimal(min_qty, 6)}-{format_decimal(max_qty, 6)})"
            )

    def _validate_notional(self, notional: Decimal, symbol_info: Dict[str, Any]):
        """Validate notional value against exchange requirements"""
        min_notional = Decimal(symbol_info['min_notional'])
        if notional < min_notional:
            raise ValueError(
                f"Notional {format_currency(notional)} below minimum {format_currency(min_notional)}"
            )

    async def _send_order_notification(self, order: OrderActivity, status: str):
        """Send structured order notification with market context"""
        price_change = await self.exchange.get_24h_price_change(order.symbol)
        message = (
            f"📊 Order {status.upper()} - {order.symbol}\n"
            f"• Side: {order.side}\n"
            f"• Quantity: {truncate_decimal(order.quantity, 6)}\n"
            f"• Price: {format_currency(order.price)}\n"
            f"• 24h Change: {format_percentage(price_change)}\n"
            f"• SL: {format_currency(order.stop_loss) if order.stop_loss else 'N/A'}\n"
            f"• TP: {format_currency(order.take_profit) if order.take_profit else 'N/A'}"
        )
        await self.notifier.send_alert(message)

    async def _handle_exchange_error(self, error: BinanceAPIException, order: OrderActivity):
        """Handle exchange errors with circuit breaker state management"""
        error_msg = (
            f"🚨 Exchange Error ({order.symbol})\n"
            f"Code: {error.code}\n"
            f"Message: {error.message}"
        )
        logger.error(error_msg, extra={
            "error_code": error.code,
            "symbol": order.symbol,
            "error_type": "ExchangeAPIError"
        })
        
        # Update circuit breaker state
        self.circuit_breaker_states[order.symbol] = True
        await self.notifier.send_alert(error_msg)

class PortfolioManager:
    """Manages portfolio allocations with risk-adjusted calculations"""
    
    def __init__(self, exchange, settings: AppSettings):
        self.exchange = exchange
        self.settings = settings
        self.allocations: Dict[str, Decimal] = {}

    async def update_allocations(self):
        """Update portfolio allocations with formatted logging"""
        total_balance = await self.exchange.get_total_balance()
        risk_adjusted_balance = total_balance * (1 - self.settings.risk_reserve)
        per_pair_allocation = risk_adjusted_balance / len(self.settings.trading_pairs)
        
        self.allocations = {
            pair: truncate_decimal(per_pair_allocation, 4)
            for pair in self.settings.trading_pairs
        }
        
        logger.info(
            "Updated portfolio allocations",
            extra={
                "total_balance": float(total_balance),
                "risk_adjusted": float(risk_adjusted_balance),
                "per_pair_allocation": {k: float(v) for k, v in self.allocations.items()}
            }
        )

    async def calculate_position_size(self, pair: str, price: Decimal) -> Decimal:
        """Calculate optimal position size with risk management"""
        allocation = self.allocations.get(pair, Decimal(0))
        if allocation <= 0:
            return Decimal(0)

        symbol_info = self.exchange.symbol_info_cache[pair]
        raw_quantity = allocation / price
        quantity = truncate_decimal(raw_quantity, symbol_info['quantity_precision'])
        
        quantity = max(Decimal(symbol_info['min_quantity']), quantity)
        quantity = min(Decimal(symbol_info['max_quantity']), quantity)
        
        notional = quantity * price
        if notional < symbol_info['min_notional']:
            return Decimal(0)

        return quantity

class TradingBot:
    """Main trading bot class with enhanced error recovery and monitoring"""
    
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.exchange = BinanceExchangeClient(settings)
        self.storage = DataStorage(settings)
        self.notifier = TelegramNotifier()
        self.market_data = MarketData(self.exchange)
        self.strategies: Dict[str, TradingStrategy] = {}
        self.portfolio = PortfolioManager(self.exchange, settings)
        self.order_executor = OrderExecutor(
            self.exchange, 
            self.storage, 
            self.notifier
        )
        self.running = True

    @AsyncErrorHandler(context="Bot Initialization", log_level=logging.CRITICAL)
    async def initialize(self):
        """Initialize components with comprehensive error handling"""
        await self.exchange.initialize()
        await self._load_strategies()
        await self._restore_state()
        await self.portfolio.update_allocations()
        logger.info("✅ Bot initialization complete")

    async def _load_strategies(self):
        """Initialize trading strategies with validation"""
        for pair in self.settings.trading_pairs:
            self.strategies[pair] = StrategyFactory.create(
                self.settings.strategy_type,
                pair,
                self.market_data,
                self.settings.strategy_params
            )
            logger.debug(
                "Initialized strategy for %s",
                pair,
                extra={"strategy_params": self.settings.strategy_params}
            )

    async def _restore_state(self):
        """Restore previous state with transactional safety"""
        try:
            state = await self.storage.load_bot_state()
            recovery_tasks = [
                self.order_executor.execute_order(activity)
                for activity in state.get('activities', [])
            ]
            await asyncio.gather(*recovery_tasks)
            logger.info("State restoration completed", extra={"recovered_activities": len(recovery_tasks)})
        except Exception as e:
            logger.error("State restoration failed", exc_info=True)
            await self.notifier.send_alert(f"🛑 State restoration failed: {str(e)}")

    async def run(self):
        """Main trading loop with performance monitoring"""
        logger.info("🚀 Starting trading operations")
        async with ClientSession() as session:
            while self.running:
                try:
                    await self._execute_trading_cycle(session)
                    await asyncio.sleep(self._get_interval_seconds())
                except asyncio.CancelledError:
                    break
                except CircuitBreakerOpenError as e:
                    await self._handle_circuit_breaker(e)
                except Exception as e:
                    await self._handle_trading_error(e)

    async def _execute_trading_cycle(self, session: ClientSession):
        """Execute complete trading cycle with async optimizations"""
        await self.portfolio.update_allocations()
        tasks = [
            self._process_pair(pair, session)
            for pair in self.settings.trading_pairs
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _process_pair(self, pair: str, session: ClientSession):
        """Process trading logic for a single pair with market analysis"""
        try:
            price = await self._get_current_price(pair)
            strategy = self.strategies[pair]

            if await strategy.should_buy(price):
                await self._execute_buy(pair, price)
            elif await strategy.should_sell(price):
                await self._execute_sell(pair, price)

        except Exception as e:
            logger.error(
                "Error processing pair",
                extra={"pair": pair, "error": str(e)},
                exc_info=True
            )
            await self.notifier.send_alert(f"⚠️ Processing error for {pair}: {str(e)}")

    @AsyncRetry(retries=3, delay=1.0, exceptions=(BinanceAPIException,))
    async def _get_current_price(self, pair: str) -> Decimal:
        """Get current market price with enhanced validation"""
        ticker = await self.exchange.client.get_symbol_ticker(symbol=pair)
        return Decimal(ticker['price'])

    async def _execute_buy(self, pair: str, price: Decimal):
        """Execute buy order workflow with risk parameters"""
        quantity = await self.portfolio.calculate_position_size(pair, price)
        if quantity <= 0:
            logger.warning(
                "Invalid position size for buy order",
                extra={"pair": pair, "calculated_quantity": float(quantity)}
            )
            return

        risk_params = await self.strategies[pair].calculate_risk_parameters(price)
        order = OrderActivity(
            symbol=pair,
            side='BUY',
            quantity=quantity,
            price=price,
            stop_loss=risk_params['stop_loss'],
            take_profit=risk_params['take_profit']
        )
        
        await self.order_executor.execute_order(order)

    async def _execute_sell(self, pair: str, price: Decimal):
        """Execute sell order workflow with position validation"""
        # Implementation similar to buy workflow
        pass

    async def graceful_shutdown(self):
        """Perform graceful shutdown with resource cleanup"""
        logger.info("🛑 Initiating shutdown sequence")
        self.running = False
        
        await asyncio.gather(
            self.exchange.client.close_connection(),
            self.storage.close(),
            self.notifier.close()
        )
        
        logger.info("✅ Clean shutdown completed")

class BinanceExchangeClient:
    """Enhanced Binance exchange client with caching and circuit breaker"""
    
    def __init__(self, settings: AppSettings):
        self.client = AsyncClient(
            api_key=settings.exchange.api_key,
            api_secret=settings.exchange.api_secret.get_secret_value(),
            testnet=settings.exchange.testnet
        )
        self.symbol_info_cache: Dict[str, dict] = {}
        self.circuit_breaker = False

    @AsyncErrorHandler(context="Exchange Initialization")
    async def initialize(self):
        """Initialize exchange connection with automatic retry"""
        await self._cache_symbol_info()
        logger.info("Exchange connection established")

    async def _cache_symbol_info(self):
        """Cache symbol information with formatted logging"""
        exchange_info = await self.client.get_exchange_info()
        for symbol in exchange_info['symbols']:
            if symbol['symbol'] in AppSettings().trading_pairs:
                self.symbol_info_cache[symbol['symbol']] = self._parse_symbol_info(symbol)
        
        logger.debug(
            "Symbol info cached",
            extra={"cached_symbols": len(self.symbol_info_cache)}
        )

    def _parse_symbol_info(self, symbol_info: dict) -> dict:
        """Parse symbol information into structured format"""
        filters = {f['filterType']: f for f in symbol_info['filters']}
        return {
            'min_quantity': Decimal(filters['LOT_SIZE']['minQty']),
            'max_quantity': Decimal(filters['LOT_SIZE']['maxQty']),
            'quantity_precision': int(symbol_info['baseAssetPrecision']),
            'min_notional': Decimal(filters['MIN_NOTIONAL']['minNotional'])
        }

    @AsyncRetry(retries=3, delay=1.0)
    async def get_total_balance(self) -> Decimal:
        """Get total USDT balance with retry logic"""
        balance = await self.client.get_asset_balance(asset='USDT')
        return Decimal(balance['free'])

    @AsyncErrorHandler(context="Order Creation", notify=True)
    async def create_order(self, order: OrderActivity) -> dict:
        """Create market order with precision formatting"""
        precision = self.symbol_info_cache[order.symbol]['quantity_precision']
        return await self.client.create_order(
            symbol=order.symbol,
            side=order.side,
            type='MARKET',
            quantity=f"{order.quantity:.{precision}f}"
        )

if __name__ == "__main__":
    import sys
    from pathlib import Path
    
    sys.path.append(str(Path(__file__).parent.parent))
    
    async def main():
        from config.settings import AppSettings
        from src.utils import configure_logging
        
        settings = AppSettings()
        configure_logging(settings.logs_dir)
        
        bot = TradingBot(settings)
        try:
            await bot.initialize()
            await bot.run()
        finally:
            await bot.graceful_shutdown()

    asyncio.run(main())