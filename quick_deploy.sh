#!/bin/bash
# Quick Deploy Script
# Loads credentials from .env and deploys to Cloud Run.
# DO NOT hardcode API keys here — use .env or Secret Manager.

if [ -f .env ]; then
    source .env
fi

if [ -z "$OANDA_API_KEY" ] && [ -z "$OANDA_API_KEY_LIVE" ]; then
    echo "❌ OANDA_API_KEY or OANDA_API_KEY_LIVE must be set in .env"
    exit 1
fi

./deploy_gcloud.sh
