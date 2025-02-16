import os
import asyncio
import psutil
import pandas as pd
import plotly.graph_objs as go
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import dash
from dash import html, dcc
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
from apscheduler.schedulers.background import BackgroundScheduler
from src.logger import logger
from src.database_manager import db_manager
from src.monitoring import metrics

class StatusMonitor:
    def __init__(self, update_interval: int = 60):
        self.update_interval = update_interval
        self.scheduler = BackgroundScheduler()
        self.market_conditions: Dict[str, str] = {}
        self.system_metrics: Dict[str, float] = {}
        self.trading_metrics: Dict[str, Dict] = {}
        self.alerts: List[Dict] = []
        
        # Initialize Dash app
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.DARKLY])
        self.setup_dashboard()
        
        # Start background jobs
        self.scheduler.add_job(
            self.update_metrics,
            'interval',
            seconds=update_interval
        )
        self.scheduler.start()

    def setup_dashboard(self):
        """Setup Dash dashboard layout"""
        self.app.layout = dbc.Container([
            dbc.Row([
                dbc.Col(html.H1("Trading Bot Dashboard", className="text-center mb-4"), width=12)
            ]),
            
            # Alerts Section
            dbc.Row([
                dbc.Col(
                    dbc.Card([
                        dbc.CardHeader("Active Alerts"),
                        dbc.CardBody(id="alerts-content")
                    ]),
                    width=12
                )
            ], className="mb-4"),
            
            # Market Overview
            dbc.Row([
                dbc.Col(
                    dbc.Card([
                        dbc.CardHeader("Market Overview"),
                        dbc.CardBody([
                            dcc.Graph(id="market-overview")
                        ])
                    ]),
                    width=6
                ),
                
                # Trading Performance
                dbc.Col(
                    dbc.Card([
                        dbc.CardHeader("Trading Performance"),
                        dbc.CardBody([
                            dcc.Graph(id="trading-performance")
                        ])
                    ]),
                    width=6
                )
            ], className="mb-4"),
            
            # System Metrics
            dbc.Row([
                dbc.Col(
                    dbc.Card([
                        dbc.CardHeader("System Metrics"),
                        dbc.CardBody([
                            dcc.Graph(id="system-metrics")
                        ])
                    ]),
                    width=12
                )
            ]),
            
            dcc.Interval(
                id='interval-component',
                interval=self.update_interval * 1000,
                n_intervals=0
            )
        ], fluid=True)
        
        self.setup_callbacks()

    def setup_callbacks(self):
        """Setup Dash callbacks for real-time updates"""
        @self.app.callback(
            [Output("alerts-content", "children"),
             Output("market-overview", "figure"),
             Output("trading-performance", "figure"),
             Output("system-metrics", "figure")],
            [Input("interval-component", "n_intervals")]
        )
        def update_dashboard(n):
            return (
                self.render_alerts(),
                self.render_market_overview(),
                self.render_trading_performance(),
                self.render_system_metrics()
            )

    async def update_metrics(self):
        """Update all metrics"""
        try:
            await self.update_market_conditions()
            await self.update_trading_metrics()
            self.update_system_metrics()
            await self.check_alerts()
        except Exception as e:
            logger.error(f"Error updating metrics: {str(e)}")
            metrics.record_error("metrics_update")

    async def update_market_conditions(self):
        """Update market conditions for all symbols"""
        try:
            symbols = ['ETHUSDT', 'SOLUSDT']  # Add more symbols as needed
            for symbol in symbols:
                volatility = await self.calculate_volatility(symbol)
                trend = await self.calculate_trend(symbol)
                volume = await self.calculate_volume_profile(symbol)
                
                self.market_conditions[symbol] = {
                    'volatility': volatility,
                    'trend': trend,
                    'volume': volume
                }
        except Exception as e:
            logger.error(f"Error updating market conditions: {str(e)}")

    async def calculate_volatility(self, symbol: str) -> str:
        """Calculate market volatility"""
        try:
            data = await db_manager.get_market_data(
                symbol,
                datetime.utcnow() - timedelta(days=1),
                datetime.utcnow()
            )
            
            if not data:
                return "Unknown"
            
            df = pd.DataFrame(data)
            returns = df['close'].pct_change()
            volatility = returns.std() * (252 ** 0.5)  # Annualized volatility
            
            if volatility > 0.8:
                return "Extreme"
            elif volatility > 0.5:
                return "High"
            elif volatility > 0.2:
                return "Moderate"
            else:
                return "Low"
        except Exception:
            return "Unknown"

    async def calculate_trend(self, symbol: str) -> str:
        """Calculate market trend"""
        try:
            data = await db_manager.get_market_data(
                symbol,
                datetime.utcnow() - timedelta(days=1),
                datetime.utcnow()
            )
            
            if not data:
                return "Unknown"
            
            df = pd.DataFrame(data)
            sma_short = df['close'].rolling(window=20).mean()
            sma_long = df['close'].rolling(window=50).mean()
            
            if sma_short.iloc[-1] > sma_long.iloc[-1] * 1.02:
                return "Strong Uptrend"
            elif sma_short.iloc[-1] > sma_long.iloc[-1]:
                return "Uptrend"
            elif sma_short.iloc[-1] < sma_long.iloc[-1] * 0.98:
                return "Strong Downtrend"
            elif sma_short.iloc[-1] < sma_long.iloc[-1]:
                return "Downtrend"
            else:
                return "Sideways"
        except Exception:
            return "Unknown"

    async def calculate_volume_profile(self, symbol: str) -> str:
        """Calculate volume profile"""
        try:
            data = await db_manager.get_market_data(
                symbol,
                datetime.utcnow() - timedelta(hours=24),
                datetime.utcnow()
            )
            
            if not data:
                return "Unknown"
            
            df = pd.DataFrame(data)
            avg_volume = df['volume'].mean()
            current_volume = df['volume'].iloc[-1]
            
            if current_volume > avg_volume * 2:
                return "Very High"
            elif current_volume > avg_volume * 1.5:
                return "High"
            elif current_volume < avg_volume * 0.5:
                return "Low"
            else:
                return "Normal"
        except Exception:
            return "Unknown"

    async def update_trading_metrics(self):
        """Update trading metrics"""
        try:
            for symbol in ['ETHUSDT', 'SOLUSDT']:  # Add more symbols as needed
                trades = await db_manager.get_trade_history(symbol, limit=100)
                if trades:
                    df = pd.DataFrame(trades)
                    
                    self.trading_metrics[symbol] = {
                        'total_trades': len(df),
                        'win_rate': len(df[df['profit_loss'] > 0]) / len(df),
                        'avg_profit': df[df['profit_loss'] > 0]['profit_loss'].mean(),
                        'avg_loss': df[df['profit_loss'] < 0]['profit_loss'].mean(),
                        'total_pnl': df['profit_loss'].sum()
                    }
        except Exception as e:
            logger.error(f"Error updating trading metrics: {str(e)}")

    def update_system_metrics(self):
        """Update system metrics"""
        try:
            self.system_metrics = {
                'cpu_usage': psutil.cpu_percent(),
                'memory_usage': psutil.virtual_memory().percent,
                'disk_usage': psutil.disk_usage('/').percent,
                'network_io': sum(psutil.net_io_counters()[:2])
            }
        except Exception as e:
            logger.error(f"Error updating system metrics: {str(e)}")

    async def check_alerts(self):
        """Check for alert conditions"""
        try:
            # Check system alerts
            if self.system_metrics['cpu_usage'] > 80:
                self.add_alert("High CPU Usage", "warning")
            if self.system_metrics['memory_usage'] > 80:
                self.add_alert("High Memory Usage", "warning")
            
            # Check market alerts
            for symbol, conditions in self.market_conditions.items():
                if conditions['volatility'] == "Extreme":
                    self.add_alert(f"Extreme Volatility: {symbol}", "danger")
                if conditions['volume'] == "Very High":
                    self.add_alert(f"Unusual Volume: {symbol}", "warning")
            
            # Check trading alerts
            for symbol, metrics in self.trading_metrics.items():
                if metrics.get('win_rate', 0) < 0.3:
                    self.add_alert(f"Low Win Rate: {symbol}", "danger")
                if metrics.get('total_pnl', 0) < -0.05:  # 5% drawdown
                    self.add_alert(f"High Drawdown: {symbol}", "danger")
            
        except Exception as e:
            logger.error(f"Error checking alerts: {str(e)}")

    def add_alert(self, message: str, level: str):
        """Add a new alert"""
        alert = {
            'message': message,
            'level': level,
            'timestamp': datetime.utcnow()
        }
        self.alerts.append(alert)
        
        # Keep only last 100 alerts
        if len(self.alerts) > 100:
            self.alerts = self.alerts[-100:]
        
        # Log alert
        logger.warning(f"Alert: {message}")
        
        # Send to monitoring system
        metrics.record_alert(message, level)

    def render_alerts(self):
        """Render alerts for dashboard"""
        alerts_list = []
        for alert in reversed(self.alerts[-5:]):  # Show last 5 alerts
            alerts_list.append(
                dbc.Alert(
                    f"{alert['timestamp'].strftime('%H:%M:%S')} - {alert['message']}",
                    color=alert['level'],
                    dismissable=True
                )
            )
        return alerts_list

    def render_market_overview(self):
        """Render market overview graph"""
        # Implementation for market overview visualization
        pass

    def render_trading_performance(self):
        """Render trading performance graph"""
        # Implementation for trading performance visualization
        pass

    def render_system_metrics(self):
        """Render system metrics graph"""
        # Implementation for system metrics visualization
        pass

    def start(self, host: str = '0.0.0.0', port: int = 8050):
        """Start the dashboard server"""
        self.app.run_server(host=host, port=port)

    def stop(self):
        """Stop the status monitor"""
        self.scheduler.shutdown()

# Initialize status monitor
status_monitor = StatusMonitor()
