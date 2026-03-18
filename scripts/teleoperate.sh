#!/bin/bash
# Teleoperate: move leader arm, follower mirrors
# Usage: ./teleoperate.sh <follower_port> <leader_port>

source ~/miniforge3/etc/profile.d/conda.sh
conda activate lerobot

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: $0 <follower_port> <leader_port>"
    exit 1
fi

lerobot-teleoperate \
    --robot.type=so101_follower --robot.port="$1" \
    --teleop.type=so101_leader --teleop.port="$2"
