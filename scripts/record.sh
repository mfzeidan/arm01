#!/bin/bash
# Record teleoperation episodes with 2 cameras (local only, no HF Hub push)
# Usage: ./record.sh <follower_port> <leader_port> [dataset_name]

source ~/miniforge3/etc/profile.d/conda.sh
conda activate lerobot

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: $0 <follower_port> <leader_port> [dataset_name]"
    exit 1
fi

DATASET_NAME="${3:-sock_sorting}"

# Load camera indices from .env if available
if [ -f "$(dirname "$0")/../backend/.env" ]; then
    source "$(dirname "$0")/../backend/.env"
fi
CAM_TOP="${CAMERA_TOP_INDEX:-0}"
CAM_FRONT="${CAMERA_FRONT_INDEX:-1}"

lerobot-record \
    --robot.type=so101_follower --robot.port="$1" \
    --robot.cameras.top.type=opencv --robot.cameras.top.index_or_path="$CAM_TOP" \
    --robot.cameras.top.width=640 --robot.cameras.top.height=480 --robot.cameras.top.fps=30 \
    --robot.cameras.front.type=opencv --robot.cameras.front.index_or_path="$CAM_FRONT" \
    --robot.cameras.front.width=640 --robot.cameras.front.height=480 --robot.cameras.front.fps=30 \
    --teleop.type=so101_leader --teleop.port="$2" \
    --dataset.repo_id="$DATASET_NAME" \
    --dataset.push_to_hub=false
