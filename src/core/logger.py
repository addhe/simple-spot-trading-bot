# src/core/logger.py
import logging
import os
from datetime import datetime
from typing import Optional


class TradingBotLogger:
    """Centralized logging configuration for trading bot."""

    def __init__(
        self,
        name: str,
        log_level: str = "INFO",
        log_dir: Optional[str] = None
    ) -> None:
        """
        Initialize logger with customizable configuration.

        Args:
            name: Logger name
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_dir: Optional custom log directory
        """
        self.name = name
        self.log_level = getattr(logging, log_level.upper())
        self.log_dir = log_dir or "logs"
        
        # Ensure log directory exists
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Configure logger
        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        """
        Configure logger with file and console handlers.

        Returns:
            Configured logging.Logger instance
        """
        logger = logging.getLogger(self.name)
        logger.setLevel(self.log_level)
        
        # Remove existing handlers
        logger.handlers.clear()
        
        # Create handlers
        console_handler = logging.StreamHandler()
        file_handler = logging.FileHandler(
            os.path.join(
                self.log_dir,
                f"{self.name}_{datetime.now():%Y%m%d}.log"
            )
        )
        
        # Create formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        
        # Set formatter for handlers
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)
        
        # Add handlers to logger
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
        
        return logger

    def get_logger(self) -> logging.Logger:
        """
        Return configured logger instance.

        Returns:
            logging.Logger: Configured logger
        """
        return self.logger