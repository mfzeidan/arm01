#!/bin/bash
# Discover USB ports for leader and follower arms
source ~/miniforge3/etc/profile.d/conda.sh
conda activate lerobot
lerobot-find-port
