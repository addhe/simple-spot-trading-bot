from config.settings import (
    STOP_LOSS_PERCENTAGE,
    TRAILING_STOP,
    TAKE_PROFIT,
    PORTFOLIO_STOP_LOSS,
    DAILY_LOSS_LIMIT
)

def handle_stop_loss(symbol, entry_price, current_price, highest_price):
    """
    Handle stop loss and trailing stop logic
    Returns: (bool) True if should sell, False otherwise
    """
    # Get symbol specific trailing stop
    trailing_stop = TRAILING_STOP.get(symbol, 0.02)  # Default to 2% if not specified
    take_profit = TAKE_PROFIT.get(symbol, 1.02)  # Default to 2% if not specified

    # Calculate current profit/loss percentage
    profit_percentage = (current_price - entry_price) / entry_price

    # Check take profit
    if current_price >= entry_price * take_profit:
        return True, "Take profit reached"

    # Check stop loss
    if profit_percentage <= -STOP_LOSS_PERCENTAGE:
        return True, "Stop loss triggered"

    # Check trailing stop
    if highest_price > 0:
        trailing_stop_price = highest_price * (1 - trailing_stop)
        if current_price <= trailing_stop_price:
            return True, "Trailing stop triggered"

    return False, None
