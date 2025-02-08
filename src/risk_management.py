import logging

# Function to manage risk for trades

def check_risk_management(available_balance, trade_amount, max_loss_percentage):
    max_loss = available_balance * max_loss_percentage
    if trade_amount > max_loss:
        logging.warning(f"Trade amount {trade_amount} exceeds maximum allowable loss of {max_loss}.")
        return False
    return True
