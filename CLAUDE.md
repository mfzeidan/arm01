# arm01 — SO-101 Sock Sorting Robot

## Project Overview

Autonomous sock sorting using an SO-101 robot arm guided by Claude Vision API. Claude identifies matching sock pairs from camera images, reads grid coordinates from a physical workspace mat, and commands the arm to pick-and-place socks into paired piles.

## Current Status

- [x] LeRobot 0.5.1 installed (editable, from source at `./lerobot/`)
- [x] Conda env `lerobot` (Python 3.12, PyTorch 2.10.0, MPS available)
- [x] Feetech servo SDK installed
- [x] TPU compliant gripper STLs identified (SO-ARM100 repo)
- [ ] Arm hardware arrives 2026-03-20 (Friday)
- [ ] Motor setup + calibration
- [ ] Camera mounting + discovery
- [ ] Grid mat workspace setup
- [ ] Pick-and-place training data collection
- [ ] ACT policy training on Jetson
- [ ] Claude Vision coordinator script
- [ ] End-to-end sock sorting test

## Architecture

```
┌─────────────────────────────────────┐
│         CLAUDE VISION API           │
│  - Identifies sock pairs by color/  │
│    pattern from camera images       │
│  - Reads grid coordinates from mat  │
│  - Plans pick order + placement     │
└──────────┬──────────────────────────┘
           │ camera images up / instructions down
           │
┌──────────▼──────────────────────────┐
│   COORDINATOR (Python on Jetson)    │
│  - Captures camera frames           │
│  - Sends images to Claude API       │
│  - Translates grid coords to arm    │
│    joint positions via lookup table  │
│  - Invokes LeRobot motor control    │
└──────────┬──────────────────────────┘
           │ Feetech serial bus
           │
┌──────────▼──────────────────────────┐
│         SO-101 FOLLOWER ARM         │
│  - 6x Feetech STS3215 servos       │
│  - TPU compliant gripper (Fin Ray)  │
│  - ~25-30cm reach                   │
└─────────────────────────────────────┘
```

## Hardware

| Component | Details |
|-----------|---------|
| Robot Arm | SO-101 (follower + leader), Feetech STS3215 servos, arriving 2026-03-20 |
| Gripper | Stock rigid (default) + TPU compliant (Fin Ray, print from SO-ARM100 repo) |
| Cameras | 2x USB cameras (top-down + front/side angle) |
| Compute (training) | NVIDIA Jetson Orin Nano Super Developer Kit |
| Compute (data collection) | Mac Mini M4 16GB |
| Compute (development) | MacBook Air M4 16GB |
| 3D Printer | Bambu Lab P1S (PLA + TPU 95A for compliant gripper) |
| Workspace | Dry-erase battle grid mat (~24x36") with hand-labeled chess-style coordinates |

## Coordinate System

Physical grid mat on the workspace with chess-style labels (A-J across top, 1-12 down side). Claude reads coordinates from camera images. One-time calibration maps grid positions to arm joint angles stored as a lookup table with interpolation for in-between points.

## Directory Structure

```
arm01/
├── CLAUDE.md              # This file — project memory
├── README.md              # Human-readable overview
├── lerobot/               # LeRobot (editable install from source)
├── backend/               # Coordinator server (Python, runs on Jetson)
│   ├── app.py             # Main coordinator: camera → Claude API → arm commands
│   ├── calibration.py     # Grid-to-joint-angle calibration + lookup
│   ├── requirements.txt
│   └── .env.example
├── enclosure/             # 3D printed parts (OpenSCAD source + STL exports)
├── scripts/               # Operational shell scripts
├── docs/                  # Status docs, troubleshooting, lessons learned
└── .claude/               # Claude Code settings
```

## Software Stack

| Layer | Tech |
|-------|------|
| Motor control | LeRobot 0.5.1 + Feetech SDK |
| Policy training | ACT (Action Chunking Transformers) on Jetson (CUDA) |
| Vision/reasoning | Claude Vision API (Anthropic) |
| Coordinator | Python (FastAPI or Flask) on Jetson |
| Camera capture | OpenCV (`cv2.VideoCapture`) |
| 3D design | OpenSCAD (parametric), Bambu Studio (slicer) |

## Key Commands

```bash
# Activate environment
conda activate lerobot

# Find USB ports for arms
lerobot-find-port

# Setup motors (one at a time, follower then leader)
lerobot-setup-motors --robot.type=so101_follower --robot.port=/dev/tty.PORT
lerobot-setup-motors --teleop.type=so101_leader --teleop.port=/dev/tty.PORT

# Calibrate arms
lerobot-calibrate --robot.type=so101_follower --robot.port=/dev/tty.PORT
lerobot-calibrate --teleop.type=so101_leader --teleop.port=/dev/tty.PORT

# Find cameras
lerobot-find-cameras

# Teleoperate (test)
lerobot-teleoperate \
  --robot.type=so101_follower --robot.port=/dev/tty.FOLLOWER \
  --teleop.type=so101_leader --teleop.port=/dev/tty.LEADER

# Record episodes (with 2 cameras, local only)
lerobot-record \
  --robot.type=so101_follower --robot.port=/dev/tty.FOLLOWER \
  --robot.cameras.top.type=opencv --robot.cameras.top.index_or_path=0 \
  --robot.cameras.top.width=640 --robot.cameras.top.height=480 --robot.cameras.top.fps=30 \
  --robot.cameras.front.type=opencv --robot.cameras.front.index_or_path=1 \
  --robot.cameras.front.width=640 --robot.cameras.front.height=480 --robot.cameras.front.fps=30 \
  --teleop.type=so101_leader --teleop.port=/dev/tty.LEADER \
  --dataset.repo_id=sock_sorting --dataset.push_to_hub=false

# Train ACT policy (on Jetson)
lerobot-train \
  --dataset.repo_id=sock_sorting \
  --dataset.root=/path/to/data \
  --policy.type=act \
  --policy.push_to_hub=false

# Eval (autonomous)
lerobot-eval \
  --robot.type=so101_follower --robot.port=/dev/tty.FOLLOWER \
  --policy.path=outputs/train/model
```

## Network / Access

| Device | Access |
|--------|--------|
| Mac Air (dev) | Local — current machine |
| Mac Mini | SSH from Mac Air (TODO: document IP/hostname) |
| Jetson Orin Nano | SSH from Mac Air (TODO: document IP/hostname) |

## Gripper Options

1. **Stock rigid gripper** — default, try first
2. **TPU grip pads** — snap-on friction pads ([Thingiverse](https://www.thingiverse.com/thing:7153144))
3. **TPU compliant gripper** — Fin Ray effect, drop-in replacement. STLs at `SO-ARM100/Optional/Compliant_Gripper/stl/`. Print in TPU 95A, 20% infill on Bambu P1S.
4. **Fin-Ray gripper** — community design ([MakerWorld](https://makerworld.com/en/models/2075813))
5. **PincOpen** — advanced, interchangeable fingertips ([pollen-robotics](https://pollen-robotics.github.io/PincOpen/))

## Camera Mounts

- Overhead mount STLs at `../so101-camera-mounts/overhead/`
- Wrist mount STL at `../so101-camera-mounts/wrist/`
- Snap-on gripper camera mount ([Thingiverse](https://www.thingiverse.com/thing:7033586))

## Known Issues / Gotchas

- **Do NOT train on Mac MPS** — known gradient explosion / NaN loss with ACT on Apple Silicon ([GitHub #1066](https://github.com/huggingface/lerobot/issues/1066)). Train on Jetson (CUDA) only.
- **ffmpeg 8.x not yet supported** by LeRobot — conda installs 8.x by default, may need to pin to 7.x if issues arise.
- **Sock grasping is hard** — flat, floppy fabric. Start with stock gripper, escalate to TPU compliant if needed.
- **Camera positions must be fixed** — never move between recording and evaluation. Model learns pixel-to-position mapping.

## Milestones

1. **Day 1 (2026-03-20)**: Assemble arm, setup motors, calibrate, teleoperate
2. **Weekend**: Record pick-and-place demos, train basic ACT on Jetson
3. **Week 2**: Grid mat calibration, Claude Vision coordinator, 4-sock test (2 pairs)
4. **Week 3**: Scale to 30 socks, iterate on gripper design
