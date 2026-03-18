#!/bin/bash
# Discover available cameras and show preview
source ~/miniforge3/etc/profile.d/conda.sh
conda activate lerobot
lerobot-find-cameras
