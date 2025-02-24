from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from binance.client import Client
from binance.exceptions import BinanceAPIException
from config.settings import API_KEY, API_SECRET, BASE_URL
from src.logger import logger
from src.get_balances import get_balances
from src.database_manager import DatabaseManager
from src.trade_manager import TradeManager

# Initialize FastAPI app
app = FastAPI()

# Initialize Binance client
try:
    client = Client(api_key=API_KEY, api_secret=API_SECRET)
    if BASE_URL:
        client.API_URL = BASE_URL
    logger.info("Binance client initialized successfully.")
except Exception as e:
    logger.error(f"Failed to initialize Binance client: {e}")
    raise

# Initialize database and trade managers
db_manager = DatabaseManager('table_transactions.db')
trade_manager = TradeManager(db_manager, client)

# Define Pydantic models for request validation
class TradeRequest(BaseModel):
    symbol: str
    quantity: float

@app.post("/buy/")
async def buy_asset(request: TradeRequest):
    symbol = request.symbol
    quantity = request.quantity
    try:
        logger.info(f"Processing buy order for {symbol} with quantity {quantity}")
        trade_manager.execute_buy(symbol, quantity)
        logger.info(f"Buy order executed for {symbol}")
        return {"status": "success", "message": f"Buy order executed for {symbol}"}
    except BinanceAPIException as e:
        logger.error(f"Error executing buy: {e}")
        raise HTTPException(status_code=400, detail=f"Error executing buy: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during buy operation: {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

@app.post("/sell/")
async def sell_asset(request: TradeRequest):
    symbol = request.symbol
    quantity = request.quantity
    try:
        logger.info(f"Processing sell order for {symbol} with quantity {quantity}")
        trade_manager.execute_sell(symbol, quantity)
        logger.info(f"Sell order executed for {symbol}")
        return {"status": "success", "message": f"Sell order executed for {symbol}"}
    except BinanceAPIException as e:
        logger.error(f"Error executing sell: {e}")
        raise HTTPException(status_code=400, detail=f"Error executing sell: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during sell operation: {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

@app.get("/check_balance/")
async def check_balance():
    try:
        balances = get_balances()
        logger.info("Balances retrieved successfully")
        return balances
    except BinanceAPIException as e:
        logger.error(f"Error retrieving balances: {e}")
        raise HTTPException(status_code=400, detail=f"Error retrieving balances: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during balance check: {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)