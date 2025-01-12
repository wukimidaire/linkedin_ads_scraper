from fastapi import FastAPI, HTTPException, Depends
from playwright.async_api import async_playwright, Browser, BrowserContext
from playwright.async_api import Error as PlaywrightError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from datetime import datetime
import logging
from contextlib import asynccontextmanager

from src.utils import init_db, generate_linkedin_url, setup_browser_context
from src.models import LinkedInAd
from src.crawler import AsyncLinkedInCrawler
from src.logger import setup_logger
from src.database import Base, engine, AsyncSessionLocal, get_db
from src.config import browser_config, crawler_config, log_config, get_settings

# Initialize logger first with debug level
logger = setup_logger("linkedin_crawler", log_level=logging.DEBUG)

app = FastAPI()

class AdProcessingService:
    def __init__(self, db: AsyncSession, logger: logging.Logger):
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
                    campaign_impressions_by_country=ad.get('campaign_impressions_by_country'),
                    company_id=int(company_id) if company_id.isdigit() else None,
                    ad_type=ad.get('ad_type'),
                    ad_redirect_url=ad.get('redirect_url'),
                    utm_parameters=ad.get('utm_parameters')
                )

                self.db.add(linkedin_ad)
                processed_ads += 1
                self.logger.info(f"Processed ad: {ad_id}")

            except Exception as e:
                failed_ads += 1
                self.logger.error(f"Error processing ad {ad.get('ad_id', 'unknown')}: {str(e)}")
                continue

        try:
            if processed_ads > 0:
                await self.db.commit()
                self.logger.info(f"Successfully committed {processed_ads} ads to database")
            return processed_ads
        except SQLAlchemyError as e:
            await self.db.rollback()
            self.logger.error(f"Database commit failed: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to commit changes to database: {str(e)}"
            )

@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(text("SELECT 1"))
        row = result.scalar()
        return {
            "status": "healthy",
            "database": "connected",
            "test_query": row
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))

@app.get("/test-db")
async def test_db(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(text("SELECT 1"))
        row = result.scalar()
        return {"database": "connected", "test_query": row}
    except Exception as e:
        return {"database": "error", "details": str(e)}

@app.get("/check-ads/{company_id}")
async def check_ads(company_id: str, db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(
            text("SELECT * FROM linkedin_ads WHERE company_id = :company_id"),
            {"company_id": int(company_id)}
        )
        ads = result.mappings().all()
        
        return {
            "total_ads": len(ads),
            "ads": [{
                "ad_id": ad['ad_id'],
                "advertiser_name": ad['advertiser_name'],
                "campaign_start_date": str(ad['campaign_start_date']),
                "campaign_end_date": str(ad['campaign_end_date'])
            } for ad in ads]
        }
    except Exception as e:
        logger.error(f"Error checking ads: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/check-ad/{ad_id}")
async def check_ad(ad_id: str, db: AsyncSession = Depends(get_db)):
    """Check details of a specific ad"""
    result = await db.execute(
        text("SELECT * FROM linkedin_ads WHERE ad_id = :ad_id"),
        {"ad_id": ad_id}
    )
    ad = result.mappings().first()
    if not ad:
        raise HTTPException(status_code=404, detail="Ad not found")
    
    return {
        'ad_id': ad['ad_id'],
        'advertiser_name': ad['advertiser_name'],
        'headline': ad['headline'],
        'description': ad['description'],
        'campaign_start_date': str(ad['campaign_start_date']) if ad['campaign_start_date'] else None,
        'campaign_end_date': str(ad['campaign_end_date']) if ad['campaign_end_date'] else None,
        'campaign_impressions_range': ad['campaign_impressions_range'],
        'last_seen': str(datetime.now())
    }

@app.get("/crawl")
async def crawl(company_id: str, db: AsyncSession = Depends(get_db)):
    """Start crawling ads for a specific company"""
    try:
        crawler = AsyncLinkedInCrawler(company_id)
        async with async_playwright() as playwright:
            browser, context = await setup_browser_context(playwright)
            page = await context.new_page()
            await crawler.collect_ad_urls(page)
            processed_count = await crawler.process_all_ads(page, db)
            await browser.close()
        return {"status": "success", "processed_ads": processed_count}
    except Exception as e:
        logger.error(f"Error during crawling: {str(e)}")
        raise HTTPException(status_code=500, detail="Crawling failed")

async def setup_browser_context(playwright) -> tuple[Browser, BrowserContext]:
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(
        user_agent=browser_config.USER_AGENT,
        viewport=browser_config.VIEWPORT
    )
    return browser, context


