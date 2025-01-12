from playwright.async_api import Page
import logging
import asyncio
from .config import (
    crawler_config,
    browser_config,
    MAX_CONCURRENT_PAGES,
    VIEWPORT_CONFIG,
    USER_AGENT,
    RETRY_COUNT,
    RETRY_DELAY,
    NAVIGATION_TIMEOUT,
    CHUNK_SIZE
)
from .utils import clean_text, clean_percentage, format_date
from src.logger import setup_logger
import re
from datetime import datetime, timedelta, date
import time
from sqlalchemy.orm import Session
from src.models import LinkedInAd
from src.utils import generate_linkedin_url
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json

logger = setup_logger("crawler", "DEBUG")

class AsyncLinkedInCrawler:
    def __init__(self, company_id: str, max_requests: int = 50):
        self.company_id = company_id
        self.max_requests = max_requests
        self.detail_urls = set()
        self.logger = setup_logger("crawler")
        self.consecutive_timeouts = 0
        self.max_consecutive_timeouts = 3
        # Add performance metrics
        self.metrics = {
            'start_time': None,
            'url_collection_time': None,
            'processing_times': [],
            'failed_urls': set(),
            'success_rate': 0,
            'avg_processing_time': 0
        }
        self.active_contexts = []
        self.active_pages = []

    async def collect_ad_urls(self, page: Page) -> None:
        """Collect all ad URLs from the page"""
        self.metrics['start_time'] = time.time()
        self.logger.info("Starting URL collection")
        
        url = generate_linkedin_url(self.company_id)
        self.logger.info(f"Navigating to {url}")
        
        try:
            # Simple initial load - we just need the page to start
            await page.goto(
                url, 
                wait_until='domcontentloaded', 
                timeout=browser_config.NAVIGATION_TIMEOUT
            )
            await asyncio.sleep(crawler_config.INITIAL_WAIT_TIME)
            
            previous_links_count = 0
            consecutive_unchanged_counts = 0
            scroll_count = 0

            # Optimized scroll loop for endless scroll
            while True:
                self.logger.debug(f"Scroll iteration {scroll_count}")
                
                try:
                    # Add more detailed logging
                    self.logger.debug("Attempting to scroll...")
                    await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    
                    # Incremental wait time based on consecutive unchanged counts
                    wait_time = crawler_config.BASE_SCROLL_WAIT + (consecutive_unchanged_counts * crawler_config.SCROLL_INCREMENT)
                    self.logger.debug(f"Waiting for {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                    
                    # Log before link collection
                    self.logger.debug("Collecting links...")
                    links = await page.eval_on_selector_all(
                        "a[href*='/ad-library/detail/']",
                        "elements => Array.from(elements).map(el => el.href)"
                    )
                    
                    current_links = set(link.split('?')[0] for link in links)
                    new_links = len(current_links) - previous_links_count
                    
                    self.logger.debug(f"Current scroll position: {await page.evaluate('window.scrollY')}")
                    self.logger.debug(f"Page height: {await page.evaluate('document.body.scrollHeight')}")
                    
                    if new_links > 0:
                        self.logger.info(f"Found {new_links} new URLs. Total: {len(current_links)}")
                        consecutive_unchanged_counts = 0
                    else:
                        consecutive_unchanged_counts += 1
                        self.logger.debug(f"No new links found. Consecutive unchanged: {consecutive_unchanged_counts}")
                    
                    self.detail_urls.update(current_links)
                    previous_links_count = len(current_links)

                except Exception as e:
                    self.logger.error(f"Error during scroll: {str(e)}\nTraceback: {e.__traceback__}")
                    consecutive_unchanged_counts += 1

                scroll_count += 1

                # Exit if no new URLs after several attempts
                if consecutive_unchanged_counts >= crawler_config.MAX_UNCHANGED_SCROLLS:
                    # Try one final scroll check before giving up
                    try:
                        # Quick scroll to top and bottom
                        await page.evaluate('window.scrollTo(0, 0)')
                        await asyncio.sleep(crawler_config.SCROLL_WAIT_TIME)
                        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                        await asyncio.sleep(crawler_config.SCROLL_WAIT_TIME)
                        
                        # One final check for any missed URLs
                        final_links = await page.eval_on_selector_all(
                            "a[href*='/ad-library/detail/']",
                            "elements => Array.from(elements).map(el => el.href)"
                        )
                        final_set = set(link.split('?')[0] for link in final_links)
                        
                        if len(final_set) > len(self.detail_urls):
                            self.logger.info(f"Found {len(final_set) - len(self.detail_urls)} additional URLs in final check")
                            self.detail_urls.update(final_set)
                            consecutive_unchanged_counts = 0
                            continue
                        
                        self.logger.info("No new URLs found in final check, proceeding to process ads")
                        break  # This will exit the loop and continue to process_all_ads
                        
                    except Exception as e:
                        self.logger.error(f"Error during final check: {str(e)}")
                        break  # Even if final check fails, we should proceed to process collected URLs

                # Safety limit
                if scroll_count > crawler_config.MAX_SCROLL_COUNT:
                    self.logger.warning("Reached maximum scroll count")
                    break

            self.logger.info(f"URL collection complete. Found {len(self.detail_urls)} unique URLs")
            self.metrics['url_collection_time'] = time.time() - self.metrics['start_time']

        except Exception as e:
            self.logger.error(f"Failed to collect URLs: {str(e)}")

    async def process_all_ads(self, page: Page, db: AsyncSession) -> int:
        """Process all collected ad URLs and save them to the database"""
        processing_start = time.time()
        total_ads = len(self.detail_urls)
        
        if total_ads == 0:
            self.logger.warning("No ads found to process")
            return 0
        
        start_time = datetime.now()
        new_ads = 0
        updated_ads = 0
        existing_ads = 0
        
        self.logger.info(f"Starting parallel processing of {total_ads} ads")
        
        try:
            browser = page.context.browser
            contexts = []
            pages = []
            
            # Initialize parallel contexts
            for i in range(MAX_CONCURRENT_PAGES):
                context = await browser.new_context(
                    viewport=VIEWPORT_CONFIG,
                    user_agent=USER_AGENT
                )
                contexts.append(context)
                pages.append(await context.new_page())

            # Process all URLs without chunking
            new_ads, updated_ads, existing_ads = await self.process_urls(
                list(self.detail_urls), pages, db
            )

            # Calculate final metrics
            total_time = time.time() - processing_start
            if total_ads > 0:
                self.metrics['success_rate'] = ((total_ads - len(self.metrics['failed_urls'])) / total_ads) * 100
                if self.metrics['processing_times']:
                    self.metrics['avg_processing_time'] = sum(self.metrics['processing_times']) / len(self.metrics['processing_times'])
            
            self.logger.info(
                f"\nPerformance Metrics:\n"
                f"- Total Processing Time: {total_time:.2f}s\n"
                f"- Average Processing Time: {self.metrics['avg_processing_time']:.2f}s\n"
                f"- Success Rate: {self.metrics['success_rate']:.1f}%\n"
                f"- Failed URLs: {len(self.metrics['failed_urls'])}\n"
                f"- New Ads: {new_ads}\n"
                f"- Updated Ads: {updated_ads}\n"
                f"- Existing Ads: {existing_ads}"
            )

        finally:
            # Cleanup
            for context in contexts:
                await context.close()

        total_duration = (datetime.now() - start_time).total_seconds()
        processed_count = new_ads + updated_ads + existing_ads
        success_rate = (processed_count / total_ads) * 100 if total_ads > 0 else 0
        
        self.logger.info(
            f"Processing complete: {processed_count}/{total_ads} ads processed "
            f"({success_rate:.1f}%) in {total_duration:.2f}s"
        )
        
        return processed_count

    async def process_urls(self, urls: list, pages: list, db: AsyncSession) -> tuple[int, int, int]:
        """Process all URLs without chunking and track progress"""
        new_ads = updated_ads = existing_ads = 0
        total_urls = len(urls)
        processed_count = 0
        consecutive_existing_count = 0  # Counter for consecutive 'existing' statuses

        for i, url in enumerate(urls):
            page_index = i % len(pages)
            try:
                ad_details = await self.extract_ad_details(pages[page_index], url)
                if ad_details:
                    status = await self.upsert_ad(db, ad_details)
                    if status == 'new':
                        new_ads += 1
                        consecutive_existing_count = 0  # Reset counter
                    elif status == 'updated':
                        updated_ads += 1
                        consecutive_existing_count = 0  # Reset counter
                    elif status == 'existing':
                        existing_ads += 1
                        consecutive_existing_count += 1  # Increment counter

                    # Log detailed information about the ad processing status
                    self.logger.info(
                        f"Ad ID={ad_details.get('ad_id')} processed: Status={status}"
                    )

                    # Check if the consecutive 'existing' count exceeds 30
                    if consecutive_existing_count > 30:
                        self.logger.info("Aborting further processing due to 30+ consecutive 'existing' ads.")
                        break

                processed_count += 1
                self.logger.info(f"Processed {processed_count}/{total_urls} ads ({(processed_count/total_urls)*100:.1f}%)")
            except Exception as e:
                self.logger.error(f"Failed to process URL: {str(e)}")

        self.logger.info(
            f"Processed ads (New: {new_ads}, Updated: {updated_ads}, Existing: {existing_ads})"
        )
        return new_ads, updated_ads, existing_ads

    async def extract_ad_details(self, page: Page, url: str, progress: str = "") -> dict:
        """Extract details from a single ad page"""
        for attempt in range(RETRY_COUNT):
            try:
                # Block unnecessary resources before navigation
                await page.route("**/*", lambda route: self._filter_requests(route))
                
                start_time = datetime.now()
                total_size = 0
                response_count = 0
                
                metrics = {
                    'url': url,
                    'attempt': attempt + 1,
                    'size_mb': 0,
                    'resources': 0,
                    'timing': {}
                }

                async def handle_response(response):
                    nonlocal total_size, response_count
                    try:
                        if response.request.resource_type in metrics['timing']:
                            metrics['timing'][response.request.resource_type] += 1
                        else:
                            metrics['timing'][response.request.resource_type] = 1
                        
                        headers = response.headers
                        if 'content-length' in headers:
                            size = int(headers['content-length'])
                            total_size += size
                            response_count += 1
                    except Exception as e:
                        self.logger.debug(f"Error tracking metrics: {str(e)}")

                page.on('response', handle_response)

                # Use a more reliable navigation strategy
                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=NAVIGATION_TIMEOUT
                )

                duration = (datetime.now() - start_time).total_seconds()
                metrics['duration'] = duration
                metrics['size_mb'] = total_size / (1024 * 1024)
                metrics['resources'] = response_count

                self.logger.info(
                    f"Page load metrics for {url}:\n"
                    f"- Duration: {duration:.2f}s\n"
                    f"- Size: {metrics['size_mb']:.2f}MB\n"
                    f"- Resources: {response_count}\n"
                    f"- Resource types: {dict(metrics['timing'])}"
                )

                if response.status == 429:  # Rate limit
                    await asyncio.sleep(30)  # Longer cooldown
                    continue
                    
                if not response.ok:
                    self.logger.error(f"HTTP {response.status} on attempt {attempt + 1}")
                    continue

                # Add a small delay to ensure content is loaded
                await asyncio.sleep(1)
                
                return await self._extract_page_content(page)
                    
            except Exception as e:
                self.logger.warning(f"Warning on attempt {attempt + 1}: {str(e)}")
                if attempt < RETRY_COUNT - 1:
                    wait_time = 5 * (attempt + 1)  # Exponential backoff
                    await asyncio.sleep(wait_time)
                    continue
                return None

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

    async def _extract_page_content(self, page: Page) -> dict:
        """Extract detailed ad content from the page"""
        try:
            await page.wait_for_load_state('networkidle')
            ad_data = {}
            
            # Get the page HTML
            html_content = await page.content()
            
            # Extract Ad ID (primary key)
            ad_id_match = re.search(r'<link rel="canonical" href="/ad-library/detail/(\d+)">', html_content)
            if not ad_id_match:
                self.logger.warning('Ad ID not found, skipping ad.')
                return None
            ad_data['ad_id'] = ad_id_match.group(1)
            
            # Extract Campaign Dates
            duration_match = re.search(r'<p class="about-ad__availability-duration[^"]*"[^>]*>([^<]*)</p>', html_content)
            if duration_match:
                duration_text = duration_match.group(1).strip()
                date_range = re.search(r'Ran from (\w+ \d{1,2}, \d{4})(?:\s+to\s+(\w+ \d{1,2}, \d{4}))?', duration_text)
                if date_range:
                    # Use exact field names from PostgreSQL model
                    ad_data['campaign_start_date'] = format_date(date_range.group(1))
                    ad_data['campaign_end_date'] = format_date(date_range.group(2)) if date_range.group(2) else None

            # Extract Total Impressions
            impressions_match = re.search(r'<p[^>]*>Total Impressions</p>\s*<p[^>]*>([^<]*)</p>', html_content)
            if impressions_match:
                ad_data['campaign_impressions_range'] = impressions_match.group(1).strip()

            # Extract Country Impressions
            country_impressions = []
            country_pattern = r'<span class="ad-analytics__country-impressions[^"]*"[^>]*aria-label="([^"]+), impressions ([^%]+%)"[^>]*>'
            for match in re.finditer(country_pattern, html_content):
                country_impressions.append({
                    'country': match.group(1),
                    'percentage': match.group(2)
                })
            ad_data['campaign_impressions_by_country'] = country_impressions

            # Extract Advertiser Info
            logo_match = re.search(r'<img[^>]*data-delayed-url="([^"]+)"[^>]*alt="advertiser logo"[^>]*>', html_content)
            if logo_match:
                ad_data['advertiser_logo'] = logo_match.group(1)

            advertiser_match = re.search(r'<a[^>]*href="https://www\.linkedin\.com/(?:company|in)/[^"]+"[^>]*>\s*([^<]+)\s*</a>', html_content)
            if advertiser_match:
                ad_data['advertiser_name'] = advertiser_match.group(1).strip()

            # Extract Creative Type
            creative_match = re.search(r'<div[^>]*data-creative-type="([^"]+)"[^>]*>', html_content)
            if creative_match:
                ad_data['creative_type'] = creative_match.group(1)

            # Determine Ad Type
            ad_data['ad_type'] = 'personal_ad' if 'linkedin.com/in/' in html_content else 'company_ad'

            # Extract Redirect URL and UTM
            redirect_match = re.search(r'<a[^>]*href="([^"]+)"[^>]*data-tracking-control-name="ad_library_ad_preview_headline_content"[^>]*>', html_content)
            if redirect_match:
                full_url = redirect_match.group(1)
                url_parts = full_url.split('?')
                ad_data['ad_redirect_url'] = url_parts[0]
                ad_data['utm_parameters'] = url_parts[1] if len(url_parts) > 1 else None

            # Extract Content
            headline_match = re.search(r'<h1[^>]*class="headline"[^>]*>([^<]+)</h1>', html_content)
            if headline_match:
                ad_data['headline'] = headline_match.group(1).strip()

            description_match = re.search(r'<p[^>]*class="[^"]*commentary__content[^"]*"[^>]*>([\s\S]*?)</p>', html_content)
            if description_match:
                ad_data['description'] = clean_text(description_match.group(1).strip())
            else:
                self.logger.warning(f"Description not found for adId: {ad_data.get('ad_id')}")
                ad_data['description'] = None

            # Extract Image URL
            img_match = re.search(r'<img[^>]*class="[^"]*ad-preview__dynamic-dimensions-image[^"]*"[^>]*src="([^"]+)"', html_content)
            if img_match:
                ad_data['image_url'] = img_match.group(1).replace('&amp;', '&')

            # Extract Company ID
            company_match = re.search(r'<a[^>]*href="https://www\.linkedin\.com/company/(\d+)"[^>]*>', html_content)
            if company_match:
                ad_data['company_id'] = company_match.group(1)

            # Instead of trying to extract company_id from the page,
            # use the one provided during crawler initialization
            ad_data['company_id'] = int(self.company_id)  # Make sure it's an integer

            return ad_data

        except Exception as e:
            self.logger.error(f"Error in content extraction: {str(e)}")
            return None

    # Add request filtering
    async def _filter_requests(self, route):
        """Filter out unnecessary resources to reduce page load size"""
        request = route.request
        resource_type = request.resource_type
        url = request.url.lower()

        # Always allow main document and essential ad content
        if resource_type == "document" or "ad-library" in url:
            await route.continue_()
            return

        # Block specific resource types
        if resource_type in ["media", "video", "font"]:
            await route.abort()
            return

        # Block large image formats
        if resource_type == "image" and any(ext in url for ext in ['.gif', '.webp']):
            await route.abort()
            return

        # Block non-essential scripts and stylesheets
        if resource_type in ["script", "stylesheet"] and not any(
            essential in url for essential in [
                "ad-library",
                "essential",
                "core"
            ]
        ):
            await route.abort()
            return

        # Block tracking and analytics
        if any(pattern in url for pattern in [
            "analytics",
            "tracking",
            "metrics",
            "telemetry",
            "logging",
            "pixel",
            "beacon"
        ]):
            await route.abort()
            return

        # Allow everything else
        await route.continue_()

    async def upsert_ad(self, db: AsyncSession, ad_data: dict):
        """Upsert ad with consistent field names and transformations"""
        try:
            # Validate required fields
            if not ad_data.get('ad_id'):
                raise ValueError("ad_id is required")

            # Transform data once with correct field names
            transformed_data = self._transform_ad_data(ad_data)
            
            # Check for existing ad
            existing_ad = await db.execute(
                select(LinkedInAd).where(LinkedInAd.ad_id == transformed_data['ad_id'])
            )
            existing_ad = existing_ad.scalars().first()

            if existing_ad:
                # Update existing ad if needed
                needs_update = False
                for field, new_value in transformed_data.items():
                    current_value = getattr(existing_ad, field)
                    
                    # Skip id field
                    if field == 'ad_id':
                        continue
                        
                    # Handle different types of comparisons
                    if isinstance(current_value, (date, datetime)):
                        if new_value and current_value != new_value:
                            setattr(existing_ad, field, new_value)
                            needs_update = True
                    elif isinstance(current_value, (dict, list)):
                        if new_value and json.dumps(current_value) != json.dumps(new_value):
                            setattr(existing_ad, field, new_value)
                            needs_update = True
                    elif current_value != new_value:
                        setattr(existing_ad, field, new_value)
                        needs_update = True
                
                if needs_update:
                    await db.commit()
                    return 'updated'
                return 'existing'
            else:
                # Create new ad
                new_ad = LinkedInAd(**transformed_data)
                db.add(new_ad)
                await db.commit()
                return 'new'

        except Exception as e:
            await db.rollback()
            self.logger.error(f"Error in upsert_ad: {str(e)}")
            raise

    def _transform_ad_data(self, data: dict) -> dict:
        """Transform ad data to match LinkedInAd model fields"""
        transformed = {}
        
        # Direct field mappings (all fields should match LinkedInAd model)
        for field in [
            'ad_id', 'creative_type', 'advertiser_name', 'advertiser_logo',
            'headline', 'description', 'promoted_text', 'image_url',
            'view_details_link', 'campaign_impressions_range',
            'company_id', 'ad_type', 'ad_redirect_url', 'utm_parameters'
        ]:
            if field in data:
                transformed[field] = data[field]
        
        # Handle date fields
        for date_field in ['campaign_start_date', 'campaign_end_date']:
            if data.get(date_field):
                try:
                    transformed[date_field] = datetime.strptime(
                        data[date_field], '%Y/%m/%d'
                    ).date()
                except ValueError:
                    transformed[date_field] = None
        
        # Handle JSON fields
        if 'campaign_impressions_by_country' in data:
            transformed['campaign_impressions_by_country'] = (
                data['campaign_impressions_by_country']
                if isinstance(data['campaign_impressions_by_country'], (dict, list))
                else json.loads(data['campaign_impressions_by_country'])
            )
        
        # Ensure company_id is integer
        if 'company_id' in transformed:
            try:
                transformed['company_id'] = int(transformed['company_id'])
            except (ValueError, TypeError):
                transformed['company_id'] = None
        
        return transformed

    async def cleanup(self):
        """Ensure all browser resources are properly cleaned up"""
        for context in self.active_contexts:
            try:
                await context.close()
            except Exception as e:
                self.logger.error(f"Error closing context: {e}")
        
        self.active_contexts = []
        self.active_pages = []