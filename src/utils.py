from datetime import datetime
import re
import emoji


def clean_text(text):
    """Clean text using the emoji library"""
    if not text:
        return ""
    
    text = emoji.demojize(text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\n+', '\n', text)
    text = re.sub(r' +', ' ', text)
    return text.strip()

def clean_percentage(percentage_str):
    """Clean percentage string"""
    if not percentage_str:
        return "0%"
    if "less than" in percentage_str.lower():
        return "<1%"
    cleaned = ''.join(char for char in percentage_str if char.isdigit() or char == '%')
    return cleaned if cleaned else "0%"

def format_date(date_string):
    """Format date string to YYYY/MM/DD"""
    if not date_string:
        return None
    
    month_map = {
        'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
        'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
        'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
    }
    
    try:
        month, day, year = re.match(r'(\w+) (\d{1,2}), (\d{4})', date_string).groups()
        month_num = month_map[month]
        day_padded = str(day).zfill(2)
        return f"{year}/{month_num}/{day_padded}"
    except Exception as e:
        return None

def extract_with_regex(pattern, html, group=1):
    """Extract content using regex pattern"""
    match = re.search(pattern, html)
    return match.group(group).strip() if match else None