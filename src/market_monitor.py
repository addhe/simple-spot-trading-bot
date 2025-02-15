from src.logger import logger

# Function to monitor market conditions

def monitor_market_conditions(current_price, required_price):
    if current_price < required_price:
        logger.info(f"Market condition favorable: Current price {current_price} is below required price {required_price}.")
    else:
        logger.info(f"Market condition unfavorable: Current price {current_price} is above required price {required_price}.")

def monitor_market_conditions(current_price, required_price):
    if current_price < required_price:
        logger.info(f"Market condition favorable: Current price {current_price} is below required price {required_price}.")
    else:
        logger.info(f"Market condition unfavorable: Current price {current_price} is above required price {required_price}.")
