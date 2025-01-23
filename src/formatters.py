# src/formatters.py
from decimal import Decimal
import locale

def format_currency(value: Decimal) -> str:
    locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
    return locale.currency(float(value), grouping=True)

def truncate_decimal(value: Decimal, precision: int) -> Decimal:
    return value.quantize(Decimal('1e-{}'.format(precision))) if value is not None else value