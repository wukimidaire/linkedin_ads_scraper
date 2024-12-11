from src.crawler import LinkedInCrawler
from src.utils import clean_text, clean_percentage, format_date

def test_clean_percentage():
    assert clean_percentage("less than 1%") == "<1%"
    assert clean_percentage("50%") == "50%"
    assert clean_percentage(None) == "0%"

def test_format_date():
    assert format_date("Jan 1, 2024") == "2024/01/01"
    assert format_date("Dec 31, 2023") == "2023/12/31"
    assert format_date(None) is None

def test_clean_text():
    assert clean_text("<p>Test</p>") == "Test"
    assert clean_text(None) == ""
