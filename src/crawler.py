from playwright.async_api import Page
import logging
import asyncio
from .config import (
    SCROLL_WAIT_TIME,
    NETWORK_IDLE_TIMEOUT,
    MAX_CONSECUTIVE_UNCHANGED,
    RETRY_COUNT,
    PAGE_TIMEOUT,
    NAVIGATION_TIMEOUT
)
from .utils import clean_text, clean_percentage, format_date
from src.logger import setup_logger
import re
from datetime import datetime

class AsyncLinkedInCrawler:
    def __init__(self, company_id: str, max_requests: int = 50):
        self.company_id = company_id
        self.max_requests = max_requests
        self.detail_urls = set()
        self.logger = setup_logger("crawler")

    async def collect_ad_urls(self, page: Page) -> None:
        self.logger.info("Starting URL collection")
        previous_links_count = 0
        consecutive_unchanged_counts = 0
        scroll_count = 0

        while True:
            self.logger.debug(f"Scroll iteration {scroll_count}")
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await asyncio.sleep(3)
            scroll_count += 1

            try:
                links = await page.eval_on_selector_all(
                    "a[href]", 
                    "elements => elements.map(el => el.href)"
                )
                
                current_links = set()
                for link in links:
                    if "/ad-library/detail/" in link:
                        clean_link = link.split('?')[0]
                        current_links.add(clean_link)
                        if clean_link not in self.detail_urls:
                            self.detail_urls.add(clean_link)
                            self.logger.debug(f"Found new URL: {clean_link}")

                if len(current_links) == previous_links_count:
                    consecutive_unchanged_counts += 1
                    self.logger.debug(f"No new links found. Unchanged count: {consecutive_unchanged_counts}")
                else:
                    consecutive_unchanged_counts = 0

                previous_links_count = len(current_links)

            except Exception as e:
                self.logger.error(f"Error during URL collection: {str(e)}", exc_info=True)

            if (consecutive_unchanged_counts >= 5 and scroll_count >= 3) or scroll_count >= 500:
                self.logger.info(f"URL collection complete. Found {len(self.detail_urls)} unique URLs")
                break

    async def process_all_ads(self, page: Page) -> list:
        all_ad_details = []
        total_ads = len(self.detail_urls)
        
        for index, url in enumerate(self.detail_urls, 1):
            try:
                self.logger.info(f"Processing ad {index}/{total_ads}: {url}")
                start_time = datetime.now()
                
                ad_details = await self.extract_ad_details(page, url)
                
                if ad_details:
                    all_ad_details.append(ad_details)
                    processing_time = (datetime.now() - start_time).total_seconds()
                    self.logger.info(f"Successfully processed ad {index}/{total_ads} in {processing_time:.2f} seconds")
                else:
                    self.logger.warning(f"Failed to extract details for ad {index}/{total_ads}")
                
                await asyncio.sleep(2)
            except Exception as e:
                self.logger.error(f"Failed to process ad {index}/{total_ads}: {str(e)}", exc_info=True)
        
        self.logger.info(f"Completed processing {len(all_ad_details)}/{total_ads} ads")
        return all_ad_details

    async def extract_ad_details(self, page: Page, url: str) -> dict:
        """Extract details from a single ad page with retry logic"""
        retry_count = 0
        while retry_count < RETRY_COUNT:
            try:
                # Navigate to the ad detail page with increased timeout
                await page.goto(url, wait_until='domcontentloaded', timeout=NAVIGATION_TIMEOUT)
                
                # Wait for key elements instead of network idle
                try:
                    await page.wait_for_selector('.ad-library-preview-creative-text', timeout=PAGE_TIMEOUT)
                except Exception:
                    logging.debug("Text content selector not found, continuing...")
                
                # Extract ad details
                ad_details = {
                    'url': url,
                    'ad_id': url.split('/')[-1],
                    'company_id': self.company_id
                }

                # Extract text content
                try:
                    text_content = await page.eval_on_selector(
                        '.ad-library-preview-creative-text', 
                        'el => el.textContent',
                        timeout=5000
                    )
                    ad_details['text_content'] = clean_text(text_content)
                except Exception:
                    ad_details['text_content'] = ""

                # Extract start date
                try:
                    start_date = await page.eval_on_selector(
                        '.ad-library-preview-metadata-start-date', 
                        'el => el.textContent',
                        timeout=5000
                    )
                    ad_details['start_date'] = format_date(start_date)
                except Exception:
                    ad_details['start_date'] = None

                # Extract demographics with shorter timeout
                demographics = await self._extract_demographics(page)
                ad_details['demographics'] = demographics

                # Extract media type
                try:
                    media_type = await page.eval_on_selector(
                        '.ad-library-preview-creative-type', 
                        'el => el.textContent',
                        timeout=5000
                    )
                    ad_details['media_type'] = clean_text(media_type)
                except Exception:
                    ad_details['media_type'] = "Unknown"

                logging.info(f"Successfully extracted details for ad {ad_details['ad_id']}")
                return ad_details

            except Exception as e:
                retry_count += 1
                if retry_count < RETRY_COUNT:
                    logging.warning(f"Retry {retry_count}/{RETRY_COUNT} for URL {url}: {str(e)}")
                    await asyncio.sleep(2)  # Wait before retrying
                else:
                    logging.error(f"Failed to extract details from {url} after {RETRY_COUNT} retries: {str(e)}")
                    return None

    async def _extract_demographics(self, page: Page) -> dict:
        """Helper method to extract demographics with error handling"""
        demographics = {}
        try:
            demo_elements = await page.query_selector_all('.ad-library-preview-demographic-data')
            
            for element in demo_elements:
                try:
                    label = await element.eval_on_selector('.demographic-data-label', 'el => el.textContent')
                    value = await element.eval_on_selector('.demographic-data-value', 'el => el.textContent')
                    
                    if 'gender' in label.lower():
                        demographics['gender'] = clean_percentage(value)
                    elif 'age' in label.lower():
                        demographics['age'] = clean_percentage(value)
                    elif 'seniority' in label.lower():
                        demographics['seniority'] = clean_percentage(value)
                except Exception:
                    continue
        except Exception as e:
            logging.error(f"Error extracting demographics: {str(e)}")
        
        return demographics