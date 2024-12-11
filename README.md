# LinkedIn Ad Library Crawler

An asynchronous web crawler for collecting and analyzing ads from LinkedIn's Ad Library. This tool helps gather insights about advertising strategies on LinkedIn by extracting detailed information about ads, including demographics, impressions, and creative content.

## Features

- Asynchronous crawling using Playwright
- Parallel processing of ad pages
- Robust error handling and retry logic
- Detailed logging system
- Extracts comprehensive ad details including:
  - Campaign dates
  - Impression ranges
  - Geographic distribution
  - Demographics (age, gender, seniority)
  - Creative content (images, text, headlines)
  - UTM parameters
  - Advertiser information

## Requirements

- Python 3.8+
- Playwright
- Additional dependencies listed in requirements.txt

## Installation

1. Clone the repository: