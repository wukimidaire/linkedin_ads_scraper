from datetime import datetime
import re
import emoji


def clean_text(text: str) -> str:
    """Clean and normalize text content"""
    if not text:
        return ""
    # Remove HTML tags, extra whitespace, and normalize
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def clean_percentage(value: str) -> str:
    """Clean and format percentage values"""
    if not value:
        return "0%"
    value = value.lower()
    if "less than" in value:
        return "<1%"
    return value.strip()

def format_date(date_str: str) -> str:
    """Format date string to YYYY/MM/DD"""
    if not date_str:
        return None
    try:
        date_obj = datetime.strptime(date_str.strip(), '%b %d, %Y')
        return date_obj.strftime('%Y/%m/%d')
    except Exception:
        return None

def extract_with_regex(pattern, html, group=1):
    """Extract content using regex pattern"""
    match = re.search(pattern, html)
    return match.group(group).strip() if match else None