from datetime import datetime
import re
import emoji
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import os
from dotenv import load_dotenv
import asyncio
from .models import LinkedInAd
from .database import AsyncSessionLocal, engine, Base
from .config import VIEWPORT_CONFIG, USER_AGENT, NAVIGATION_TIMEOUT
import time

# Load environment variables if not already done
load_dotenv()

async def init_db():
    """Initialize database and tables"""
    try:
        # Import all models to ensure they're registered with SQLAlchemy
        from src.models import LinkedInAd, Base
        
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("Database tables created successfully!")
        
        # Test the connection
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            print("Database connection verified!")
            
    except Exception as e:
        print(f"Error initializing database: {str(e)}")

async def close_db():
    """Close database connection"""
    await engine.dispose()

def clean_text(text: str) -> str:
    """Clean and normalize text content"""
    if not text:
        return ""
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
    browser = await playwright.chromium.launch(
        headless=True,
        args=[
            '--disable-gpu',
            '--disable-dev-shm-usage',
            '--disable-setuid-sandbox',
            '--no-sandbox',
            '--disable-web-security',
            '--disable-features=IsolateOrigins,site-per-process',
        ]
    )
    
    context = await browser.new_context(
        viewport=VIEWPORT_CONFIG,
        user_agent=USER_AGENT,
        proxy=None,  # Add proxy support if needed
        java_script_enabled=True,
        bypass_csp=True,
        ignore_https_errors=True,
        extra_http_headers={
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    )
    
    # Block unnecessary resources
    await context.route("**/*.{png,jpg,jpeg,gif,svg,css,font,woff,woff2}", 
        lambda route: route.abort())
    
    await context.set_default_timeout(NAVIGATION_TIMEOUT)
    await context.set_default_navigation_timeout(NAVIGATION_TIMEOUT)
    
    return browser, context

async def batch_upsert_ads(ads: list, db: AsyncSession, batch_size: int = 100):
    """Batch process ad insertions/updates"""
    for i in range(0, len(ads), batch_size):
        batch = ads[i:i + batch_size]
        ad_objects = [LinkedInAd(**ad) for ad in batch]
        db.add_all(ad_objects)
        await asyncio.sleep(0.1)  # Prevent overwhelming the database
    await db.commit()

class CrawlerMetrics:
    def __init__(self):
        self.start_time = time.time()
        self.successful_requests = 0
        self.failed_requests = 0
        self.total_processing_time = 0
        
    def get_success_rate(self):
        total = self.successful_requests + self.failed_requests
        return (self.successful_requests / total * 100) if total > 0 else 0
