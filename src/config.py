from datetime import datetime
from functools import lru_cache
from pydantic_settings import BaseSettings
import logging

class BrowserConfig:
    """Browser-specific configuration settings"""
    USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    VIEWPORT = {'width': 1920, 'height': 1080}
    PAGE_TIMEOUT = 30000  # 30 seconds
    NAVIGATION_TIMEOUT = 15000  # 30 seconds
    MAX_CONCURRENT_PAGES = 4
    CHUNK_SIZE = 4
    RETRY_COUNT = 3
    RETRY_DELAY = 2  # seconds

class CrawlerConfig:
    """Crawler behavior configuration"""
    MAX_REQUESTS = 50
    SCROLL_TIMEOUT = 3
    SCROLL_COUNT = {
        'MIN': 3,
        'MAX': 500
    }
    SCROLL_WAIT_TIME = 3  # seconds
    NETWORK_IDLE_TIMEOUT = 5000  # milliseconds
    MAX_CONSECUTIVE_UNCHANGED = 5


class LogConfig:
    """Logging configuration"""
    FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
    DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
    LEVEL = logging.INFO
    DEBUG = logging.DEBUG

class Settings(BaseSettings):
    """Environment-specific settings"""
    # Database settings
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str
    CLOUD_SQL_INSTANCE: str | None = None  # Make it optional
    
    # Environment settings
    ENVIRONMENT: str = "development"
    OUTPUT_FILE: str = 'ad_details.json'
    
    class Config:
        env_file = ".env"

@lru_cache()
def get_settings() -> Settings:
    """Cached settings loader"""
    return Settings()

# Initialize configurations
browser_config = BrowserConfig()
crawler_config = CrawlerConfig()
log_config = LogConfig()

# Export constants for use in other modules
MAX_CONCURRENT_PAGES = browser_config.MAX_CONCURRENT_PAGES
VIEWPORT_CONFIG = browser_config.VIEWPORT
USER_AGENT = browser_config.USER_AGENT
NAVIGATION_TIMEOUT = browser_config.NAVIGATION_TIMEOUT
RETRY_COUNT = browser_config.RETRY_COUNT
RETRY_DELAY = browser_config.RETRY_DELAY
CHUNK_SIZE = browser_config.CHUNK_SIZE