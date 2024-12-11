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
        self.consecutive_timeouts = 0
        self.max_consecutive_timeouts = 3

    async def collect_ad_urls(self, page: Page) -> None:
        self.logger.info("Starting URL collection")
        previous_links_count = 0
        consecutive_unchanged_counts = 0
        scroll_count = 0
        last_height = 0

        # Wait for initial content
        try:
            await page.wait_for_selector("a[href*='/ad-library/detail/']", timeout=5000)
        except Exception as e:
            self.logger.warning(f"Initial content wait timeout: {str(e)}")

        while True:
            self.logger.debug(f"Scroll iteration {scroll_count}")
            
            # Get current scroll height
            current_height = await page.evaluate('document.body.scrollHeight')
            
            # Break if we've reached the bottom and no new content loaded
            if current_height == last_height:
                consecutive_unchanged_counts += 1
            else:
                consecutive_unchanged_counts = 0
                last_height = current_height

            # Scroll with more sophisticated approach
            try:
                await page.evaluate('''() => {
                    window.scrollTo({
                        top: document.body.scrollHeight,
                        behavior: 'instant'
                    });
                    // Trigger any lazy loading
                    window.dispatchEvent(new Event('scroll'));
                }''')
                
                # Wait for potential new content
                await asyncio.sleep(2)
                
                # Check for new ads with more specific selector
                links = await page.eval_on_selector_all(
                    "a[href*='/ad-library/detail/']",
                    "elements => Array.from(elements).map(el => el.href)"
                )
                
                current_links = set()
                for link in links:
                    clean_link = link.split('?')[0]
                    current_links.add(clean_link)
                    if clean_link not in self.detail_urls:
                        self.detail_urls.add(clean_link)
                        self.logger.debug(f"Found new URL: {clean_link}")

                # Log progress
                if len(current_links) > previous_links_count:
                    self.logger.info(f"Found {len(current_links) - previous_links_count} new URLs. Total: {len(self.detail_urls)}")
                
                previous_links_count = len(current_links)

            except Exception as e:
                self.logger.error(f"Error during scroll: {str(e)}")
                consecutive_unchanged_counts += 1

            scroll_count += 1

            # More sophisticated exit conditions
            if (consecutive_unchanged_counts >= 5 and scroll_count >= 3) or scroll_count >= 50:
                # Double-check by scrolling back up and down
                try:
                    await page.evaluate('window.scrollTo(0, 0)')
                    await asyncio.sleep(1)
                    await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    await asyncio.sleep(2)
                    
                    final_links = await page.eval_on_selector_all(
                        "a[href*='/ad-library/detail/']",
                        "elements => Array.from(elements).map(el => el.href)"
                    )
                    
                    for link in final_links:
                        clean_link = link.split('?')[0]
                        if clean_link not in self.detail_urls:
                            self.detail_urls.add(clean_link)
                            self.logger.debug(f"Found additional URL in final check: {clean_link}")
                    
                except Exception as e:
                    self.logger.error(f"Error during final check: {str(e)}")

                self.logger.info(f"URL collection complete. Found {len(self.detail_urls)} unique URLs")
                break

            # Prevent infinite loops
            if scroll_count > 100:
                self.logger.warning("Reached maximum scroll count")
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
                            error_msg = str(result)
                            if "Timeout" in error_msg:
                                self.consecutive_timeouts += 1
                                self.logger.warning(f"Timeout error {self.consecutive_timeouts}/3")
                                if self.consecutive_timeouts >= self.max_consecutive_timeouts:
                                    self.logger.error("Maximum consecutive timeouts reached. Stopping processing.")
                                    return all_ad_details
                            else:
                                self.consecutive_timeouts = 0
                            self.logger.error(f"Failed to process URL {url_chunk[i]}: {error_msg}")
                        elif result:
                            self.consecutive_timeouts = 0
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
            return all_ad_details
        
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
                self.logger.error(f"Error on attempt {attempt + 1}: {str(e)}")
                if "Timeout" in str(e):
                    raise
                if attempt == RETRY_COUNT - 1:
                    self.logger.error(f"Failed to process {url} after {RETRY_COUNT} attempts")
                    return None
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                continue

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

    async def process_chunk(self, chunk, pages):
        tasks = []
        for i, url in enumerate(chunk):
            # Add progressive delay
            delay = 2 + (i * 1)  # 2s, 3s, 4s, 5s
            await asyncio.sleep(delay)
            
            page_index = i % len(pages)
            task = asyncio.create_task(
                self.extract_ad_details(
                    pages[page_index],
                    url,
                    f"[Chunk {i+1}/{len(chunk)}]"
                )
            )
            tasks.append(task)

    async def _extract_page_content(self, page: Page) -> dict:
        """Extract detailed ad content from the page"""
        try:
            await page.wait_for_load_state('networkidle')
            ad_data = {}
            
            # Get the page HTML
            html_content = await page.content()
            
            # Extract Ad ID
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
                    ad_data['start_date'] = format_date(date_range.group(1))
                    ad_data['end_date'] = format_date(date_range.group(2)) if date_range.group(2) else None

            # Extract Total Impressions
            impressions_match = re.search(r'<p[^>]*>Total Impressions</p>\s*<p[^>]*>([^<]*)</p>', html_content)
            if impressions_match:
                ad_data['total_impressions'] = impressions_match.group(1).strip()

            # Extract Country Impressions
            country_impressions = []
            country_pattern = r'<span class="ad-analytics__country-impressions[^"]*"[^>]*aria-label="([^"]+), impressions ([^%]+%)"[^>]*>'
            for match in re.finditer(country_pattern, html_content):
                country_impressions.append({
                    'country': match.group(1),
                    'percentage': match.group(2)
                })
            ad_data['country_impressions'] = country_impressions

            # Extract Advertiser Info
            logo_match = re.search(r'<img[^>]*data-delayed-url="([^"]+)"[^>]*alt="advertiser logo"[^>]*>', html_content)
            if logo_match:
                ad_data['advertiser_logo_url'] = logo_match.group(1)

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
                ad_data['redirect_url'] = url_parts[0]
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
                ad_data['description'] = 'No description available.'

            # Extract Image URL
            img_match = re.search(r'<img[^>]*class="[^"]*ad-preview__dynamic-dimensions-image[^"]*"[^>]*src="([^"]+)"', html_content)
            if img_match:
                ad_data['image_url'] = img_match.group(1).replace('&amp;', '&')

            # Extract Company ID
            company_match = re.search(r'<a[^>]*href="https://www\.linkedin\.com/company/(\d+)"[^>]*>', html_content)
            if company_match:
                ad_data['company_id'] = company_match.group(1)

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