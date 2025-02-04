from config.settings import (
    MAX_INVESTMENT_PER_TRADE,
    MIN_24H_VOLUME,
    MIN_TRADE_AMOUNT
)

def calculate_position_size(symbol, available_balance, current_price, volume_24h):
    """
    Calculate the position size for a trade based on various constraints

    Args:
        symbol (str): Trading pair symbol (e.g., 'BTCUSDT')
        available_balance (float): Available USDT balance
        current_price (float): Current market price
        volume_24h (float): 24-hour trading volume in USDT

    Returns:
        tuple: (position_size, error_message)
            - position_size (float): Amount to trade in USDT, 0 if trade not possible
            - error_message (str): Error message if trade not possible, None otherwise
    """
    # Check minimum volume requirement
    min_required_volume = MIN_24H_VOLUME.get(symbol, 100000)  # Default 100k USDT
    if volume_24h < min_required_volume:
        return 0, f"Insufficient 24h volume (${volume_24h:.2f} < ${min_required_volume:.2f})"

    # Calculate maximum position size based on portfolio percentage
    max_position_size = available_balance * MAX_INVESTMENT_PER_TRADE

    # Check if we have enough balance for minimum trade
    min_trade = MIN_TRADE_AMOUNT.get(symbol, 0.001)  # Default to 0.001 BTC worth
    min_trade_value = min_trade * current_price

    if max_position_size < min_trade_value:
        return 0, f"Insufficient balance for minimum trade (${max_position_size:.2f} < ${min_trade_value:.2f})"

    # Ensure position size doesn't exceed 1% of 24h volume for liquidity
    max_volume_based_size = volume_24h * 0.01
    if max_position_size > max_volume_based_size:
        max_position_size = max_volume_based_size

    return max_position_size, None
