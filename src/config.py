# Standard library imports
import logging
from datetime import datetime

# Third-party imports
import emoji
from playwright.sync_api import sync_playwright

# Browser Configuration
USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'

# Crawler Configuration
DEFAULT_MAX_REQUESTS = 50
DEFAULT_SCROLL_TIMEOUT = 3
MIN_SCROLL_COUNT = 3
MAX_SCROLL_COUNT = 500

# Logging Configuration
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
LOG_LEVEL = logging.INFO
DEBUG_LEVEL = logging.DEBUG

# Add these constants
SCROLL_WAIT_TIME = 3  # seconds
NETWORK_IDLE_TIMEOUT = 5000  # milliseconds
MAX_CONSECUTIVE_UNCHANGED = 5
OUTPUT_FILE = 'ad_details.json'

# Browser viewport settings
VIEWPORT_CONFIG = {
    'width': 1920,
    'height': 1080
}

# Add these new constants
RETRY_COUNT = 3
PAGE_TIMEOUT = 60000  # 60 seconds
NAVIGATION_TIMEOUT = 30000  # 30 seconds
RETRY_DELAY = 2  # seconds between retries

# Performance tuning
MAX_CONCURRENT_PAGES = 2
CHUNK_SIZE = 4

# Performance optimization settings
PERFORMANCE_CONFIG = {
    'viewport': {
        'width': 1024,
        'height': 768,
        'deviceScaleFactor': 1,
    },
    'javascript_enabled': True,
    'bypass_csp': True,  # Bypass Content Security Policy
    'ignore_https_errors': True,
    'proxy': None,  # Add proxy support if needed
}

# Resource optimization
RESOURCE_LIMITS = {
    'max_concurrent_requests': 4,
    'max_request_size': 1024 * 1024 * 5,  # 5MB
    'request_timeout': 15000,  # 15 seconds
}

# Timing configurations
TIMING_CONFIG = {
    'navigation_timeout': 20000,
    'content_timeout': 5000,
    'retry_delay': 2000,
    'max_retries': 3,
}
