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
from dotenv import load_dotenv
import os
import aiohttp
from playwright.async_api import async_playwright

class AsyncLinkedInCrawler:
    def __init__(self, company_id: str, max_requests: int = 50):
        self.company_id = company_id
        self.max_requests = max_requests
        self.detail_urls = set()
        self.logger = setup_logger("crawler")
        
        # Load proxy credentials
        load_dotenv()
        self.username = os.getenv('PROXY_USERNAME')
        self.password = os.getenv('PROXY_PASSWORD')
        
        if not self.username or not self.password:
            raise ValueError("Proxy credentials not found in .env file")
        
        # Initialize the proxy pool with HTTP proxies
        self.proxy_pool = [
            f"http://{self.username}:{self.password}@dc.smartproxy.com:{port}"
            for port in range(10001, 10101)  # Adjust port range as needed
        ]
        self.current_proxy_index = 0

    def _blacklist_proxy(self, proxy_server: str, blacklist_duration: int = 300):
        """Blacklist a proxy server for a specified duration."""
        if not hasattr(self, 'blacklisted_proxies'):
            self.blacklisted_proxies = {}
        
        self.blacklisted_proxies[proxy_server] = asyncio.get_event_loop().time() + blacklist_duration
        self.logger.warning(f"Blacklisted proxy: {proxy_server} for {blacklist_duration} seconds")
    
    def get_next_proxy(self) -> dict:
        """Get the next proxy configuration in the correct format for Playwright."""
        proxy_url = self.proxy_pool[self.current_proxy_index]
        self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxy_pool)
        
        try:
            # Parse the proxy URL
            proxy_parts = proxy_url.split('://')
            protocol = proxy_parts[0]  # http or socks5
            auth_host_port = proxy_parts[1].split('@')
            
            if len(auth_host_port) == 2:
                auth, host_port = auth_host_port
                username, password = auth.split(':')
                host, port = host_port.split(':')
            else:
                host_port = auth_host_port[0]
                host, port = host_port.split(':')
                username = self.username
                password = self.password
            
            # Format proxy config according to Playwright's requirements
            return {
                "server": f"{host}:{port}",  # Remove protocol prefix
                "username": username,
                "password": password
            }
        except Exception as e:
            self.logger.error(f"Error parsing proxy URL {proxy_url}: {str(e)}")
            # Return a fallback proxy if available, or raise the exception
            raise

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

    async def create_browser_context(self, browser, url):
        """Creates and validates a browser context with a proxy."""
        max_retries = 3
        for attempt in range(max_retries):
            proxy_config = self.get_next_proxy()
            try:
                context = await browser.new_context(
                    viewport=VIEWPORT_CONFIG,
                    user_agent=USER_AGENT,
                    proxy={
                        "server": proxy_config["server"],
                        "username": proxy_config.get("username"),  # Use get to handle missing keys
                        "password": proxy_config.get("password")
                    }
                )

                # Validate the proxy within Playwright
                async def check_proxy(route):
                    await route.continue_()  # Allow the request

                intercepted_request = False
                async def handle_request(route):
                    nonlocal intercepted_request
                    intercepted_request = True
                    await check_proxy(route)

                page = await context.new_page()
                await page.route("**/*", handle_request)  # Intercept requests to ensure proxy works
                try:
                    await page.goto("https://www.linkedin.com", timeout=10000, wait_until="domcontentloaded") # Use LinkedIn for validation
                except Exception as e:
                    raise Exception(f"Proxy validation failed: {e}") from e
                finally:
                    await page.close()

                if not intercepted_request:
                    raise Exception("Proxy not used for requests")

                self.logger.debug(f"Proxy {proxy_config['server']} validated successfully for {url}")
                return context, proxy_config
            except Exception as e:
                self.logger.error(f"Proxy setup failed for {url} (attempt {attempt+1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    raise  # Re-raise the exception after all retries fail
                # Optionally add a delay between retries
                await asyncio.sleep(2)
                continue # proceed to the next attempt

    async def process_all_ads(self, page: Page) -> list:
        all_ad_details = []
        browser = page.context.browser
        
        try:
            url_chunks = [list(chunk) for chunk in self._chunk_urls(self.detail_urls, CHUNK_SIZE)]
            
            for chunk_index, chunk in enumerate(url_chunks):
                self.logger.info(f"Processing chunk {chunk_index + 1}/{len(url_chunks)}")
                tasks = []
                contexts = []
                
                for url in chunk:
                    try:
                        context, proxy_config = await self.create_browser_context(browser, url)
                        contexts.append(context)
                        
                        new_page = await context.new_page()
                        await new_page.route("**/*", self._filter_requests)
                        
                        task = asyncio.create_task(
                            self.extract_ad_details(new_page, url)
                        )
                        tasks.append(task)
                        
                    except Exception as e:
                        self.logger.error(f"Failed to set up context for URL {url}: {str(e)}")
                        continue
                
                if tasks:
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    successful_results = [r for r in results if isinstance(r, dict)]
                    all_ad_details.extend(successful_results)
                
                # Clean up contexts
                for context in contexts:
                    await context.close()
                
                # Add delay between chunks
                await asyncio.sleep(2)
        
        except Exception as e:
            self.logger.error(f"Error in process_all_ads: {str(e)}")
            raise
        
        return all_ad_details

    async def extract_ad_details(self, page: Page, url: str, progress: str = "") -> dict:
        """Extract detailed ad content from the page."""
        for attempt in range(RETRY_COUNT):
            try:
                # Get proxy config for this request
                proxy_config = self.get_next_proxy()
                
                # Update the route handler to include proxy_config
                await page.route("**/*", lambda route: self._filter_requests(route, proxy_config))
                
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
                if attempt == RETRY_COUNT - 1:
                    self.logger.error(f"Failed to process {url} after {RETRY_COUNT} attempts")
                    return None
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))  # Progressive delay
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
    async def _filter_requests(self, route, proxy_config=None):
        """Filter and modify requests with proper error handling."""
        try:
            if route.request.resource_type in ['image', 'stylesheet', 'font']:
                await route.abort()
                return
            
            headers = route.request.headers.copy()
            headers['User-Agent'] = USER_AGENT
            
            # Add proxy authentication headers if needed
            if proxy_config:
                headers['Proxy-Authorization'] = f"Basic {proxy_config.get('auth', '')}"
            
            await route.continue_(headers=headers)
            
        except Exception as e:
            self.logger.error(f"Route error: {str(e)}")
            await route.abort()

    async def test_proxies(self):
        """Test all proxies in the pool."""
        for proxy in self.proxy_pool:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        'https://ip.smartproxy.com/json',
                        proxy=proxy,  # HTTP proxy
                        timeout=10
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            self.logger.info(f"Proxy {proxy} is working. IP: {data.get('proxy', {}).get('ip')}")
                        else:
                            self.logger.error(f"Proxy {proxy} returned status {response.status}")
                            self._blacklist_proxy(proxy.split('://')[-1].split('@')[0])
            except Exception as e:
                self.logger.error(f"Proxy {proxy} failed: {str(e)}")
                self._blacklist_proxy(proxy.split('://')[-1].split('@')[0])

    async def _test_proxy_connection(self, context, proxy_info):
        """Test proxy connection before using it"""
        try:
            test_page = await context.new_page()
            await test_page.goto('https://ip.smartproxy.com/json', 
                               timeout=5000,
                               wait_until='networkidle')
            await test_page.close()
            return True
        except Exception as e:
            self.logger.error(f"Proxy test failed for {proxy_info['server']}: {str(e)}")
            return False

    async def validate_proxy(self, proxy_config: dict) -> bool:
        """Validate proxy configuration before using it."""
        try:
            async with aiohttp.ClientSession() as session:
                proxy_url = f"http://{proxy_config['username']}:{proxy_config['password']}@{proxy_config['server']}"
                async with session.get(
                    'https://ip.smartproxy.com/json',
                    proxy=proxy_url,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        self.logger.debug(f"Proxy {proxy_config['server']} validated successfully")
                        return True
                    else:
                        self.logger.warning(f"Proxy {proxy_config['server']} validation failed with status {response.status}")
                        return False
        except Exception as e:
            self.logger.error(f"Proxy {proxy_config['server']} validation error: {str(e)}")
            return False

async def test_proxy(proxy_config):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(proxy=proxy_config)
            page = await context.new_page()
            await page.goto('https://ip.smartproxy.com/json', timeout=10000)
            content = await page.content()
            print(content)
            await context.close()
        except Exception as e:
            print(f"Proxy {proxy_config['server']} failed: {e}")
        finally:
            await browser.close()
