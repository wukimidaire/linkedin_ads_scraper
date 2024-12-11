# LinkedIn Ad Library Crawler

<p align="center">
  <img src="[your-logo-url]" alt="LinkedIn Ad Crawler Logo" width="200"/>
</p>

<p align="center">
  <a href="#key-features">Features</a> •
  <a href="#installation">Installation</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#deployment">Deployment</a> •
  <a href="#documentation">Documentation</a>
</p>

## 📋 Overview

A high-performance web crawler that helps businesses and researchers analyze advertising strategies on LinkedIn by automatically collecting and analyzing ads from LinkedIn's Ad Library. Built with FastAPI and Playwright, this tool provides valuable competitive intelligence and market research data.

### 🎯 Problem Statement

LinkedIn's Ad Library contains valuable insights about how companies advertise on the platform, but manually collecting this data is time-consuming. This crawler automates the process by:

- 🤖 Collecting ads from any company's LinkedIn Ad Library
- 📊 Extracting detailed metrics and creative content
- 🗃️ Organizing data in a structured JSON format
- 🔌 Providing an API endpoint for easy integration

## ✨ Key Features

### Data Collection
- Campaign dates and duration
- Impression ranges and geographic distribution
- Demographic targeting (age, gender, seniority)
- Creative content (images, text, headlines)
- UTM parameters for campaign tracking
- Advertiser information

### Technical Capabilities
- ⚡ Asynchronous crawling with Playwright
- 🔄 Parallel processing for faster data collection
- 🛡️ Rate limiting and retry mechanisms
- 📝 Detailed logging system
- 🐳 Docker containerization
- ☁️ Cloud-ready deployment

## 🚀 Getting Started

### Prerequisites
- Python 3.8+
- Docker (for containerized deployment)
- Google Cloud SDK (for cloud deployment)

### Installation

```bash
# Clone the repository
git clone [your-repository-url]
cd linkedin-ad-crawler

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Quick Start

```bash
# Run the application
uvicorn app:app --reload

# Access the API
# Swagger UI: http://localhost:8080/docs
# API endpoint: http://localhost:8080/crawl?company_id=[company-id]
```

## 🌐 Deployment Options

### Docker Deployment

```bash
# Build and run container
docker build -t linkedin-crawler .
docker run -p 8080:8080 linkedin-crawler
```

### Google Cloud Run Deployment

```bash
# Configure Google Cloud SDK
gcloud init
gcloud auth configure-docker
```

## 🔧 Configuration

### Environment Variables
- `PORT`: Server port (default: 8080)
- `LOG_LEVEL`: Logging level (default: INFO)
- `MAX_CONCURRENT_PAGES`: Maximum parallel pages (default: 2)
- `RETRY_COUNT`: Number of retry attempts (default: 3)

### Resource Requirements
- Memory: Minimum 2GB recommended
- CPU: 2 cores recommended
- Storage: Minimal (~500MB)

## 📊 Example Output

The crawler returns structured JSON data containing ad details:


json
{
"adId": "123456789",
"advertiserName": "Company Name",
"startDate": "2024/01/01",
"endDate": "2024/01/31",
"totalImpressionsRange": "10k-50k",
"countryImpressions": [...],
"demographics": {...},
"creativeContent": {...}
}


## 🔐 Security & Rate Limiting

- Built-in rate limiting to prevent API abuse
- Request filtering for optimal performance
- Browser isolation in containerized environment
- Automatic retry mechanism for failed requests

## 📝 Logging & Monitoring

- Structured logging with timestamp and severity levels
- Automatic integration with Google Cloud Logging
- Performance metrics tracking
- Error tracking and reporting

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## ⚠️ Disclaimer

This tool is for research purposes only. Ensure compliance with LinkedIn's terms of service and rate limiting policies when using this crawler.

## 📄 License

[Your License Type] - See LICENSE file for details

## 🆘 Support

- Create an issue for bug reports or feature requests
- Check existing issues before creating new ones
- Include relevant details and error logs in bug reports