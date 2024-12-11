from playwright.sync_api import sync_playwright
import logging
from .config import json, logging, sync_playwright
from .crawler import LinkedInCrawler

def get_search_url(company_id: str) -> str:
    """Generate search URL based on input type"""
    if company_id.isdigit():
        logging.info(f"Searching by Company ID: {company_id}")
        return f"https://www.linkedin.com/ad-library/search?companyIds={company_id}"
    else:
        logging.info(f"Searching by Account Name: {company_id}")
        return f"https://www.linkedin.com/ad-library/search?accountOwner={company_id}"

def save_to_json(data: list, filename: str = 'ad_details.json') -> None:
    """Save data to JSON file"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logging.info(f"Results saved to {filename}")
    except Exception as e:
        logging.error(f"Error saving results: {str(e)}")

def main():
    company_id = input("Enter LinkedIn Company ID or Account Name: ")
    start_url = get_search_url(company_id)
    
    with sync_playwright() as p:
        crawler = LinkedInCrawler(company_id)
        
        try:
            # Setup browser and get page
            page = crawler.setup_browser(p)
            
            # Navigate to start URL
            response = page.goto(start_url, wait_until='domcontentloaded')
            if not response.ok:
                logging.error(f"Failed to load page: {response.status} {response.status_text}")
                return "[]"
            
            # Rest of your crawling logic
            crawler.collect_ad_urls(page)
            ad_details = crawler.process_all_ads(page)
            
            if ad_details:
                all_ads_data = ad_details
                save_to_json(all_ads_data)
                return json.dumps(all_ads_data, indent=2, ensure_ascii=False)
            
            return "[]"
            
        except Exception as e:
            logging.error(f"An error occurred: {str(e)}")
            return "[]"
        finally:
            crawler.cleanup()

if __name__ == "__main__":
    json_data = main()
    print(json_data)