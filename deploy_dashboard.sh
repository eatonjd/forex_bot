#!/bin/bash

# Deploy Streamlit Dashboard to Cloud Run
# This creates a separate service for the dashboard that reads from Cloud Storage

set -e

PROJECT_ID=$(gcloud config get-value project)
REGION="us-central1"
SERVICE_NAME="forex-dashboard"
BUCKET_NAME="forex-bot-state"

echo "============================================================"
echo "Deploying Forex Dashboard to Cloud Run"
echo "============================================================"
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Service: $SERVICE_NAME"
echo "Bucket: $BUCKET_NAME"
echo ""

# Build and deploy using Dockerfile.dashboard
echo "Building and deploying dashboard..."
gcloud run deploy $SERVICE_NAME \
  --source . \
  --dockerfile Dockerfile.dashboard \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --timeout 300 \
  --set-env-vars USE_CLOUD_STORAGE=true,GCS_BUCKET_NAME=$BUCKET_NAME \
  --project $PROJECT_ID

echo ""
echo "============================================================"
echo "✅ Dashboard deployed successfully!"
echo "============================================================"
echo ""
echo "Dashboard URL:"
gcloud run services describe $SERVICE_NAME \
  --region $REGION \
  --format 'value(status.url)' \
  --project $PROJECT_ID

echo ""
echo "To view logs:"
echo "gcloud run logs read $SERVICE_NAME --region $REGION --project $PROJECT_ID"
echo ""
