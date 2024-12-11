FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    xvfb \
    libgbm1 \
    libnss3 \
    libxss1 \
    libasound2 \
    libxtst6 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install playwright browsers and dependencies
RUN playwright install chromium --with-deps

# Set up virtual display
ENV DISPLAY=:99
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

# Copy application code
COPY . .

# Set environment variables
ENV PORT=8080

# Modify the CMD to use xvfb-run
CMD ["sh", "-c", "xvfb-run --server-args='-screen 0 1280x800x24' uvicorn app:app --host 0.0.0.0 --port $PORT"]