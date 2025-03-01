from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from binance.client import Client
from src.trade_manager import TradeManager
from src.db_manager import DatabaseManager
from src.get_balances import get_balances
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

from config.settings import (
    API_KEY,
    API_SECRET,
    BASE_URL,
    TELEGRAM_TOKEN,
    TELEGRAM_GROUP_ID,
    SYMBOL_CONFIG,
    INTERVAL,
    CACHE_LIFETIME,
    BUY_MULTIPLIER,
    SELL_MULTIPLIER,
    MIN_VOLUME_MULTIPLIER,
    MIN_POSITION_SIZE,
    MIN_24H_VOLUME,
    MARKET_VOLATILITY_LIMIT,
    TRAILING_STOP,
    TAKE_PROFIT,
    MIN_TRADE_AMOUNT,
    MAX_INVESTMENT_PER_TRADE,
    RSI_OVERSOLD,
    MIN_USDT_BALANCE,
    SYMBOLS
)

app = FastAPI()

class TradeRequest(BaseModel):
    symbol: str
    usdt_amount: float
    percentage: float = None  # Optional percentage of holdings to sell

class BalanceResponse(BaseModel):
    balance: float

class AssetRequest(BaseModel):
    symbol: str

# Initialize Binance client
client = Client(API_KEY, API_SECRET)

# Initialize database and trade manager
db_manager = DatabaseManager()
trade_manager = TradeManager(db_manager=db_manager, client=client)

@app.post("/buy")
async def buy_asset(request: TradeRequest):
    try:
        # Get current price and log it
        ticker = client.get_symbol_ticker(symbol=request.symbol)
        current_price = float(ticker['price'])
        logger.info(f"Current price for {request.symbol}: {current_price}")

        # Get symbol info
        symbol_info = client.get_symbol_info(request.symbol)
        min_notional = float(next((f['minNotional'] for f in symbol_info['filters'] if f['filterType'] == 'MIN_NOTIONAL'), 10))

        # Adjust USDT amount if needed to meet minimum notional
        usdt_amount = request.usdt_amount
        if usdt_amount < min_notional:
            usdt_amount = min_notional + 0.1  # Add a small buffer to ensure we meet the minimum
            logger.info(f"Adjusting USDT amount from {request.usdt_amount} to {usdt_amount} to meet minimum notional requirement")

        # Calculate quantity and log it
        quantity = usdt_amount / current_price
        logger.info(f"Calculated quantity to buy: {quantity} {request.symbol}")

        # Execute buy and get result
        result = trade_manager.execute_buy(request.symbol, quantity)
        logger.info(f"Buy execution result: {result}")

        return {
            "message": result,
            "adjusted_usdt": usdt_amount if usdt_amount > request.usdt_amount else None,
            "quantity": quantity,
            "price": current_price
        }
    except Exception as e:
        logger.error(f"Error in buy_asset: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/sell")
async def sell_asset(request: TradeRequest):
    try:
        # Get current price
        ticker = client.get_symbol_ticker(symbol=request.symbol)
        current_price = float(ticker['price'])
        logger.info(f"Current price for {request.symbol}: {current_price}")

        # Get symbol info for precision and limits
        symbol_info = client.get_symbol_info(request.symbol)
        min_notional = float(next((f['minNotional'] for f in symbol_info['filters'] if f['filterType'] == 'MIN_NOTIONAL'), 10))

        # Get current balance
        balances = get_balances(client)
        asset = request.symbol.replace('USDT', '')
        available_balance = float(balances.get(asset, {}).get('free', 0))
        logger.info(f"Available balance: {available_balance} {asset}")

        # Calculate quantity to sell
        if request.percentage is not None:
            # Sell percentage of holdings
            if request.percentage <= 0 or request.percentage > 100:
                raise HTTPException(status_code=400, detail="Percentage must be between 0 and 100")
            quantity = available_balance * (request.percentage / 100)
        else:
            # Sell by USDT amount
            quantity = min(request.usdt_amount / current_price, available_balance)

        # Check if total value meets minimum notional
        total_value = quantity * current_price
        if total_value < min_notional:
            # Try to adjust to minimum notional if possible
            min_quantity = min_notional / current_price
            if min_quantity <= available_balance:
                logger.info(f"Adjusting quantity to meet minimum notional value ({min_notional} USDT)")
                quantity = min_quantity
            else:
                error_msg = f"Order value ({total_value:.2f} USDT) is below minimum ({min_notional} USDT) and not enough balance to adjust"
                logger.error(error_msg)
                raise HTTPException(status_code=400, detail=error_msg)

        logger.info(f"Calculated quantity to sell: {quantity} {request.symbol}")

        # Get lot size filter for precision
        lot_size_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
        if lot_size_filter:
            step_size = float(lot_size_filter['stepSize'])
            # Round quantity to valid step size
            quantity = round(quantity - (quantity % step_size), len(str(step_size).split('.')[1]))
            logger.info(f"Adjusted quantity to step size: {quantity} {request.symbol}")

        # Execute sell
        result = trade_manager.execute_sell(request.symbol, quantity)
        logger.info(f"Sell execution result: {result}")

        return {
            "message": result,
            "quantity": quantity,
            "price": current_price,
            "total_usdt": quantity * current_price,
            "available_balance": available_balance,
            "min_notional": min_notional
        }
    except Exception as e:
        logger.error(f"Error in sell_asset: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/check_balance", response_model=BalanceResponse)
async def check_balance():
    try:
        balances = get_balances(client)
        return BalanceResponse(balance=balances['USDT']['free'])  # Adjust based on actual response structure
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/get_assets")
async def get_assets():
    try:
        balances = get_balances(client)
        assets = {symbol: balances.get(symbol.replace('USDT', ''), {}).get('free', 0) for symbol in SYMBOLS}
        return assets
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/get_asset")
async def get_specific_asset(request: AssetRequest):
    try:
        # Get the symbol from request
        symbol = request.symbol.upper()

        # Get all balances
        balances = get_balances(client)

        # Check if the requested symbol exists in balances
        if symbol in balances:
            return {
                symbol: {
                    "free": balances[symbol]["free"],
                    "locked": balances[symbol]["locked"],
                    "total": balances[symbol]["total"]
                }
            }
        else:
            # If symbol not found, return zero balance
            return {
                symbol: {
                    "free": 0,
                    "locked": 0,
                    "total": 0
                }
            }
    except Exception as e:
        logger.error(f"Error in get_specific_asset: {e}")
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
