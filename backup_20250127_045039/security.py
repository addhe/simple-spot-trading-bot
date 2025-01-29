import re

# src/security.py
class InputValidator:
    @staticmethod
    def validate_symbol(symbol: str) -> bool:
        return re.match(r"^[A-Z]{6,10}$", symbol) is not None

    @staticmethod
    def sanitize_log_entry(entry: str) -> str:
        return re.sub(r"(api_key|api_secret)=[^&]+", r"\1=***", entry)
