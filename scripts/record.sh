#!/bin/bash
# Record teleoperation episodes with 3 cameras (local only, no HF Hub push)
# Usage: ./record.sh <follower_port> <leader_port> [dataset_name] [--resume]

source ~/miniforge3/etc/profile.d/conda.sh
conda activate lerobot

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: $0 <follower_port> <leader_port> [dataset_name]"
    exit 1
fi

DATASET_NAME="${3:-mfzeidan/sock_sorting}"

# Check for --resume flag
RESUME_FLAG=""
for arg in "$@"; do
    if [ "$arg" = "--resume" ]; then
        RESUME_FLAG="--resume=true"
    fi
done

# Load camera indices from .env if available
if [ -f "$(dirname "$0")/../backend/.env" ]; then
    source "$(dirname "$0")/../backend/.env"
fi
CAM_RIGHT="${CAMERA_RIGHT_INDEX:-0}"
CAM_WRIST="${CAMERA_WRIST_INDEX:-1}"
CAM_ACROSS="${CAMERA_ACROSS_INDEX:-2}"

CAMERAS="{right: {type: opencv, index_or_path: $CAM_RIGHT, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: $CAM_WRIST, width: 640, height: 480, fps: 30}, across: {type: opencv, index_or_path: $CAM_ACROSS, width: 640, height: 480, fps: 30}}"

lerobot-record \
    --robot.type=so101_follower --robot.port="$1" \
    --robot.cameras="$CAMERAS" \
    --teleop.type=so101_leader --teleop.port="$2" \
    --dataset.repo_id="$DATASET_NAME" \
    --dataset.single_task="Pick and place sock" \
    --dataset.push_to_hub=false \
    --dataset.episode_time_s=30 \
    --dataset.reset_time_s=10 \
    --display_data=true \
    $RESUME_FLAG
