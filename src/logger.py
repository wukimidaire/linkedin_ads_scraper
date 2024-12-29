import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Union, Callable, Any
from functools import wraps

def setup_logger(name: str, log_level: Union[str, int] = "INFO") -> logging.Logger:
    """Set up and return a logger instance"""
    logger = logging.getLogger(name)
    
    # If level is already an integer, use it directly
    if isinstance(log_level, int):
        level = log_level
    else:
        # Convert string to logging level
        level = getattr(logging, log_level.upper())
    
    logger.setLevel(level)
    
    # Create console handler with formatting
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Add formatter to handler
    console_handler.setFormatter(formatter)
    
    # Add handler to logger if it doesn't already have one
    if not logger.handlers:
        logger.addHandler(console_handler)
    
    return logger

def handle_crawler_errors(retries: int = 3):
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            for attempt in range(retries):
                try:
                    return await func(*args, **kwargs)
                except PlaywrightError as e:
                    logger.error(f"Playwright error: {str(e)}")
                    if attempt == retries - 1:
                        raise
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
        return wrapper
    return decorator