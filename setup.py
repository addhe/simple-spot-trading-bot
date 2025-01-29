# setup.py
from setuptools import setup, find_packages

setup(
    name="crypto_trading_bot",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "python-binance",
        "pandas",
        "cachetools",
        "ratelimit",
        "pydantic",
        "requests"
    ],
)