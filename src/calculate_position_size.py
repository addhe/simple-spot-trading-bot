from config.settings import MAX_INVESTMENT_PER_TRADE, STOP_LOSS_PERCENTAGE, TRAILING_STOP

def calculate_position_size(total_portfolio, current_price):
    """Menghitung ukuran posisi berdasarkan risk management"""
    max_position = total_portfolio * MAX_INVESTMENT_PER_TRADE
    return min(usdt_per_symbol, max_position)