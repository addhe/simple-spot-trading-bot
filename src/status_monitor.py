import time
from datetime import datetime
import pytz
from typing import Dict, Optional
from config.settings import (
    STATUS_INTERVAL,
    DETAILED_LOGGING,
    WIN_RATE_THRESHOLD,
    PROFIT_FACTOR_THRESHOLD,
    SYMBOLS
)
from .send_telegram_message import send_telegram_message
from .get_balances import get_balances
from .get_last_price import get_last_price

def format_balance_change(current: float, previous: float) -> str:
    """Format balance change with arrow indicators"""
    if previous == 0:
        return "🆕"
    change = ((current - previous) / previous) * 100
    if change > 0:
        return f"↗️ +{change:.2f}%"
    elif change < 0:
        return f"↘️ {change:.2f}%"
    return "→"

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
    previous_balances: Dict[str, float] = {}
    error_count = 0
    max_errors = 3
    error_sleep = 60  # Sleep 1 minute after error

    while bot.app_status['running']:
        try:
            if not bot.app_status['status_thread']:
                bot.logger.info("Restarting status monitor thread...")
                bot.app_status['status_thread'] = True
                error_count = 0

            # Get current balances
            balances = get_balances()
            if not balances:
                error_msg = "⚠️ Warning: Could not fetch balances. Will retry in 60 seconds."
                bot.logger.warning("Could not fetch balances")
                send_telegram_message(error_msg)
                time.sleep(error_sleep)
                error_count += 1
                if error_count >= max_errors:
                    bot.logger.error("Status monitor: Too many balance fetch errors")
                    send_telegram_message("🚨 Critical: Balance fetch failed multiple times. Check API connectivity.")
                    bot.app_status['status_thread'] = False
                continue

            # Calculate total portfolio value
            total_value = float(balances.get('USDT', {}).get('free', 0.0))
            total_locked = float(balances.get('USDT', {}).get('locked', 0.0))
            asset_values = []
            error_count = 0  # Reset error count on successful balance fetch

            # Process each trading pair
            for symbol in SYMBOLS:
                asset = symbol.replace('USDT', '')
                if asset in balances:
                    free_balance = float(balances[asset]['free'])
                    locked_balance = float(balances[asset]['locked'])
                    price = get_last_price(symbol)

                    if price:
                        asset_value = (free_balance + locked_balance) * price
                        total_value += asset_value

                        # Calculate balance change
                        previous_balance = previous_balances.get(asset, 0.0)
                        change_indicator = format_balance_change(free_balance, previous_balance)

                        # Update balance history
                        previous_balances[asset] = free_balance

                        # Format balance string
                        balance_str = (
                            f"{asset}: {free_balance:.8f}"
                            f" ({change_indicator})"
                            f" [${asset_value:.2f}]"
                        )
                        if locked_balance > 0:
                            balance_str += f" 🔒{locked_balance:.8f}"
                        asset_values.append(balance_str)

            # Calculate performance metrics
            metrics = calculate_performance_metrics(getattr(bot, 'trades', []))

            # Format status message
            current_time = datetime.now(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')

            status_msg = [
                "📊 Trading Bot Status Report",
                f"⏰ {current_time} UTC",
                "",
                "💰 Portfolio Summary:",
                f"Total Value: ${total_value:.2f}",
                f"USDT Available: ${balances.get('USDT', {}).get('free', 0.0):.2f}",
                f"USDT Locked: ${total_locked:.2f}",
                "",
                "🔐 Asset Positions:"
            ]
            status_msg.extend(asset_values)

            if metrics and DETAILED_LOGGING:
                status_msg.extend([
                    "",
                    "📈 Performance Metrics:",
                    f"Total Trades: {metrics['total_trades']}",
                    f"Win Rate: {metrics['win_rate']:.2f}%",
                    f"Profit Factor: {metrics['profit_factor']:.2f}"
                ])

                # Add performance warnings if needed
                if metrics['win_rate'] < WIN_RATE_THRESHOLD * 100:
                    status_msg.append(f"⚠️ Win rate below threshold ({WIN_RATE_THRESHOLD*100}%)")
                if metrics['profit_factor'] < PROFIT_FACTOR_THRESHOLD:
                    status_msg.append(f"⚠️ Profit factor below threshold ({PROFIT_FACTOR_THRESHOLD})")

            # Send status message to Telegram
            send_telegram_message("\n".join(status_msg))

        except Exception as e:
            bot.logger.error(f"Error in status monitor: {e}")
            send_telegram_message(f"⚠️ Error in status monitor: {str(e)}")
            error_count += 1
            if error_count >= max_errors:
                bot.logger.error("Status monitor: Too many consecutive errors")
                send_telegram_message("🚨 Critical: Status monitor encountered multiple errors. Check logs.")
                bot.app_status['status_thread'] = False
            time.sleep(error_sleep)
            continue

        time.sleep(STATUS_INTERVAL)
