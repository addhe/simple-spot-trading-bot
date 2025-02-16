# src/logger.py
import os
import logging
import newrelic.agent
import structlog
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from datetime import datetime
from typing import Dict, Any

# Initialize New Relic
newrelic.agent.initialize('newrelic.ini')

def setup_logging():
    """Setup structured logging with New Relic integration"""
    log_directory = 'logs/bot'
    if not os.path.exists(log_directory):
        os.makedirs(log_directory)

    # Base logger configuration
    logger = logging.getLogger('TradingBot')
    logger.setLevel(logging.INFO)

    # Clear existing handlers
    logger.handlers = []

    # File handler for regular logs with size-based rotation
    regular_handler = RotatingFileHandler(
        os.path.join(log_directory, 'bot.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )

    # File handler for error logs with time-based rotation
    error_handler = TimedRotatingFileHandler(
        os.path.join(log_directory, 'error.log'),
        when='midnight',
        interval=1,
        backupCount=30
    )
    error_handler.setLevel(logging.ERROR)

    # Structured logging processors
    processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        add_newrelic_context,
    ]

    # Configure structlog
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Create formatters
    json_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=processors
    )

    regular_handler.setFormatter(json_formatter)
    error_handler.setFormatter(json_formatter)
    
    logger.addHandler(regular_handler)
    logger.addHandler(error_handler)

    return logger

def add_newrelic_context(logger: str, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add New Relic transaction information to log context"""
    try:
        transaction = newrelic.agent.current_transaction()
        if transaction:
            event_dict.update({
                'newrelic': {
                    'transaction_id': transaction.guid,
                    'account_id': transaction.application.account_id,
                    'application_id': transaction.application.id,
                }
            })
    except Exception:
        pass
    return event_dict

def log_error(logger, error: Exception, context: Dict[str, Any] = None):
    """Log error with context and send to New Relic"""
    if context is None:
        context = {}
    
    error_details = {
        'error_type': type(error).__name__,
        'error_message': str(error),
        'timestamp': datetime.utcnow().isoformat(),
        **context
    }
    
    logger.error('Error occurred', extra=error_details)
    newrelic.agent.notice_error(error, attributes=error_details)

# Initialize the logger
logger = setup_logging()
