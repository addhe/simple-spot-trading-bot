# src/bot.py
import asyncio
import logging
from decimal import Decimal
from typing import Dict, Optional, List

from aiohttp import ClientSession
from binance import AsyncClient, BinanceSocketManager
from binance.exceptions import BinanceAPIException

from config.settings import AppSettings
from src.strategy import TradingStrategy, StrategyFactory
from src.telegram_notifier import TelegramNotifier
from src.storage import DataStorage
from src.market_data import MarketData
from src.utils import (
    async_retry,
    format_currency,
    truncate_decimal,
    async_error_handler  # Impor yang diperbaiki
)
from src.models import OrderActivity

logger = logging.getLogger(__name__)

class OrderExecutor:
    """Handles order execution with validation and retry logic"""
    
    def __init__(self, exchange, storage, notifier):
        self.exchange = exchange
        self.storage = storage
        self.notifier = notifier
        self.pending_orders: Dict[str, OrderActivity] = {}

    @async_error_handler("Order execution failed", notify=True)
    @async_retry(max_retries=3, initial_delay=1.0)
    async def execute_order(self, order: OrderActivity):
        """Execute and track an order with full validation"""
        if order.symbol in self.pending_orders:
            logger.warning(f"Active order exists for {order.symbol}, skipping")
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
        """Comprehensive order validation"""
        # Balance validation
        base_asset = order.symbol.replace('USDT', '')
        balance = await self.exchange.get_balance(
            'USDT' if order.side == 'BUY' else base_asset
        )
        required = order.quantity * order.price if order.side == 'BUY' else order.quantity
        
        if balance < required:
            raise ValueError(
                f"Insufficient balance. Required: {required:.4f}, Available: {balance:.4f}"
            )

        # Exchange limits validation
        symbol_info = self.exchange.symbol_info_cache[order.symbol]
        if not (symbol_info['min_quantity'] <= order.quantity <= symbol_info['max_quantity']):
            raise ValueError(
                f"Quantity {order.quantity:.6f} out of allowed range "
                f"({symbol_info['min_quantity']:.6f}-{symbol_info['max_quantity']:.6f})"
            )

        # Notional value check
        notional = order.quantity * order.price
        if notional < symbol_info['min_notional']:
            raise ValueError(
                f"Notional value {notional:.2f} below minimum {symbol_info['min_notional']:.2f}"
            )

    async def _send_order_notification(self, order: OrderActivity, status: str):
        """Send detailed order notification"""
        message = (
            f"📊 Order {status.upper()} - {order.symbol}\n"
            f"• Side: {order.side}\n"
            f"• Quantity: {order.quantity:.6f}\n"
            f"• Price: {format_currency(order.price)}\n"
            f"• Stop Loss: {format_currency(order.stop_loss) if order.stop_loss else 'N/A'}\n"
            f"• Take Profit: {format_currency(order.take_profit) if order.take_profit else 'N/A'}"
        )
        await self.notifier.send_alert(message)

    async def _handle_exchange_error(self, error: BinanceAPIException, order: OrderActivity):
        """Handle exchange API errors"""
        error_msg = (
            f"🚨 Exchange Error ({order.symbol})\n"
            f"Code: {error.code}\n"
            f"Message: {error.message}"
        )
        logger.error(error_msg)
        await self.notifier.send_alert(error_msg)

class PortfolioManager:
    """Manages portfolio allocations and risk calculations"""
    
    def __init__(self, exchange, settings: AppSettings):
        self.exchange = exchange
        self.settings = settings
        self.allocations: Dict[str, Decimal] = {}

    async def update_allocations(self):
        """Update portfolio allocations based on current balance"""
        total_balance = await self.exchange.get_balance('USDT')
        risk_adjusted_balance = total_balance * (1 - self.settings.risk_reserve)
        per_pair_allocation = risk_adjusted_balance / len(self.settings.trading_pairs)
        
        self.allocations = {
            pair: truncate_decimal(per_pair_allocation, 2)
            for pair in self.settings.trading_pairs
        }
        logger.info(f"Updated allocations: {self.allocations}")

    async def calculate_position_size(self, pair: str, price: Decimal) -> Decimal:
        """Calculate optimal position size with risk management"""
        allocation = self.allocations.get(pair, Decimal(0))
        if allocation <= 0:
            return Decimal(0)

        symbol_info = self.exchange.symbol_info_cache[pair]
        raw_quantity = allocation / price
        quantity = truncate_decimal(raw_quantity, symbol_info['quantity_precision'])
        
        # Ensure quantity meets exchange requirements
        quantity = max(Decimal(symbol_info['min_quantity']), quantity)
        quantity = min(Decimal(symbol_info['max_quantity']), quantity)
        
        # Final notional check
        notional = quantity * price
        if notional < symbol_info['min_notional']:
            return Decimal(0)

        return quantity

class TradingBot:
    """Main trading bot class orchestrating all components"""
    
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

    async def initialize(self):
        """Initialize all components with proper error handling"""
        try:
            await self.exchange.initialize()
            await self._load_strategies()
            await self._restore_state()
            await self.portfolio.update_allocations()
            logger.info("✅ Bot initialization complete")
        except Exception as e:
            await self._handle_initialization_error(e)
            raise

    async def _load_strategies(self):
        """Initialize trading strategies dynamically"""
        for pair in self.settings.trading_pairs:
            self.strategies[pair] = StrategyFactory.create(
                self.settings.strategy_type,
                pair,
                self.market_data,
                self.settings.strategy_params
            )

    async def _restore_state(self):
        """Restore previous state from persistent storage"""
        try:
            state = await self.storage.load_bot_state()
            for activity in state.get('activities', []):
                await self.order_executor.execute_order(activity)
        except Exception as e:
            logger.error(f"State restoration failed: {e}")
            await self.notifier.notify_error(e, "state-restoration")

    async def run(self):
        """Main trading loop with health monitoring"""
        logger.info("🚀 Starting trading operations")
        async with ClientSession() as session:
            while self.running:
                try:
                    await self._execute_trading_cycle(session)
                    await asyncio.sleep(self._get_interval_seconds())
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    await self._handle_trading_error(e)

    def _get_interval_seconds(self) -> int:
        """Convert trading interval to seconds"""
        intervals = {'1m': 60, '5m': 300, '15m': 900, '1h': 3600, '4h': 14400}
        return intervals[self.settings.trading_interval]

    async def _execute_trading_cycle(self, session: ClientSession):
        """Execute complete trading cycle"""
        await self.portfolio.update_allocations()
        tasks = [
            self._process_pair(pair, session)
            for pair in self.settings.trading_pairs
        ]
        await asyncio.gather(*tasks)

    async def _process_pair(self, pair: str, session: ClientSession):
        """Process trading logic for a single pair"""
        try:
            price = await self._get_current_price(pair)
            strategy = self.strategies[pair]

            if await strategy.should_buy(price):
                await self._execute_buy(pair, price)
            elif await strategy.should_sell(price):
                await self._execute_sell(pair, price)

        except Exception as e:
            logger.error(f"Error processing {pair}: {e}")
            await self.notifier.notify_error(e, f"pair-processing-{pair}")

    @async_retry(max_retries=3, initial_delay=1.0)
    async def _get_current_price(self, pair: str) -> Decimal:
        """Get current market price with retry logic"""
        ticker = await self.exchange.client.get_symbol_ticker(symbol=pair)
        return Decimal(ticker['price'])

    async def _execute_buy(self, pair: str, price: Decimal):
        """Execute buy order workflow"""
        quantity = await self.portfolio.calculate_position_size(pair, price)
        if quantity <= 0:
            return

        order = OrderActivity(
            symbol=pair,
            side='BUY',
            quantity=quantity,
            price=price,
            stop_loss=await self.strategies[pair].calculate_risk_parameters(price)['stop_loss'],
            take_profit=await self.strategies[pair].calculate_risk_parameters(price)['take_profit']
        )
        await self.order_executor.execute_order(order)

    async def _execute_sell(self, pair: str, price: Decimal):
        """Execute sell order workflow"""
        # Implement sell logic similar to buy
        pass

    async def graceful_shutdown(self):
        """Perform graceful shutdown sequence"""
        logger.info("🛑 Initiating shutdown sequence")
        self.running = False
        
        shutdown_tasks = [
            self.exchange.client.close_connection(),
            self.storage.close(),
            self.notifier.close()
        ]
        
        await asyncio.gather(*shutdown_tasks)
        logger.info("✅ Clean shutdown completed")

class BinanceExchangeClient:
    """Binance exchange client implementation"""
    
    def __init__(self, settings: AppSettings):
        self.client = AsyncClient(
            api_key=settings.exchange.api_key,
            api_secret=settings.exchange.api_secret.get_secret_value(),
            testnet=settings.exchange.testnet
        )
        self.symbol_info_cache: Dict[str, dict] = {}

    async def initialize(self):
        """Initialize exchange connection and cache symbol info"""
        await self._cache_symbol_info()

    async def _cache_symbol_info(self):
        """Cache symbol information from exchange"""
        exchange_info = await self.client.get_exchange_info()
        for symbol in exchange_info['symbols']:
            if symbol['symbol'] in AppSettings().trading_pairs:
                self.symbol_info_cache[symbol['symbol']] = self._parse_symbol_info(symbol)

    def _parse_symbol_info(self, symbol_info: dict) -> dict:
        """Parse and normalize symbol information"""
        filters = {f['filterType']: f for f in symbol_info['filters']}
        return {
            'min_quantity': Decimal(filters['LOT_SIZE']['minQty']),
            'max_quantity': Decimal(filters['LOT_SIZE']['maxQty']),
            'quantity_precision': int(symbol_info['baseAssetPrecision']),
            'min_notional': Decimal(filters['MIN_NOTIONAL']['minNotional'])
        }

    @async_retry(max_retries=3, initial_delay=1.0)
    async def get_balance(self, asset: str) -> Decimal:
        """Get available balance for an asset"""
        balance = await self.client.get_asset_balance(asset=asset)
        return Decimal(balance['free'])

    async def create_order(self, order: OrderActivity) -> dict:
        """Create market order on exchange"""
        return await self.client.create_order(
            symbol=order.symbol,
            side=order.side,
            type='MARKET',
            quantity=f"{order.quantity:.{self.symbol_info_cache[order.symbol]['quantity_precision']}f}"
        )

if __name__ == "__main__":
    import sys
    from pathlib import Path
    
    # Add project root to PYTHONPATH
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