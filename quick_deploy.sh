#!/bin/bash
# Quick Deploy Script
# Sets environment variables and deploys to Cloud Run

export OANDA_API_KEY="029fd0b11f5079ccccb4ab14b5f5638b-32865d7468197e4231101be7bc6f3863"
export OANDA_ACCOUNT_ID="101-001-11289252-001"

echo "✅ Environment variables set"
echo "🚀 Starting deployment..."
echo ""

./deploy_gcloud.sh
