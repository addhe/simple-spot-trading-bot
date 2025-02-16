import time
from prometheus_client import Counter, Gauge, Histogram, start_http_server
import newrelic.agent

# Prometheus metrics
TRADE_COUNTER = Counter('trading_bot_trades_total', 'Total number of trades', ['symbol', 'type'])
PROFIT_GAUGE = Gauge('trading_bot_profit', 'Current profit/loss', ['symbol'])
TRADE_DURATION = Histogram('trading_bot_trade_duration_seconds', 'Time taken for trade execution')
ERROR_COUNTER = Counter('trading_bot_errors_total', 'Total number of errors', ['type'])
BALANCE_GAUGE = Gauge('trading_bot_balance', 'Current balance', ['asset'])
API_LATENCY = Histogram('trading_bot_api_latency_seconds', 'API request latency')

class MetricsCollector:
    def __init__(self, port=8000):
        """Initialize metrics collector"""
        self.port = port
        start_http_server(port)

    @newrelic.agent.background_task()
    def record_trade(self, symbol: str, trade_type: str, amount: float, price: float):
        """Record trade metrics"""
        TRADE_COUNTER.labels(symbol=symbol, type=trade_type).inc()
        
        # Record to New Relic
        newrelic.agent.record_custom_metric(
            f'Custom/Trade/{symbol}/{trade_type}',
            amount * price
        )

    @newrelic.agent.background_task()
    def update_profit(self, symbol: str, profit: float):
        """Update profit metrics"""
        PROFIT_GAUGE.labels(symbol=symbol).set(profit)
        
        # Record to New Relic
        newrelic.agent.record_custom_metric(
            f'Custom/Profit/{symbol}',
            profit
        )

    @newrelic.agent.background_task()
    def record_error(self, error_type: str):
        """Record error metrics"""
        ERROR_COUNTER.labels(type=error_type).inc()
        
        # Record to New Relic
        newrelic.agent.record_custom_metric(
            f'Custom/Errors/{error_type}',
            1
        )

    @newrelic.agent.background_task()
    def update_balance(self, asset: str, balance: float):
        """Update balance metrics"""
        BALANCE_GAUGE.labels(asset=asset).set(balance)
        
        # Record to New Relic
        newrelic.agent.record_custom_metric(
            f'Custom/Balance/{asset}',
            balance
        )

    def measure_api_latency(self):
        """Context manager for measuring API latency"""
        class LatencyTimer:
            def __init__(self, collector):
                self.collector = collector
                self.start_time = None

            def __enter__(self):
                self.start_time = time.time()
                return self

            @newrelic.agent.background_task()
            def __exit__(self, exc_type, exc_val, exc_tb):
                duration = time.time() - self.start_time
                API_LATENCY.observe(duration)
                
                # Record to New Relic
                newrelic.agent.record_custom_metric(
                    'Custom/API/Latency',
                    duration
                )

        return LatencyTimer(self)

# Initialize metrics collector
metrics = MetricsCollector()
