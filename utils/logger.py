"""
Caravan Logging Utility

Provides rotating file loggers for bot and web applications.
Logs are stored in the logs/ directory with automatic rotation.

Usage:
    from utils.logger import get_logger

    # In bot/main.py
    logger = get_logger('bot')
    logger.info("Bot started")

    # In web/main.py
    logger = get_logger('web')
    logger.info("Web server started")

    # In db/main.py
    logger = get_logger('db')
    logger.info("Database service started")
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Literal

# Create logs directory if it doesn't exist
LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Log format with timestamp, level, logger name, and message
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(funcName)s:%(lineno)d - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Rotating file handler configuration
MAX_BYTES = 10 * 1024 * 1024  # 10MB per file
BACKUP_COUNT = 5  # Keep 5 backup files

# Cache for loggers to prevent duplicate handlers
_loggers = {}


def get_logger(
    app_type: Literal["bot", "web", "db"], level: int = logging.INFO
) -> logging.Logger:
    """
    Get or create a logger for the specified application type.

    Args:
        app_type: Type of application ('bot', 'web', or 'db')
        level: Logging level (default: logging.INFO)

    Returns:
        Configured logger instance

    Example:
        >>> logger = get_logger('bot')
        >>> logger.info("Bot is ready")
        >>> logger.error("Failed to connect to database")
    """
    # Return cached logger if already created
    if app_type in _loggers:
        return _loggers[app_type]

    # Create logger
    logger = logging.getLogger(f"caravan.{app_type}")
    logger.setLevel(level)

    # Prevent duplicate handlers if logger already exists
    if logger.handlers:
        _loggers[app_type] = logger
        return logger

    # Create formatters
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # File handler with rotation
    log_file = LOGS_DIR / f"{app_type}.log"
    file_handler = RotatingFileHandler(
        log_file, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    # Console handler for real-time monitoring
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Cache the logger
    _loggers[app_type] = logger

    logger.info(f"{app_type.upper()} logger initialized - logs saved to {log_file}")

    return logger


def set_log_level(app_type: Literal["bot", "web", "db"], level: int) -> None:
    """
    Change the logging level for an existing logger.

    Args:
        app_type: Type of application ('bot', 'web', or 'db')
        level: New logging level (e.g., logging.DEBUG, logging.WARNING)

    Example:
        >>> set_log_level('bot', logging.DEBUG)  # Enable debug logging
    """
    if app_type in _loggers:
        logger = _loggers[app_type]
        logger.setLevel(level)
        for handler in logger.handlers:
            handler.setLevel(level)
        logger.info(f"Log level changed to {logging.getLevelName(level)}")
    else:
        raise ValueError(f"Logger for '{app_type}' not found. Call get_logger() first.")


def get_log_file_path(app_type: Literal["bot", "web", "db"]) -> Path:
    """
    Get the path to the log file for the specified application.

    Args:
        app_type: Type of application ('bot', 'web', or 'db')

    Returns:
        Path object pointing to the log file
    """
    return LOGS_DIR / f"{app_type}.log"


# Convenience function for Discord.py integration
def setup_discord_logging(level: int = logging.INFO) -> None:
    """
    Configure logging for discord.py library.

    Args:
        level: Logging level for discord.py (default: logging.INFO)

    Example:
        >>> setup_discord_logging(logging.WARNING)  # Only show warnings/errors
    """
    discord_logger = logging.getLogger("discord")
    discord_logger.setLevel(level)

    # Reuse bot's file handler
    bot_logger = get_logger("bot", level)
    for handler in bot_logger.handlers:
        if isinstance(handler, RotatingFileHandler):
            discord_logger.addHandler(handler)
            break
