# src/models.py
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

@dataclass
class OrderActivity:
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None