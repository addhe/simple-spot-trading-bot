import time
from datetime import datetime
import pytz
from config.settings import (
    STATUS_INTERVAL,
    DETAILED_LOGGING,
    WIN_RATE_THRESHOLD,
    PROFIT_FACTOR_THRESHOLD
)
from .send_telegram_message import send_telegram_message
from .get_balances import get_balances
from .get_last_price import get_last_price

def calculate_performance_metrics(trades):
    """Calculate trading performance metrics"""
    if not trades:
        return None

    total_trades = len(trades)
    winning_trades = len([t for t in trades if t['profit'] > 0])
    win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0

    total_profit = sum([t['profit'] for t in trades if t['profit'] > 0])
    total_loss = abs(sum([t['profit'] for t in trades if t['profit'] < 0]))
    profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')

    return {
        'total_trades': total_trades,
        'win_rate': win_rate,
        'profit_factor': profit_factor
    }

def status_monitor(bot):
    """Monitor trading status and performance"""
    while bot.app_status['running'] and bot.app_status['status_thread']:
        try:
            # Get current balances
            balances = get_balances()
            if not balances:
                send_telegram_message("⚠️ Warning: Could not fetch balances")
                time.sleep(STATUS_INTERVAL)
                continue

            # Calculate total portfolio value
            total_value = float(balances.get('USDT', {}).get('free', 0.0))
            asset_values = []

            for symbol in bot.symbols:
                asset = symbol.replace('USDT', '')
                if asset in balances:
                    asset_balance = float(balances[asset]['free'])
                    price = get_last_price(symbol)
                    if price:
                        asset_value = asset_balance * price
                        total_value += asset_value
                        asset_values.append(f"{asset}: {asset_balance:.8f} (${asset_value:.2f})")

            # Calculate performance metrics
            metrics = calculate_performance_metrics(bot.trades)

            # Prepare status message
            status_msg = [
                "📊 Trading Bot Status Report",
                f"Time: {datetime.now(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC",
                f"Total Portfolio Value: ${total_value:.2f}",
                f"USDT Balance: ${balances.get('USDT', {}).get('free', 0.0):.2f}",
                "\nAsset Positions:",
                *asset_values
            ]

            if metrics and DETAILED_LOGGING:
                status_msg.extend([
                    "\nPerformance Metrics:",
                    f"Total Trades: {metrics['total_trades']}",
                    f"Win Rate: {metrics['win_rate']:.2f}%",
                    f"Profit Factor: {metrics['profit_factor']:.2f}"
                ])

                # Check performance thresholds
                if metrics['win_rate'] < WIN_RATE_THRESHOLD * 100:
                    status_msg.append(f"⚠️ Win rate below threshold ({WIN_RATE_THRESHOLD*100}%)")
                if metrics['profit_factor'] < PROFIT_FACTOR_THRESHOLD:
                    status_msg.append(f"⚠️ Profit factor below threshold ({PROFIT_FACTOR_THRESHOLD})")

            send_telegram_message("\n".join(status_msg))

        except Exception as e:
            send_telegram_message(f"⚠️ Error in status monitor: {str(e)}")

        time.sleep(STATUS_INTERVAL)
