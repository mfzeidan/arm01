#!/bin/bash
# Calibrate follower and leader arms
# Usage: ./calibrate.sh <follower_port> <leader_port>

source ~/miniforge3/etc/profile.d/conda.sh
conda activate lerobot

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: $0 <follower_port> <leader_port>"
    exit 1
fi

echo "=== Calibrating FOLLOWER arm on $1 ==="
lerobot-calibrate --robot.type=so101_follower --robot.port="$1"

echo ""
echo "=== Calibrating LEADER arm on $2 ==="
lerobot-calibrate --teleop.type=so101_leader --teleop.port="$2"
