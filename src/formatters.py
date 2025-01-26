# src/formatters.py
"""
Modul untuk handling formatting data keuangan dan numerik
dengan presisi tinggi menggunakan Decimal.
"""

from decimal import Decimal, ROUND_DOWN
import locale
from typing import Optional

class FormatterConfig:
    """Konfigurasi default untuk formatter"""
    DEFAULT_LOCALE = 'en_US.UTF-8'
    CURRENCY_FORMAT = {
        'en_US.UTF-8': ('$', 2),
        'id_ID.UTF-8': ('Rp', 0),
        'de_DE.UTF-8': ('€', 2)
    }
    SAFE_MODE = True  # Mencegah perubahan locale global

def format_currency(
    value: Decimal,
    precision: int = 2,
    locale_str: str = FormatterConfig.DEFAULT_LOCALE,
    symbol: bool = True
) -> str:
    """
    Format nilai Decimal ke string mata uang dengan locale awareness.
    
    Args:
        value: Nilai yang akan diformat
        precision: Jumlah digit desimal
        locale_str: Lokal target (default: en_US.UTF-8)
        symbol: Tampilkan simbol mata uang
    
    Returns:
        String terformat sesuai locale
        
    Contoh:
        >>> format_currency(Decimal('1234.56'), locale_str='de_DE.UTF-8')
        '1.234,56 €'
    """
    if FormatterConfig.SAFE_MODE:
        original_locale = locale.getlocale(locale.LC_MONETARY)
    
    try:
        currency_symbol, default_precision = FormatterConfig.CURRENCY_FORMAT.get(
            locale_str, ('$', 2)
        )
        precision = precision if precision is not None else default_precision
        
        if not FormatterConfig.SAFE_MODE:
            locale.setlocale(locale.LC_ALL, locale_str)
            formatted = locale.currency(
                float(value),
                symbol=symbol,
                grouping=True,
                international=False
            )
        else:
            formatted_value = format_decimal(value, precision)
            formatted = f"{currency_symbol}{formatted_value}" if symbol else formatted_value
            
    except (locale.Error, ValueError) as e:
        # Fallback ke formatting dasar
        formatted = f"{currency_symbol}{format_decimal(value, precision)}" if symbol else format_decimal(value, precision)
    
    finally:
        if FormatterConfig.SAFE_MODE and 'original_locale' in locals():
            locale.setlocale(locale.LC_ALL, original_locale)
    
    return formatted

def format_decimal(value: Decimal, precision: int = 2) -> str:
    """
    Format Decimal ke string numerik dengan presisi tertentu.
    
    Args:
        value: Nilai Decimal
        precision: Jumlah digit desimal
    
    Returns:
        String numerik dengan grouping separator
    """
    return "{0:,.{1}f}".format(float(value), precision).rstrip('0').rstrip('.') if value else "0"

def truncate_decimal(
    value: Optional[Decimal], 
    precision: int,
    rounding: str = ROUND_DOWN
) -> Optional[Decimal]:
    """
    Potong nilai Decimal ke presisi tertentu tanpa pembulatan.
    
    Args:
        value: Nilai Decimal yang akan dipotong
        precision: Jumlah digit desimal
        rounding: Mode rounding (default: ROUND_DOWN)
    
    Returns:
        Decimal terpotong atau None jika input None
        
    Raises:
        ValueError: Jika precision negatif
    """
    if value is None:
        return None
    if precision < 0:
        raise ValueError("Precision must be non-negative integer")
    
    quantizer = Decimal('1e-{0}'.format(precision)) if precision > 0 else Decimal('1')
    return value.quantize(quantizer, rounding=rounding)

def format_percentage(
    value: Decimal,
    precision: int = 2,
    display_sign: bool = True
) -> str:
    """
    Format Decimal ke persentase.
    
    Args:
        value: Nilai Decimal (contoh: 0.0543 untuk 5.43%)
        precision: Jumlah digit desimal
        display_sign: Tampilkan tanda %
    
    Returns:
        String persentase terformat
    """
    formatted_value = format_decimal(value * 100, precision)
    return f"{formatted_value}%" if display_sign else formatted_value