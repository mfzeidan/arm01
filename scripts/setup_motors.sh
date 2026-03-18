#!/bin/bash
# Setup motor IDs and baudrates for follower and leader arms
# Usage: ./setup_motors.sh <follower_port> <leader_port>
# Example: ./setup_motors.sh /dev/tty.usbmodem575E0032081 /dev/tty.usbmodem575E0031751

source ~/miniforge3/etc/profile.d/conda.sh
conda activate lerobot

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: $0 <follower_port> <leader_port>"
    echo "Run ./find_ports.sh first to discover ports"
    exit 1
fi

echo "=== Setting up FOLLOWER arm on $1 ==="
lerobot-setup-motors --robot.type=so101_follower --robot.port="$1"

echo ""
echo "=== Setting up LEADER arm on $2 ==="
lerobot-setup-motors --teleop.type=so101_leader --teleop.port="$2"
