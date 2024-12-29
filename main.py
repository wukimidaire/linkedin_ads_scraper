from fastapi import FastAPI, HTTPException, Depends
from playwright.async_api import async_playwright
from playwright.async_api import Error as PlaywrightError
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from datetime import datetime
import logging
from contextlib import asynccontextmanager

from src.utils import get_db, init_db, generate_linkedin_url
from src.models import LinkedInAd
from src.crawler import AsyncLinkedInCrawler
from src.logger import setup_logger
from src.database import Base, engine, SessionLocal
from src.config import browser_config, crawler_config, log_config, get_settings

# Initialize database
init_db()

app = FastAPI()
logger = setup_logger("linkedin_crawler")

# Access browser settings
viewport = browser_config.VIEWPORT
timeout = browser_config.PAGE_TIMEOUT

# Access crawler settings
max_requests = crawler_config.MAX_REQUESTS
scroll_timeout = crawler_config.SCROLL_TIMEOUT

# Access environment settings
settings = get_settings()
db_user = settings.POSTGRES_USER

# Access logging settings
log_format = log_config.FORMAT

class AdProcessingService:
    def __init__(self, db: Session, logger: logging.Logger):
        self.db = db
        self.logger = logger

    async def process_ad_batch(self, ad_details: list, company_id: str) -> int:
        if not ad_details:
            self.logger.warning("No ad details provided for processing")
            return 0

        processed_ads = 0
        failed_ads = 0

        for ad in ad_details:
            try:
                if not isinstance(ad, dict):
                    self.logger.error(f"Invalid ad data format: {type(ad)}")
                    continue

                ad_id = ad.get('ad_id')
                if not ad_id:
                    self.logger.error(f"No ad_id found in ad data: {ad}")
                    continue

                # Transform dates
                try:
                    start_date = datetime.strptime(ad.get('start_date'), '%Y/%m/%d').date() if ad.get('start_date') else None
                    end_date = datetime.strptime(ad.get('end_date'), '%Y/%m/%d').date() if ad.get('end_date') else None
                except ValueError as e:
                    self.logger.error(f"Date parsing error for ad {ad_id}: {str(e)}")
                    start_date = None
                    end_date = None

                try:
                    linkedin_ad = LinkedInAd(
                        ad_id=ad_id,
                        creative_type=ad.get('creative_type'),
                        advertiser_name=ad.get('advertiser_name'),
                        advertiser_logo=ad.get('advertiser_logo_url'),
                        headline=ad.get('headline'),
                        description=ad.get('description'),
                        promoted_text=ad.get('promoted_text'),
                        image_url=ad.get('image_url'),
                        view_details_link=ad.get('url'),
                        campaign_start_date=start_date,
                        campaign_end_date=end_date,
                        campaign_impressions_range=ad.get('total_impressions'),
                        campaign_impressions_by_country=ad.get('country_impressions'),
                        company_id=int(company_id) if company_id.isdigit() else None,
                        ad_type=ad.get('ad_type'),
                        ad_redirect_url=ad.get('redirect_url'),
                        utm_parameters=ad.get('utm_parameters')
                    )

                    self.db.merge(linkedin_ad)
                    processed_ads += 1
                    self.logger.info(f"Processed ad: {ad_id}")

                except Exception as e:
                    failed_ads += 1
                    self.logger.error(f"Error creating LinkedInAd object for ad {ad_id}: {str(e)}")
                    continue

            except Exception as e:
                failed_ads += 1
                self.logger.error(f"Error processing ad {ad.get('ad_id', 'unknown')}: {str(e)}")
                continue

        try:
            if processed_ads > 0:
                self.db.commit()
                self.logger.info(f"Successfully committed {processed_ads} ads to database")
            return processed_ads
        except SQLAlchemyError as e:
            self.db.rollback()
            self.logger.error(f"Database commit failed: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to commit changes to database: {str(e)}"
            )

@asynccontextmanager
async def get_browser_context(playwright):
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(
        viewport=browser_config.VIEWPORT,
        user_agent=browser_config.USER_AGENT
    )
    try:
        yield context
    finally:
        await browser.close()

@app.get("/")
async def read_root():
    logger.info("Root endpoint accessed")
    return {"message": "Welcome to the LinkedIn Ads Crawler API"}

@app.get("/crawl")
async def crawl(company_id: str, db: Session = Depends(get_db)):
    if not company_id:
        logger.error("No company ID provided")
        raise HTTPException(status_code=400, detail="Company ID or Account Name is required")
    
    logger.info(f"Starting crawl for company ID: {company_id}")
    ad_service = AdProcessingService(db, logger)
    
    try:
        async with async_playwright() as p:
            async with get_browser_context(p) as context:
                page = await context.new_page()
                crawler = AsyncLinkedInCrawler(company_id)
                
                start_url = generate_linkedin_url(company_id)
                logger.info(f"Navigating to: {start_url}")
                
                try:
                    response = await page.goto(start_url, wait_until='domcontentloaded')
                    if not response.ok:
                        logger.error(f"Failed to load page: {response.status} {response.status_text}")
                        raise HTTPException(status_code=400, detail="Failed to load LinkedIn page")
                    
                    await crawler.collect_ad_urls(page)
                    logger.info(f"Found {len(crawler.detail_urls)} ad URLs")
                    
                    if not crawler.detail_urls:
                        return {
                            "status": "success",
                            "message": "No ads found",
                            "processed_ads": 0,
                            "total_ads_found": 0
                        }
                    
                    processed_count = await crawler.process_all_ads(page, db)
                    
                    return {
                        "status": "success",
                        "processed_ads": processed_count,
                        "total_ads_found": len(crawler.detail_urls)
                    }
                    
                except PlaywrightError as e:
                    logger.error(f"Playwright error during crawl: {str(e)}")
                    raise HTTPException(status_code=502, detail=f"Crawler operation failed: {str(e)}")
                except Exception as e:
                    logger.error(f"Error during crawl: {str(e)}")
                    raise HTTPException(status_code=500, detail=f"Error during crawl: {str(e)}")
                
    except SQLAlchemyError as db_error:
        logger.error(f"Database error: {str(db_error)}")
        raise HTTPException(status_code=503, detail=f"Database operation failed: {str(db_error)}")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    try:
        result = db.execute(text("SELECT 1")).fetchone()
        return {
            "status": "healthy",
            "database": "connected",
            "test_query": result[0] if result else None
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))

@app.get("/test-db")
async def test_db(db: Session = Depends(get_db)):
    try:
        # Test query
        result = db.execute(text("SELECT 1")).fetchone()
        return {"database": "connected", "test_query": result[0]}
    except Exception as e:
        return {"database": "error", "details": str(e)}

@app.get("/check-ads/{company_id}")
async def check_ads(company_id: str, db: Session = Depends(get_db)):
    try:
        # Query ads for the specific company
        ads = db.query(LinkedInAd).filter(
            LinkedInAd.company_id == int(company_id)
        ).all()
        
        # Return detailed information
        return {
            "total_ads": len(ads),
            "ads": [{
                "ad_id": ad.ad_id,
                "advertiser_name": ad.advertiser_name,
                "campaign_start_date": str(ad.campaign_start_date),
                "campaign_end_date": str(ad.campaign_end_date)
            } for ad in ads]
        }
    except Exception as e:
        logger.error(f"Error checking ads: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/check-ad/{ad_id}")
async def check_ad(ad_id: str, db: Session = Depends(get_db)):
    """Check details of a specific ad"""
    ad = db.query(LinkedInAd).filter(LinkedInAd.ad_id == ad_id).first()
    if not ad:
        raise HTTPException(status_code=404, detail="Ad not found")
    
    # Convert to dict for display
    ad_dict = {
        'ad_id': ad.ad_id,
        'advertiser_name': ad.advertiser_name,
        'headline': ad.headline,
        'description': ad.description,
        'campaign_start_date': str(ad.campaign_start_date) if ad.campaign_start_date else None,
        'campaign_end_date': str(ad.campaign_end_date) if ad.campaign_end_date else None,
        'campaign_impressions_range': ad.campaign_impressions_range,
        'last_seen': str(datetime.now())
    }
    return ad_dict

@app.get("/list-ads/{company_id}")
async def list_ads(company_id: str, db: Session = Depends(get_db)):
    """List all ads for a company"""
    ads = db.query(LinkedInAd).filter(
        LinkedInAd.company_id == int(company_id)
    ).all()
    
    return {
        "total_ads": len(ads),
        "ads": [{
            'ad_id': ad.ad_id,
            'advertiser_name': ad.advertiser_name,
            'headline': ad.headline,
            'campaign_start_date': str(ad.campaign_start_date) if ad.campaign_start_date else None,
            'campaign_end_date': str(ad.campaign_end_date) if ad.campaign_end_date else None,
            'campaign_impressions_range': ad.campaign_impressions_range
        } for ad in ads]
    }