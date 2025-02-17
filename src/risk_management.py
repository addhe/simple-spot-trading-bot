import logging
from src.logger import logger

# Function to manage risk for trades

def check_risk_management(available_balance, trade_amount, max_loss_percentage):
    """
    Check if the trade amount is within acceptable risk parameters
    """
    logger.debug(f"Risk Management Check:")
    logger.debug(f"Available Balance: ${available_balance:.2f}")
    logger.debug(f"Proposed Trade Amount: ${trade_amount:.2f}")
    logger.debug(f"Max Loss Percentage: {max_loss_percentage * 100}%")

    max_loss = available_balance * max_loss_percentage
    logger.debug(f"Maximum Allowable Loss: ${max_loss:.2f}")

    if trade_amount > max_loss:
        logger.warning(f"Trade amount ${trade_amount:.2f} exceeds maximum allowable loss of ${max_loss:.2f}")
        return False
    
    logger.debug(f"Trade amount within risk parameters")
    return True
