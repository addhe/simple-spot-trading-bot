import logging

def setup_logger() -> logging.Logger:
    logging.basicConfig(level=logging.INFO)
    return logging.getLogger()
