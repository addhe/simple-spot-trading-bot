import functools
from tenacity import retry, stop_after_attempt, wait_exponential
from binance.exceptions import BinanceAPIException
import requests


def retry_on_api_error(func):
    @functools.wraps(func)
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=lambda e: isinstance(e, (BinanceAPIException, requests.exceptions.RequestException))
    )
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper
