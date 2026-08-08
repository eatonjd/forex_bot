#!/usr/bin/env bash
# ==============================================================================
# GCP Resource Cleanup Script for Forex & Options Bots
# Performs daily cleanup of inactive Cloud Run revisions & old Artifact Registry images.
# Schedule: Daily at 3:00 AM EST (08:00 UTC)
# ==============================================================================

set -euo pipefail

PROJECT_ID="big-e-trading-bot"
REGION="us-central1"
RETENTION_DAYS=7

echo "🧹 Starting GCP Resource Cleanup for project: ${PROJECT_ID}..."
echo "📅 Policy: Delete inactive revisions & untagged images older than ${RETENTION_DAYS} days"

# ------------------------------------------------------------------------------
# 1. Clean up inactive Cloud Run revisions
# ------------------------------------------------------------------------------
echo "🔍 Searching for inactive Cloud Run revisions..."
SERVICES=("forex-bot-live" "forex-trading-bot" "options-regime-bot")

for SERVICE in "${SERVICES[@]}"; do
    echo "  Checking service: ${SERVICE}..."
    ACTIVE_REV=$(gcloud run services describe "${SERVICE}" --region="${REGION}" --format="value(status.latestReadyRevisionName)" 2>/dev/null || echo "")
    
    if [ -n "${ACTIVE_REV}" ]; then
        echo "  Active revision for ${SERVICE}: ${ACTIVE_REV}"
    fi

    INACTIVE_REVS=$(gcloud run revisions list --service="${SERVICE}" --region="${REGION}" --format="value(name)" 2>/dev/null | grep -v "${ACTIVE_REV}" || true)

    for REV in ${INACTIVE_REVS}; do
        if [ -n "${REV}" ]; then
            echo "  🗑️ Deleting inactive revision: ${REV}"
            gcloud run revisions delete "${REV}" --region="${REGION}" --quiet || true
        fi
    done
done

# ------------------------------------------------------------------------------
# 2. Clean up old untagged Artifact Registry images
# ------------------------------------------------------------------------------
echo "🔍 Searching for old untagged container images in Artifact Registry..."
REPO="cloud-run-source-deploy"

# Read package and version for untagged images older than RETENTION_DAYS
gcloud artifacts docker images list "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}" \
    --filter="CREATE_TIME < -P${RETENTION_DAYS}D AND NOT tags:*" \
    --format="value(package,version)" 2>/dev/null | while read -r PKG VER; do
    if [ -n "${PKG}" ] && [ -n "${VER}" ]; then
        FULL_IMAGE="${PKG}@${VER}"
        echo "  🗑️ Deleting old untagged image: ${FULL_IMAGE}"
        gcloud artifacts docker images delete "${FULL_IMAGE}" --delete-tags --quiet || true
    fi
done

echo "✨ GCP Resource Cleanup finished successfully!"
