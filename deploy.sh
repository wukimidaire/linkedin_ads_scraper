#!/bin/bash

# Clean up old containers and images
docker system prune -f

# Build the Docker image
echo "🏗️ Building Docker image..."
docker build -t linkedin-ad-crawler .

# Tag the image for GCR
echo "🏷️ Tagging image for GCR..."
docker tag linkedin-ad-crawler gcr.io/personal-projects-426408/linkedin-ad-crawler

# Push to Google Container Registry
echo "⬆️ Pushing to Google Container Registry..."
docker push gcr.io/personal-projects-426408/linkedin-ad-crawler

# Deploy to Cloud Run with increased timeout and memory
echo "🚀 Deploying to Cloud Run..."
gcloud run deploy linkedin-ad-crawler \
  --image gcr.io/personal-projects-426408/linkedin-ad-crawler \
  --platform managed \
  --region europe-west1 \
  --project personal-projects-426408 \
  --memory 2Gi \
  --timeout 300 \
  --cpu 1 \
  --port 8080 \
  --set-env-vars="PYTHONUNBUFFERED=1" \
  --allow-unauthenticated