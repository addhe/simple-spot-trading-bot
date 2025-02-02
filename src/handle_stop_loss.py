from config.settings import MAX_INVESTMENT_PER_TRADE, STOP_LOSS_PERCENTAGE, TRAILING_STOP

def handle_stop_loss(symbol, entry_price, current_price, highest_price):
    """Implementasi stop loss dan trailing stop"""
    if current_price <= entry_price * (1 - STOP_LOSS_PERCENTAGE):
        return True
    if highest_price * (1 - TRAILING_STOP) > current_price:
        return True
    return False