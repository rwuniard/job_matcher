"""
Logging configuration module using python-json-logger.
Reads configuration from environment variables.
"""

import logging
from pickle import NONE
import sys
import os
from typing import Optional
from pythonjsonlogger import jsonlogger


class Log:
    """
    Logging configuration class that supports:
    - JSON format to stdout (for CloudWatch/observability)
    - Human-readable text to stderr (for console debugging)
    - Configuration via environment variables
    """
    
    # Environment variable names
    ENV_LOG_LEVEL = 'LOG_LEVEL'
    ENV_LOG_FORMAT = 'LOG_FORMAT'  # 'json', 'text', or 'dual'
    ENV_ENVIRONMENT = 'ENVIRONMENT'  # 'development' or 'production'
    _configured = False

    def __init__(
        self,
        log_level: Optional[str] = None,
        log_format: Optional[str] = None,
        environment: Optional[str] = None
    ):
        """
        Initialize logging configuration.
        
        Args:
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
                      If None, reads from LOG_LEVEL env var (default: INFO)
            log_format: Output format - 'json', 'text', or 'dual'.
                       If None, reads from LOG_FORMAT env var (default: 'dual')
            environment: 'development' or 'production'.
                        If None, reads from ENVIRONMENT env var (default: 'development')
        """
        # Load environment variables
        self.log_level = self._get_log_level(log_level)
        self.log_format = self._get_log_format(log_format)
        self.environment = environment or os.getenv(self.ENV_ENVIRONMENT, 'development')
        
    
    def _get_log_level(self, level: Optional[str]) -> int:
        """Get logging level from parameter or environment."""
        level_str = level or os.getenv(self.ENV_LOG_LEVEL, 'INFO')
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        return level_map.get(level_str.upper(), logging.INFO)
    
    def _get_log_format(self, fmt: Optional[str]) -> str:
        """Get log format from parameter or environment."""
        fmt_str = fmt or os.getenv(self.ENV_LOG_FORMAT, 'dual')
        valid_formats = {'json', 'text', 'dual'}
        return fmt_str.lower() if fmt_str.lower() in valid_formats else 'dual'
    
    def setup(self) -> None:
        """
        Configure logging based on settings.
        """
        if Log._configured:
            return
        Log._configured = True
        
        # Get root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(self.log_level)
        
        # Remove existing handlers to avoid duplicates
        root_logger.handlers.clear()
        
        # Setup handlers based on format
        if self.log_format == 'json':
            self._add_json_handler(root_logger)
        elif self.log_format == 'text':
            self._add_text_handler(root_logger)
        else:  # dual
            self._add_json_handler(root_logger)
            self._add_text_handler(root_logger)
        
        self._configured = True
        
        # Log configuration info
        logger = logging.getLogger(__name__)
        logger.info(
            "Logging configured",
            extra={
                'log_level': logging.getLevelName(self.log_level),
                'log_format': self.log_format,
                'environment': self.environment
            }
        )
        
    
    def _add_json_handler(self, logger: logging.Logger):
        """Add JSON formatter handler to stdout using python-json-logger."""
        handler = logging.StreamHandler(sys.stdout)
        
        # Create JSON formatter with custom fields
        formatter = jsonlogger.JsonFormatter(
            '%(timestamp)s %(levelname)s %(name)s %(message)s %(module)s %(funcName)s %(lineno)d',
            rename_fields={
                'levelname': 'level',
                'name': 'logger',
                'funcName': 'function',
                'lineno': 'line'
            },
            timestamp=True
        )
        
        handler.setFormatter(formatter)
        handler.setLevel(self.log_level)
        logger.addHandler(handler)
    
    def _add_text_handler(self, logger: logging.Logger):
        """Add text formatter handler to stderr."""
        handler = logging.StreamHandler(sys.stderr)
        
        # Different format based on environment
        if self.environment == 'production':
            # Compact format for production
            formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        else:
            # Detailed format for development
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        
        handler.setFormatter(formatter)
        handler.setLevel(self.log_level)
        logger.addHandler(handler)
    
    @staticmethod
    def get_logger(name: Optional[str] = None) -> logging.Logger:
        """
        Get a logger instance.
        
        Args:
            name: Logger name. If None, uses the calling module's __name__
        
        Returns:
            Logger instance
        """
        return logging.getLogger(name)


def setup_logging(
    log_level: Optional[str] = None,
    log_format: Optional[str] = None,
    environment: Optional[str] = None
) -> None:
    """
    Convenience function to setup logging.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Output format ('json', 'text', or 'dual')
        environment: 'development' or 'production'
    
        
    Example:
        >>> from logger_config_v2 import setup_logging
        >>> setup_logging()
        >>> logger = logging.getLogger(__name__)
        >>> logger.info("Hello", extra={'user_id': 123})
    """
    log = Log(log_level=log_level, log_format=log_format, environment=environment)
    log.setup()