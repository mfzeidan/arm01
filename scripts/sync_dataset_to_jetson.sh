#!/bin/bash
# Sync recorded dataset from Mac to Jetson for training
# Usage: ./sync_dataset_to_jetson.sh [dataset_name]

if [ -f "$(dirname "$0")/../backend/.env" ]; then
    source "$(dirname "$0")/../backend/.env"
fi

DATASET_NAME="${1:-sock_sorting}"
JETSON="${JETSON_USER:-mark}@${JETSON_HOST:?Set JETSON_HOST in backend/.env}"
LOCAL_DATA="$HOME/.cache/huggingface/lerobot/$DATASET_NAME"

if [ ! -d "$LOCAL_DATA" ]; then
    echo "Dataset not found at $LOCAL_DATA"
    echo "Available datasets:"
    ls "$HOME/.cache/huggingface/lerobot/" 2>/dev/null
    exit 1
fi

echo "Syncing $DATASET_NAME to $JETSON..."
rsync -avz --progress "$LOCAL_DATA" "$JETSON:~/.cache/huggingface/lerobot/"
echo "Done. SSH to Jetson and run training."
