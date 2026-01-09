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
    source .env
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

# Enable Secret Manager API (needed for SMTP password)
echo "🔧 Enabling Secret Manager API..."
gcloud services enable secretmanager.googleapis.com --quiet

# ============================================================
# SMS Configuration
# ============================================================
echo ""
echo "📱 SMS Notification Setup"
echo "-------------------------"

# Check if smtp-password secret exists
if ! gcloud secrets describe smtp-password &> /dev/null 2>&1; then
    echo "No SMS secret found."
    read -p "Setup SMS notifications? (y/n, default n): " -n 1 -r setup_sms
    echo
    if [[ $setup_sms =~ ^[Yy]$ ]]; then
        echo -n "Enter 10-digit phone number: "
        read SMS_PHONE_NUMBER
        echo -n "Enter SMTP email (Gmail): "
        read SMTP_USER
        echo -n "Enter SMTP App Password: "
        read -s SMTP_PASSWORD
        echo
        
        # Store password in Secret Manager
        echo -n "$SMTP_PASSWORD" | gcloud secrets create smtp-password --data-file=-
        
        # Save phone/email to .env
        if [ -f .env ]; then
            # Remove existing entries
            sed -i.bak '/^SMS_PHONE_NUMBER=/d' .env
            sed -i.bak '/^SMTP_USER=/d' .env
            rm -f .env.bak
        fi
        echo "SMS_PHONE_NUMBER=$SMS_PHONE_NUMBER" >> .env
        echo "SMTP_USER=$SMTP_USER" >> .env
        
        echo "✅ SMS configured"
    else
        echo "⏭️  Skipping SMS setup"
    fi
else
    echo "✅ SMS secret exists (smtp-password)"
    # Offer to update
    read -p "Update SMS settings? (y/n, default n): " -n 1 -r update_sms
    echo
    if [[ $update_sms =~ ^[Yy]$ ]]; then
        echo -n "Enter 10-digit phone number: "
        read SMS_PHONE_NUMBER
        echo -n "Enter SMTP email (Gmail): "
        read SMTP_USER
        echo -n "Enter new SMTP App Password: "
        read -s SMTP_PASSWORD
        echo
        
        # Update secret
        echo -n "$SMTP_PASSWORD" | gcloud secrets versions add smtp-password --data-file=-
        
        # Update .env
        if [ -f .env ]; then
            sed -i.bak '/^SMS_PHONE_NUMBER=/d' .env
            sed -i.bak '/^SMTP_USER=/d' .env
            rm -f .env.bak
        fi
        echo "SMS_PHONE_NUMBER=$SMS_PHONE_NUMBER" >> .env
        echo "SMTP_USER=$SMTP_USER" >> .env
        
        echo "✅ SMS updated"
    fi
fi

echo ""
echo "🔨 Building Docker image..."
gcloud builds submit --tag ${IMAGE_NAME}

# Get project number for service account
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

# Grant secret access if smtp-password exists
if gcloud secrets describe smtp-password &> /dev/null 2>&1; then
    echo "🔐 Granting secret access to service account..."
    gcloud secrets add-iam-policy-binding smtp-password \
        --member="serviceAccount:${SERVICE_ACCOUNT}" \
        --role="roles/secretmanager.secretAccessor" \
        --quiet
fi

echo ""
echo "🚀 Deploying to Cloud Run..."

# Build secrets flag if smtp-password exists
SECRETS_FLAG=""
if gcloud secrets describe smtp-password &> /dev/null 2>&1; then
    SECRETS_FLAG="--set-secrets=SMTP_PASSWORD=smtp-password:latest"
fi

gcloud run deploy ${SERVICE_NAME} \
    --image ${IMAGE_NAME} \
    --platform managed \
    --region ${REGION} \
    --allow-unauthenticated \
    --memory 1Gi \
    --cpu 1 \
    --min-instances 1 \
    --max-instances 1 \
    --concurrency 1 \
    --timeout 3600 \
    --no-cpu-throttling \
    --set-env-vars "OANDA_API_KEY=${OANDA_API_KEY}" \
    --set-env-vars "OANDA_ACCOUNT_ID=${OANDA_ACCOUNT_ID}" \
    --set-env-vars "OANDA_ENVIRONMENT=practice" \
    --set-env-vars "OANDA_API_KEY_LIVE=${OANDA_API_KEY_LIVE:-}" \
    --set-env-vars "OANDA_ACCOUNT_ID_LIVE=${OANDA_ACCOUNT_ID_LIVE:-}" \
    --set-env-vars "USE_CLOUD_STORAGE=true" \
    --set-env-vars "GCS_BUCKET_NAME=forex-bot-state" \
    --set-env-vars "SMS_PHONE_NUMBER=${SMS_PHONE_NUMBER:-}" \
    --set-env-vars "SMTP_USER=${SMTP_USER:-}" \
    --set-env-vars "TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:-}" \
    --set-env-vars "TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID:-}" \
    --set-env-vars "GOOGLE_API_KEY=${GOOGLE_API_KEY:-}" \
    $SECRETS_FLAG

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
