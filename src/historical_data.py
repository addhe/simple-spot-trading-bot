from datetime import datetime, timedelta
from src.logger import logger

class HistoricalDataCollector:
    def __init__(self, client, db_manager):
        self.client = client
        self.db_manager = db_manager
        self.logger = logger

    def collect_historical_data(self, symbol, interval='1h', lookback_days=30):
        """
        Collect historical kline data for a symbol
        """
        try:
            # Calculate start time (30 days ago)
            start_time = int((datetime.now() - timedelta(days=lookback_days)).timestamp() * 1000)
            
            # Get kline data from Binance
            klines = self.client.get_klines(
                symbol=symbol,
                interval=interval,
                startTime=start_time,
                limit=500  # Maximum limit from Binance
            )
            
            if klines:
                self.logger.info(f"Retrieved {len(klines)} klines for {symbol}")
                # Store in database
                self.db_manager.store_historical_data(symbol, klines)
                return True
            else:
                self.logger.warning(f"No historical data retrieved for {symbol}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error collecting historical data for {symbol}: {e}")
            return False

    def update_recent_data(self, symbols, interval='1h'):
        """
        Update recent historical data for all symbols
        """
        for symbol in symbols:
            try:
                # Get most recent 100 candles
                klines = self.client.get_klines(
                    symbol=symbol,
                    interval=interval,
                    limit=100
                )
                
                if klines:
                    self.db_manager.store_historical_data(symbol, klines)
                    self.logger.debug(f"Updated recent data for {symbol}")
                else:
                    self.logger.warning(f"No recent data retrieved for {symbol}")
                    
            except Exception as e:
                self.logger.error(f"Error updating recent data for {symbol}: {e}")
                continue
