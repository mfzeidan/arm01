# Grid Mat Calibration Procedure

One-time calibration to map grid mat coordinates to arm joint angles.

## Overview

The grid mat has chess-style labels (letters across top, numbers down side). This procedure records the arm's joint angles at each grid intersection, creating a lookup table. During sock sorting, Claude says "pick from B3" and the coordinator looks up the joint angles for B3.

## What You Need

- SO-101 follower arm (calibrated, connected)
- Leader arm (for teleoperation)
- Grid mat laid flat in the workspace
- Grid labeled with coordinates (e.g., A1-J12)
- Top-down camera mounted and working

## Step 1: Define the Active Area

The SO-101 has ~25-30cm reach. Not the whole mat is reachable.

1. Teleoperate the arm to the farthest corners it can reach
2. Mark these on the mat with dry-erase marker
3. The rectangle inside those marks is your **active area**
4. Only label coordinates within the active area

Expect roughly a 20x20cm usable zone, maybe 10x10 grid squares at 2cm spacing.

## Step 2: Record Grid Points

For each labeled grid intersection:

1. Teleoperate the follower arm so the gripper is centered directly above the grid point
2. Lower the gripper to **sock-grasping height** (~1-2cm above the mat)
3. Record the joint angles at this position
4. Move to the next grid point

### How Many Points?

- **Every 2 grid squares** is fine — you'll interpolate between them
- For a 10x10 active area with 1" squares: ~25 calibration points (every other intersection)
- Takes about 15-20 minutes

## Step 3: Store the Lookup Table

Save as a JSON file at `backend/calibration_data.json`:

```json
{
  "metadata": {
    "date": "2026-03-20",
    "grid_spacing_inches": 1,
    "sample_spacing": 2,
    "notes": "Calibrated with stock rigid gripper"
  },
  "points": {
    "A1": [1024, 512, 768, 256, 512, 128],
    "A3": [1030, 520, 760, 260, 510, 130],
    "C1": [1050, 500, 780, 240, 520, 125],
    "C3": [1055, 510, 775, 245, 515, 127]
  }
}
```

Each value is an array of 6 joint angles: [base, shoulder, elbow, wrist_pitch, wrist_roll, gripper].

## Step 4: Interpolation

For coordinates between calibration points (e.g., B2 when you calibrated A1, A3, C1, C3), use bilinear interpolation. The coordinator script (`backend/calibration.py`) will handle this.

## Step 5: Verify

1. Pick 5 random grid coordinates NOT in the calibration set
2. Command the arm to move there via the lookup table + interpolation
3. Check if the gripper lands on the correct grid square
4. If accuracy is poor, add more calibration points in that region

## Recalibration

You need to recalibrate if:
- The grid mat is moved
- The arm base is moved
- You switch grippers (different gripper length changes the reach)

You do NOT need to recalibrate if:
- Cameras are moved (cameras are independent of the grid-to-joint mapping)
- Socks are added/removed from the workspace
- You restart the software

## Calibration Script

```bash
# TODO: backend/calibration.py will provide an interactive calibration mode
# that prompts for each grid point and records joint angles automatically
python backend/calibration.py --mode=calibrate --port=/dev/tty.FOLLOWER_PORT
```
