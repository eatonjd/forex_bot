#!/bin/bash
for pkg in forex-bot-live forex-bot-vol forex-trading-bot; do
    echo "Cleaning up $pkg..."
    digests=$(/Users/eatonjd/google-cloud-sdk/bin/gcloud artifacts docker images list "us-central1-docker.pkg.dev/big-e-trading-bot/cloud-run-source-deploy/$pkg" --sort-by=~CREATE_TIME --format="value(digest)")
    to_delete=$(echo "$digests" | tail -n +5)
    for digest in $to_delete; do
        if [ -n "$digest" ]; then
            echo "Deleting $digest"
            /Users/eatonjd/google-cloud-sdk/bin/gcloud artifacts docker images delete "us-central1-docker.pkg.dev/big-e-trading-bot/cloud-run-source-deploy/$pkg@$digest" --delete-tags --quiet
        fi
    done
done
