from playwright.async_api import Page
import logging
import asyncio
from .config import (
    SCROLL_WAIT_TIME,
    NETWORK_IDLE_TIMEOUT,
    MAX_CONSECUTIVE_UNCHANGED,
    RETRY_COUNT,
    PAGE_TIMEOUT,
    NAVIGATION_TIMEOUT,
    MAX_CONCURRENT_PAGES,
    CHUNK_SIZE,
    RETRY_DELAY,
    VIEWPORT_CONFIG,
    USER_AGENT
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
        start_time = datetime.now()
        
        self.logger.info(f"Starting parallel processing of {total_ads} ads with {MAX_CONCURRENT_PAGES} concurrent pages")
        
        try:
            # Create multiple browser contexts
            browser = page.context.browser
            contexts = []
            pages = []
            
            # Initialize parallel contexts
            self.logger.debug(f"Initializing {MAX_CONCURRENT_PAGES} browser contexts")
            for i in range(MAX_CONCURRENT_PAGES):
                try:
                    context = await browser.new_context(
                        viewport=VIEWPORT_CONFIG,
                        user_agent=USER_AGENT
                    )
                    contexts.append(context)
                    pages.append(await context.new_page())
                    self.logger.debug(f"Context {i+1}/{MAX_CONCURRENT_PAGES} initialized successfully")
                except Exception as e:
                    self.logger.error(f"Failed to initialize context {i+1}: {str(e)}")
                    raise

            # Process URLs in chunks
            url_chunks = [list(urls) for urls in self._chunk_urls(self.detail_urls, CHUNK_SIZE)]
            total_chunks = len(url_chunks)
            self.logger.info(f"Split {total_ads} URLs into {total_chunks} chunks of size {CHUNK_SIZE}")
            
            for chunk_index, url_chunk in enumerate(url_chunks):
                chunk_start_time = datetime.now()
                self.logger.info(f"Processing chunk {chunk_index + 1}/{total_chunks} with {len(url_chunk)} URLs")
                
                tasks = []
                for i, url in enumerate(url_chunk):
                    page_index = i % len(pages)
                    self.logger.debug(f"Creating task for URL {url} using page {page_index + 1}")
                    task = asyncio.create_task(
                        self.extract_ad_details(
                            pages[page_index],
                            url,
                            f"[Chunk {chunk_index + 1}/{total_chunks}]"
                        )
                    )
                    tasks.append(task)
                
                # Process chunk in parallel
                try:
                    chunk_results = await asyncio.gather(*tasks, return_exceptions=True)
                    successful_results = []
                    
                    for i, result in enumerate(chunk_results):
                        if isinstance(result, Exception):
                            self.logger.error(f"Failed to process URL {url_chunk[i]}: {str(result)}")
                        elif result:
                            successful_results.append(result)
                    
                    all_ad_details.extend(successful_results)
                    
                    chunk_duration = (datetime.now() - chunk_start_time).total_seconds()
                    self.logger.info(
                        f"Chunk {chunk_index + 1}/{total_chunks} completed: "
                        f"{len(successful_results)}/{len(url_chunk)} successful in {chunk_duration:.2f}s"
                    )
                    
                except Exception as e:
                    self.logger.error(f"Error processing chunk {chunk_index + 1}: {str(e)}")
                
                # Add delay between chunks
                if chunk_index > 0:
                    self.logger.debug(f"Waiting {RETRY_DELAY * 2}s between chunks to avoid rate limiting")
                    await asyncio.sleep(RETRY_DELAY * 2)

        except Exception as e:
            self.logger.error(f"Fatal error during parallel processing: {str(e)}", exc_info=True)
            raise
        
        finally:
            # Cleanup
            self.logger.debug("Cleaning up browser contexts")
            for i, context in enumerate(contexts):
                try:
                    await context.close()
                    self.logger.debug(f"Context {i+1} closed successfully")
                except Exception as e:
                    self.logger.error(f"Error closing context {i+1}: {str(e)}")
        
        # Final statistics
        total_duration = (datetime.now() - start_time).total_seconds()
        success_rate = (len(all_ad_details) / total_ads) * 100
        
        self.logger.info(
            f"Processing complete: {len(all_ad_details)}/{total_ads} ads processed successfully "
            f"({success_rate:.1f}%) in {total_duration:.2f}s"
        )
        
        return all_ad_details

    async def extract_ad_details(self, page: Page, url: str, progress: str = "") -> dict:
        """Extract details from a single ad page with retry logic"""
        retry_count = 0
        while retry_count < RETRY_COUNT:
            try:
                # Reset page if needed
                if retry_count > 0:
                    await page.reload()
                    await asyncio.sleep(RETRY_DELAY * (retry_count + 1))  # Exponential backoff
                
                # Add initial wait before navigation
                await asyncio.sleep(2)
                
                # More robust navigation
                await page.goto(
                    url, 
                    wait_until='networkidle',  # Changed from domcontentloaded
                    timeout=NAVIGATION_TIMEOUT
                )
                
                # Wait for any of these selectors
                try:
                    await page.wait_for_selector(
                        '.ad-library-preview-container, .about-ad__availability-duration, .ad-analytics__country-impressions',
                        timeout=PAGE_TIMEOUT,
                        state='visible'  # Wait for actual visibility
                    )
                except Exception as e:
                    self.logger.warning(f"{progress} Timeout waiting for content: {str(e)}, retrying...")
                    retry_count += 1
                    continue

                # Basic ad details
                ad_details = {
                    'url': url,
                    'ad_id': url.split('/')[-1],
                    'company_id': self.company_id
                }

                # Extract campaign dates
                try:
                    date_selector = '.about-ad__availability-duration'
                    await page.wait_for_selector(date_selector, timeout=5000)
                    duration_text = await page.eval_on_selector(date_selector, 'el => el.innerText')
                    
                    # Parse dates from text like "Ran from Mar 1, 2024 to Mar 15, 2024"
                    if 'Ran from' in duration_text:
                        dates = duration_text.replace('Ran from ', '').split(' to ')
                        ad_details['start_date'] = format_date(dates[0])
                        ad_details['end_date'] = format_date(dates[1]) if len(dates) > 1 else None
                except Exception as e:
                    self.logger.debug(f"Failed to extract dates: {str(e)}")
                    ad_details['start_date'] = None
                    ad_details['end_date'] = None

                # Extract impressions range
                try:
                    impressions_selector = 'p:has-text("Total Impressions") + p'
                    impressions = await page.eval_on_selector(impressions_selector, 'el => el.innerText')
                    ad_details['total_impressions_range'] = clean_text(impressions)
                except Exception:
                    ad_details['total_impressions_range'] = None

                # Extract country impressions
                try:
                    country_selector = '.ad-analytics__country-impressions'
                    countries = await page.query_selector_all(country_selector)
                    country_impressions = []
                    
                    for country_elem in countries:
                        aria_label = await country_elem.get_attribute('aria-label')
                        if aria_label:
                            country, percentage = aria_label.split(', impressions ')
                            country_impressions.append({
                                'country': country,
                                'impressionsPercentage': percentage
                            })
                    ad_details['country_impressions'] = country_impressions
                except Exception:
                    ad_details['country_impressions'] = []

                # Extract advertiser details
                try:
                    logo_selector = 'img[alt="advertiser logo"]'
                    logo_elem = await page.query_selector(logo_selector)
                    if logo_elem:
                        ad_details['advertiser_logo_url'] = await logo_elem.get_attribute('src')
                    
                    advertiser_selector = 'a[href*="/company/"], a[href*="/in/"]'
                    advertiser_elem = await page.query_selector(advertiser_selector)
                    if advertiser_elem:
                        ad_details['advertiser_name'] = await advertiser_elem.inner_text()
                        href = await advertiser_elem.get_attribute('href')
                        ad_details['ad_type'] = 'personal_ad' if '/in/' in href else 'company_ad'
                except Exception:
                    ad_details['advertiser_logo_url'] = None
                    ad_details['advertiser_name'] = None
                    ad_details['ad_type'] = None

                # Extract company ID from the page
                try:
                    company_link_selector = 'a[href*="/company/"]'
                    company_link = await page.query_selector(company_link_selector)
                    if company_link:
                        href = await company_link.get_attribute('href')
                        company_id_match = re.search(r'/company/(\d+)', href)
                        if company_id_match:
                            ad_details['company_id'] = company_id_match.group(1)
                        else:
                            ad_details['company_id'] = self.company_id
                    else:
                        ad_details['company_id'] = self.company_id
                except Exception as e:
                    self.logger.debug(f"Failed to extract company ID: {str(e)}")
                    ad_details['company_id'] = self.company_id  # Fallback to initialized company_id

                # Extract creative content
                try:
                    # Headline
                    headline_selector = '.headline'
                    headline = await page.eval_on_selector(headline_selector, 'el => el.innerText')
                    ad_details['headline'] = clean_text(headline)
                except Exception:
                    ad_details['headline'] = clean_text(None)

                # Description/text content
                try:
                    description_selector = '.commentary__content, .ad-library-preview-creative-text'
                    description = await page.eval_on_selector(description_selector, 'el => el.innerText')
                    ad_details['text_content'] = clean_text(description)
                except Exception:
                    ad_details['text_content'] = clean_text(None)

                # Extract image URL
                try:
                    img_selector = 'img.ad-preview__dynamic-dimensions-image'
                    img_elem = await page.query_selector(img_selector)
                    if img_elem:
                        ad_details['image_url'] = await img_elem.get_attribute('src')
                except Exception:
                    ad_details['image_url'] = None

                # Extract redirect URL and UTM parameters
                try:
                    link_selector = 'a[data-tracking-control-name="ad_library_ad_preview_headline_content"]'
                    link_elem = await page.query_selector(link_selector)
                    if link_elem:
                        full_url = await link_elem.get_attribute('href')
                        url_parts = full_url.split('?')
                        ad_details['redirect_url'] = url_parts[0]
                        ad_details['utm_parameters'] = url_parts[1] if len(url_parts) > 1 else None
                except Exception:
                    ad_details['redirect_url'] = None
                    ad_details['utm_parameters'] = None

                # Extract demographics (using existing method)
                ad_details['demographics'] = await self._extract_demographics(page)

                return ad_details

            except Exception as e:
                retry_count += 1
                if retry_count < RETRY_COUNT:
                    self.logger.warning(f"Retry {retry_count}/{RETRY_COUNT} for URL {url}: {str(e)}")
                    await asyncio.sleep(2)
                else:
                    self.logger.error(f"Failed to extract details from {url} after {RETRY_COUNT} retries: {str(e)}")
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
            self.logger.error(f"Error extracting demographics: {str(e)}")
        
        return demographics

    def _chunk_urls(self, urls, size):
        """Split URLs into chunks of specified size"""
        urls = list(urls)
        return [urls[i:i + size] for i in range(0, len(urls), size)]