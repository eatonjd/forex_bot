#!/bin/bash
for pkg in forex-bot-live forex-bot-vol forex-trading-bot options-regime-bot; do
    echo "Cleaning up $pkg..."
    digests=$(gcloud artifacts docker images list "us-central1-docker.pkg.dev/big-e-trading-bot/cloud-run-source-deploy/$pkg" --sort-by=~CREATE_TIME --format="value(digest)" 2>/dev/null)
    to_delete=$(echo "$digests" | tail -n +5)
    count=0
    for digest in $to_delete; do
        if [ -n "$digest" ]; then
            echo "Deleting old image digest: $digest"
            gcloud artifacts docker images delete "us-central1-docker.pkg.dev/big-e-trading-bot/cloud-run-source-deploy/$pkg@$digest" --delete-tags --quiet 2>/dev/null
            count=$((count+1))
        fi
    done
    echo "Done cleaning $pkg ($count old image(s) purged)."
done
