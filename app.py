from fastapi import FastAPI, HTTPException
from playwright.async_api import async_playwright
from src.crawler import AsyncLinkedInCrawler
from src.logger import setup_logger

app = FastAPI()
logger = setup_logger("linkedin_crawler")

@app.get("/")
async def read_root():
    logger.info("Root endpoint accessed")
    return {"message": "Welcome to the LinkedIn Ads Crawler API"}

@app.get("/crawl")
async def crawl(company_id: str):
    if not company_id:
        logger.error("No company ID provided")
        raise HTTPException(status_code=400, detail="Company ID or Account Name is required")
    
    logger.info(f"Starting crawl for company ID: {company_id}")
    
    try:
        async with async_playwright() as p:
            logger.debug("Initializing playwright")
            crawler = AsyncLinkedInCrawler(company_id)
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            try:
                start_url = (f"https://www.linkedin.com/ad-library/search?companyIds={company_id}" 
                           if company_id.isdigit() 
                           else f"https://www.linkedin.com/ad-library/search?accountOwner={company_id}")
                
                logger.info(f"Navigating to: {start_url}")
                response = await page.goto(start_url, wait_until='domcontentloaded')
                
                if not response.ok:
                    logger.error(f"Failed to load page: {response.status} {response.status_text}")
                    raise HTTPException(status_code=400, detail="Failed to load LinkedIn page")
                
                logger.info("Starting to collect ad URLs")
                await crawler.collect_ad_urls(page)
                logger.info(f"Found {len(crawler.detail_urls)} ad URLs")
                
                logger.info("Starting to process ads")
                ad_details = await crawler.process_all_ads(page)
                logger.info(f"Successfully processed {len(ad_details)} ads")
                
                return {"result": ad_details}
            finally:
                logger.debug("Closing browser")
                await browser.close()
                
    except Exception as e:
        logger.error(f"Crawler error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Crawler error: {str(e)}")