#!/bin/bash
#
# Deploy Forex Bot to Google Cloud Run
#
# Usage: ./deploy_gcloud.sh
#

set -e

echo "============================================================"
echo "DEPLOYING FOREX BOT TO GOOGLE CLOUD RUN"
echo "============================================================"
echo ""

# Load environment variables from .env if it exists
if [ -f .env ]; then
    echo "📄 Loading environment variables from .env..."
    # Export vars from .env, excluding comments
    export $(grep -v '^#' .env | xargs)
fi

# Check for required OANDA credentials
if [ -z "$OANDA_API_KEY" ]; then
    echo "⚠️  OANDA_API_KEY is not set in environment or .env"
    read -p "Enter OANDA_API_KEY: " OANDA_API_KEY
    export OANDA_API_KEY
fi

if [ -z "$OANDA_ACCOUNT_ID" ]; then
    echo "⚠️  OANDA_ACCOUNT_ID is not set in environment or .env"
    read -p "Enter OANDA_ACCOUNT_ID: " OANDA_ACCOUNT_ID
    export OANDA_ACCOUNT_ID
fi

echo "✅ Credentials loaded: OANDA_ACCOUNT_ID=$OANDA_ACCOUNT_ID"
echo ""

# Configuration
PROJECT_ID="big-e-trading-bot"
REGION="us-central1"
SERVICE_NAME="forex-trading-bot"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI not found. Please install: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Get current project
CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null)
echo "📋 Current GCP Project: ${CURRENT_PROJECT}"
echo ""

# Ask to confirm or change project
read -p "Use this project? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    read -p "Enter GCP Project ID: " PROJECT_ID
    gcloud config set project ${PROJECT_ID}
fi

echo ""
echo "🔨 Building Docker image..."
gcloud builds submit --tag ${IMAGE_NAME}

echo ""
echo "🚀 Deploying to Cloud Run..."
gcloud run deploy ${SERVICE_NAME} \
    --image ${IMAGE_NAME} \
    --platform managed \
    --region ${REGION} \
    --allow-unauthenticated \
    --memory 1Gi \
    --cpu 1 \
    --timeout 3600 \
    --set-env-vars "OANDA_API_KEY=${OANDA_API_KEY}" \
    --set-env-vars "OANDA_ACCOUNT_ID=${OANDA_ACCOUNT_ID}" \
    --set-env-vars "OANDA_ENVIRONMENT=practice" \
    --set-env-vars "USE_CLOUD_STORAGE=true" \
    --set-env-vars "GCS_BUCKET_NAME=forex-bot-state"

echo ""
echo "============================================================"
echo "✅ DEPLOYMENT COMPLETE!"
echo "============================================================"
echo ""

# Get service URL
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region ${REGION} --format 'value(status.url)')
echo "🌐 Service URL: ${SERVICE_URL}"
echo ""

echo "📊 To view logs:"
echo "   gcloud run services logs tail ${SERVICE_NAME} --region ${REGION}"
echo ""

echo "🛑 To stop the bot:"
echo "   gcloud run services delete ${SERVICE_NAME} --region ${REGION}"
echo ""

echo "============================================================"
