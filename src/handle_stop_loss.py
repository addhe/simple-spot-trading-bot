from config.settings import TRAILING_STOP, TAKE_PROFIT, STOP_LOSS_PERCENTAGE

def handle_stop_loss(symbol, entry_price, current_price, highest_price):
    """
    Handle stop loss and take profit logic

    Args:
        symbol (str): Trading pair symbol (e.g., 'BTCUSDT')
        entry_price (float): Price at which the position was entered
        current_price (float): Current market price
        highest_price (float): Highest price since entry

    Returns:
        tuple: (should_sell, reason)
            - should_sell (bool): True if should sell, False otherwise
            - reason (str): Reason for selling if should_sell is True
    """
    # Calculate price change percentage
    price_change = ((current_price - entry_price) / entry_price) * 100

    # Check take profit
    take_profit = TAKE_PROFIT.get(symbol, 0.03) * 100  # Default 3%
    if price_change >= take_profit:
        return True, f"Take profit reached ({price_change:.2f}%)"

    # Check trailing stop
    trailing_stop = TRAILING_STOP.get(symbol, 0.015) * 100  # Default 1.5%
    if highest_price > entry_price:
        trailing_stop_price = highest_price * (1 - trailing_stop/100)
        if current_price <= trailing_stop_price:
            drop_from_high = ((highest_price - current_price) / highest_price) * 100
            return True, f"Trailing stop triggered ({drop_from_high:.2f}% drop from {highest_price:.2f})"

    # Check stop loss
    if price_change <= -STOP_LOSS_PERCENTAGE * 100:
        return True, f"Stop loss triggered ({price_change:.2f}%)"

    return False, None
