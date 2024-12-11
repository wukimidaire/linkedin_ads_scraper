class CrawlerException(Exception):
    """Base exception for crawler errors"""
    pass

class NavigationError(CrawlerException):
    """Raised when page navigation fails"""
    pass

class ExtractionError(CrawlerException):
    """Raised when data extraction fails"""
    pass
