from config.settings import (
    MAX_INVESTMENT_PER_TRADE,
    MIN_USDT_BALANCE,
    MAX_POSITIONS,
    MIN_24H_VOLUME
)

def calculate_position_size(symbol, available_balance, current_price, volume_24h):
    """
    Calculate position size based on risk management rules
    Returns: (float) position size in quote currency (USDT)
    """
    try:
        # Check minimum required volume
        min_required_volume = MIN_24H_VOLUME.get(symbol, 100000)  # Default 100k USDT if not specified
        if volume_24h < min_required_volume:
            return 0, "24h volume too low"

        # Check minimum balance requirement
        if available_balance < MIN_USDT_BALANCE:
            return 0, "Balance below minimum required"

        # Calculate maximum position size based on portfolio percentage
        max_position = available_balance * MAX_INVESTMENT_PER_TRADE

        # Calculate position size in quote currency (USDT)
        position_size = min(max_position, available_balance - MIN_USDT_BALANCE)

        # Round down to avoid precision errors
        position_size = float(format(position_size, '.8f'))

        return position_size, None

    except Exception as e:
        return 0, f"Error calculating position size: {str(e)}"
