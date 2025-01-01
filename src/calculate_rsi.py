import logging
import pandas as pd

# Setup logger
logger = logging.getLogger(__name__)

def calculate_rsi(data, period=14):
    """Hitung RSI dari data harga."""
    try:
        df = pd.DataFrame(data)
        delta = df.diff(1)
        gain, loss = delta.copy(), delta.copy()
        gain[gain < 0] = 0
        loss[loss > 0] = 0
        avg_gain = gain.ewm(com=period-1, adjust=False).mean()
        avg_loss = abs(loss).ewm(com=period-1, adjust=False).mean()
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
        return rsi.iloc[-1]
    except Exception as e:
        logger.error(f"Error calculating RSI: {str(e)}")
        return None