from datetime import datetime
import pytz
from .get_balances import get_balances
from .get_last_price import get_last_price
from .send_telegram_message import send_telegram_message
from config.settings import (
    SYMBOLS,
    DETAILED_LOGGING,
    MIN_24H_VOLUME,
    MARKET_VOLATILITY_LIMIT
)

def get_24h_stats(symbol):
    """Get 24h trading statistics for a symbol"""
    try:
        from binance.client import Client
        client = Client("", "")  # Use empty strings for public API endpoints
        stats = client.get_ticker(symbol=symbol)
        return {
            'volume': float(stats['volume']) * float(stats['weightedAvgPrice']),
            'price_change': float(stats['priceChangePercent']),
            'high': float(stats['highPrice']),
            'low': float(stats['lowPrice'])
        }
    except Exception as e:
        return None

def send_asset_status():
    """Send detailed asset status report via Telegram"""
    try:
        balances = get_balances()
        if not balances:
            send_telegram_message("⚠️ Could not fetch balances")
            return

        # Calculate total portfolio value and prepare asset status
        total_value = float(balances.get('USDT', {}).get('free', 0.0))
        asset_status = []
        market_conditions = []

        for symbol in SYMBOLS:
            asset = symbol.replace('USDT', '')
            current_price = get_last_price(symbol)
            stats = get_24h_stats(symbol)

            if not current_price or not stats:
                asset_status.append(f"⚠️ {symbol}: Could not fetch data")
                continue

            # Asset position and value
            asset_balance = float(balances.get(asset, {}).get('free', 0.0))
            asset_value = asset_balance * current_price
            total_value += asset_value

            # Market conditions analysis
            volume_threshold = MIN_24H_VOLUME.get(symbol, 100000)
            volatility = abs(stats['price_change'])

            status_emoji = "🟢" if stats['volume'] >= volume_threshold else "🔴"
            if volatility > MARKET_VOLATILITY_LIMIT * 100:
                status_emoji = "⚠️"

            asset_info = [
                f"{status_emoji} {symbol}:",
                f"  Price: ${current_price:.2f}",
                f"  Balance: {asset_balance:.8f}",
                f"  Value: ${asset_value:.2f}"
            ]

            if DETAILED_LOGGING:
                asset_info.extend([
                    f"  24h Change: {stats['price_change']}%",
                    f"  24h Volume: ${stats['volume']:.2f}",
                    f"  24h High: ${stats['high']:.2f}",
                    f"  24h Low: ${stats['low']:.2f}"
                ])

            asset_status.append("\n".join(asset_info))

            # Add market condition warnings
            if stats['volume'] < volume_threshold:
                market_conditions.append(f"⚠️ {symbol}: Low volume (${stats['volume']:.2f})")
            if volatility > MARKET_VOLATILITY_LIMIT * 100:
                market_conditions.append(f"⚠️ {symbol}: High volatility ({volatility:.1f}%)")

        # Prepare and send message
        utc_now = datetime.now(pytz.UTC)
        message = [
            "💼 Asset Status Report",
            f"Time: {utc_now.strftime('%Y-%m-%d %H:%M:%S')} UTC",
            f"\nTotal Portfolio Value: ${total_value:.2f}",
            f"USDT Balance: ${balances.get('USDT', {}).get('free', 0.0):.2f}",
            "\nAsset Details:",
            *asset_status
        ]

        if market_conditions:
            message.extend(["\nMarket Conditions:", *market_conditions])

        send_telegram_message("\n".join(message))

    except Exception as e:
        send_telegram_message(f"⚠️ Error in asset status report: {str(e)}")
