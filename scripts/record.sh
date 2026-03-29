#!/bin/bash
# Record teleoperation episodes with 3 cameras (local only, no HF Hub push)
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
CAM_RIGHT="${CAMERA_RIGHT_INDEX:-0}"
CAM_WRIST="${CAMERA_WRIST_INDEX:-1}"
CAM_ACROSS="${CAMERA_ACROSS_INDEX:-2}"

lerobot-record \
    --robot.type=so101_follower --robot.port="$1" \
    --robot.cameras.right.type=opencv --robot.cameras.right.index_or_path="$CAM_RIGHT" \
    --robot.cameras.right.width=640 --robot.cameras.right.height=480 --robot.cameras.right.fps=30 \
    --robot.cameras.wrist.type=opencv --robot.cameras.wrist.index_or_path="$CAM_WRIST" \
    --robot.cameras.wrist.width=640 --robot.cameras.wrist.height=480 --robot.cameras.wrist.fps=30 \
    --robot.cameras.across.type=opencv --robot.cameras.across.index_or_path="$CAM_ACROSS" \
    --robot.cameras.across.width=640 --robot.cameras.across.height=480 --robot.cameras.across.fps=30 \
    --teleop.type=so101_leader --teleop.port="$2" \
    --dataset.repo_id="$DATASET_NAME" \
    --dataset.push_to_hub=false
