from datetime import datetime
import re
import emoji
from sqlalchemy import text
from sqlalchemy.orm import Session
import os
from dotenv import load_dotenv
import asyncio
from .models import LinkedInAd
from .database import SessionLocal, engine, Base
from .config import VIEWPORT_CONFIG, USER_AGENT, NAVIGATION_TIMEOUT

# Load environment variables if not already done
load_dotenv()

def init_db():
    """Initialize database and tables"""
    try:
        # Import all models to ensure they're registered with SQLAlchemy
        from src.models import LinkedInAd, Base
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        print("Database tables created successfully!")
        
        # Test the connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            print("Database connection verified!")
            
    except Exception as e:
        print(f"Error initializing database: {str(e)}")

# Database dependency
def get_db():
    db = SessionLocal()
    try:
        # Test the connection
        db.execute(text("SELECT 1"))
        yield db
    finally:
        db.close()

# Add these database-related functions if not present
def close_db():
    """Close database connection"""
    engine.dispose()

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

def generate_linkedin_url(company_id: str) -> str:
    """Generate LinkedIn Ad Library URL based on company ID or name"""
    return (f"https://www.linkedin.com/ad-library/search?companyIds={company_id}" 
            if company_id.isdigit() 
            else f"https://www.linkedin.com/ad-library/search?accountOwner={company_id}")

async def setup_browser_context(playwright):
    """Configure and return a new browser context with optimal settings"""
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(
        viewport=VIEWPORT_CONFIG,
        user_agent=USER_AGENT,
        proxy=None,  # Add proxy support if needed
        java_script_enabled=True,
        bypass_csp=True,  # Bypass Content Security Policy for better scraping
        ignore_https_errors=True
    )
    
    # Add performance optimizations
    await context.set_default_timeout(NAVIGATION_TIMEOUT)
    await context.set_default_navigation_timeout(NAVIGATION_TIMEOUT)
    
    return browser, context

async def batch_upsert_ads(ads: list, db: Session, batch_size: int = 100):
    """Batch process ad insertions/updates"""
    for i in range(0, len(ads), batch_size):
        batch = ads[i:i + batch_size]
        ad_objects = [LinkedInAd(**ad) for ad in batch]
        db.bulk_save_objects(ad_objects, update_changed_only=True)
        await asyncio.sleep(0.1)  # Prevent overwhelming the database
    db.commit()
