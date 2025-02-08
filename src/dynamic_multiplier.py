import logging

# Function to dynamically adjust the buy multiplier based on market conditions

def adjust_buy_multiplier(current_price, historical_prices):
    if not historical_prices:
        return 0.99  # Default multiplier if no historical data
    price_change = (current_price - historical_prices[-1]) / historical_prices[-1]
    if price_change > 0.02:  # If price increased by more than 2%
        return 0.97  # More aggressive buying
    elif price_change < -0.02:  # If price decreased by more than 2%
        return 0.95  # More conservative buying
    return 0.99  # Default multiplier
