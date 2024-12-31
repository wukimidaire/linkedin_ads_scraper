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

**Tech Stack**: Python, FastAPI, Playwright, Docker, PostgreSQL

**Key Features**:
  - Automated collection of LinkedIn Ad Library data
  - Asynchronous crawling with parallel processing
  - Structured data storage in PostgreSQL
  - RESTful API endpoints for data access

### 🎯 Problem Statement

LinkedIn's Ad Library contains valuable insights about how companies advertise on the platform, but manually collecting this data is time-consuming. This crawler automates the process by:

- 🤖 Collecting ads from any company's LinkedIn Ad Library
- 📊 Extracting detailed metrics and creative content
- 🗃️ Organizing data in a structured format in PostgreSQL
- 🔌 Providing API endpoints for easy integration

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
- 🗄️ PostgreSQL database integration

## 🚀 Getting Started

### Prerequisites
- Python 3.8+
- Docker (for containerized deployment)
- PostgreSQL
- Git

### Required Files Setup

Before starting, you need to create the following files that are not included in the repository:

1. Create `.env` file in the root directory:

```
# Database Configuration
POSTGRES_USER=your_username
POSTGRES_PASSWORD=your_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=linkedin_ads

# Environment
ENVIRONMENT=development
```

2. Create `.gitignore` file in the root directory:
```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
ENV/

# Environment
.env
.env.local
.env.*.local

# IDE
.idea/
.vscode/
*.swp
*.swo

# Logs
*.log
```

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

# Install Playwright browsers
playwright install chromium
playwright install-deps
```

### Database Setup

1. Create PostgreSQL database:
```bash
createdb linkedin_ads
```

2. Verify database connection:
```bash
psql -h localhost -U your_username -d linkedin_ads
```

3. The application will automatically create required tables on first run

## 🔐 Environment Variables Reference

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| POSTGRES_USER | Database username | - | Yes |
| POSTGRES_PASSWORD | Database password | - | Yes |
| POSTGRES_HOST | Database host | localhost | Yes |
| POSTGRES_PORT | Database port | 5432 | Yes |
| POSTGRES_DB | Database name | linkedin_ads | Yes |
| ENVIRONMENT | Deployment environment | development | No |

## 🌐 API Endpoints

### Available Endpoints

1. **Root Endpoint**
   - GET `/`: Welcome message and API status

2. **Crawler Endpoint**
   - GET `/crawl?company_id={company_id}`: Start crawling ads for a specific company

3. **Health Checks**
   - GET `/health`: Check API and database health
   - GET `/test-db`: Test database connection

4. **Ad Management**
   - GET `/check-ads/{company_id}`: Get all ads for a specific company
   - GET `/check-ad/{ad_id}`: Get details of a specific ad
   - GET `/list-ads/{company_id}`: List all ads with basic details for a company

## 🔧 Configuration

### Performance Settings
- `MAX_CONCURRENT_PAGES`: Maximum parallel pages (default: 4)
- `CHUNK_SIZE`: Batch size for processing (default: 4)
- `RETRY_COUNT`: Number of retry attempts (default: 3)
- `PAGE_TIMEOUT`: Page load timeout in ms (default: 30000)

### Resource Requirements
- Memory: Minimum 2GB recommended
- CPU: 2 cores recommended
- Storage: ~500MB for application, database size varies with data

## 🐳 Docker Deployment

```bash
# Build container
docker build -t linkedin-crawler .

# Run container
docker run -p 8080:8080 \
  --env-file .env \
  linkedin-crawler
```

## ⚠️ Disclaimer

This tool is for research purposes only. Ensure compliance with LinkedIn's terms of service and rate limiting policies when using this crawler.

## 📄 Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## 📄 License

This tool is for research purposes only. Ensure compliance with LinkedIn's terms of service and rate limiting policies when using this crawler.

## 📄 MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## 🆘 Support

- Create an issue for bug reports or feature requests
- Check existing issues before creating new ones
- Include relevant details and error logs in bug reports




Here's a checklist for deploying to Cloud Run, broken down into prerequisites and # LinkedIn Ad Crawler

## Prerequisites

### Local Development

1. **Test Application Locally**
   ```bash
   uvicorn main:app --reload
   ```

2. **Test Database Connections**
   ```bash
   python -c "from src.utils import init_db; import asyncio; asyncio.run(init_db())"
   ```

### Docker Testing

1. **Build Locally**
   ```bash
   docker build -t linkedin-ad-crawler .
   ```

2. **Run Locally**
   ```bash
   docker run -p 8080:8080 --env-file .env linkedin-ad-crawler
   ```

### Required Files

- `Dockerfile` 
- `cloudbuild.yaml` 
- `requirements.txt` 
- `.env.yaml` 

## Deployment Steps

### Setup Google Cloud CLI

1. **Install and Initialize gcloud**
   ```bash
   gcloud init
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   ```

2. **Enable Required APIs**
   ```bash
   gcloud services enable \
     cloudbuild.googleapis.com \
     run.googleapis.com \
     secretmanager.googleapis.com \
     cloudresourcemanager.googleapis.com
   ```

3. **Set Up Secrets**
   ```bash
   gcloud secrets create POSTGRES_USER --data-file=- <<< "your-username"
   gcloud secrets create POSTGRES_PASSWORD --data-file=- <<< "your-password"
   gcloud secrets create POSTGRES_HOST --data-file=- <<< "your-host"
   gcloud secrets create POSTGRES_DB --data-file=- <<< "your-db-name"
   ```

### Deploy

1. **Using Cloud Build**
   ```bash
   gcloud builds submit --config cloudbuild.yaml
   ```

2. **Or Direct to Cloud Run**
   ```bash
   gcloud run deploy linkedin-ad-crawler \
     --image gcr.io/$PROJECT_ID/linkedin-ad-crawler \
     --platform managed \
     --region europe-west1 \
     --allow-unauthenticated
   ```

## Common Issues to Check

### Database Connectivity

- Ensure your database allows connections from Cloud Run IP range.
- Add this to your PostgreSQL config:
  ```
  host    all             all             0.0.0.0/0               md5
  ```

### Environment Variables

- `.env.yaml` should look like:
  ```yaml
  POSTGRES_USER: "user"
  POSTGRES_PASSWORD: "pass"
  POSTGRES_HOST: "host"
  POSTGRES_PORT: "5432"
  POSTGRES_DB: "dbname"
  ```

### IAM Permissions

- Grant necessary permissions:
  ```bash
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
  ```

### Network Configuration

- If using Cloud SQL, create a connection:
  ```bash
  gcloud sql connections create vpc-connection \
    --network=default \
    --region=europe-west1
  ```

## Fix TypeError in `config.py`

- Update the type hint to be compatible with Python 3.9:
  ```python
  from typing import Optional

  class Settings(BaseSettings):
      CLOUD_SQL_INSTANCE: Optional[str] = None
  ```

This updated `README.md` provides a clear guide for setting up and deploying your application, along with addressing the TypeError issue.