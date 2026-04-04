# Training PC Setup Agent Prompt

Copy-paste the below into a Claude Code terminal session on your Mac Air. You'll run commands on the new PC over SSH, and Claude will guide you through each step.

---

I just built a new ML training PC from Micro Center and need help setting it up from scratch. I'm SSH'd into it from my MacBook Air. Walk me through every step — I'll paste command outputs back to you so you can diagnose issues.

## The hardware

- **GPU:** PNY RTX Pro 4500 Blackwell — 32GB GDDR7, PCIe 5.0
- **CPU:** AMD Ryzen 9 9950X — 16-core, AM5
- **Motherboard:** AM5 ATX (B850 or X670E — I'll confirm which I got)
- **RAM:** 32GB DDR5 6000MHz (2x16GB)
- **Storage:** 2TB NVMe M.2 SSD
- **PSU:** 1000W 80+ Gold, fully modular

## What I need installed (in order)

### Phase 1: OS + drivers
1. Ubuntu 24.04 LTS (already flashed to USB, need to boot and install)
2. NVIDIA proprietary drivers (latest stable for RTX Pro 4500 Blackwell)
3. Verify GPU is detected: `nvidia-smi` should show 32GB VRAM
4. SSH server so I can work headless from my Mac Air
5. Tailscale for remote access (I already have a Tailscale account — same network as my Jetson at `100.98.191.120`)

### Phase 2: ML stack
6. Miniforge (conda) — same as my Jetson setup
7. Create `lerobot` conda environment with Python 3.12
8. PyTorch with CUDA support (latest stable, must detect the RTX Pro 4500)
9. LeRobot v0.5.x from source (editable install)
10. Feetech servo SDK (`pip install feetech-servo-sdk`)
11. OpenCV with CUDA support if possible (fallback: regular opencv-python)

### Phase 3: Project setup
12. Clone my repo: `git clone https://github.com/mfzeidan/arm01.git`
13. Set up Anthropic API key (I'll provide it — for the Claude Vision coordinator)
14. Transfer any training datasets from Jetson if needed

### Phase 4: Validation
15. Run a quick PyTorch CUDA test — confirm GPU training works
16. Run a small ACT training job to verify the full pipeline
17. Benchmark VRAM usage so I know my headroom for larger models

## My existing network

| Device | Access | Role |
|--------|--------|------|
| MacBook Air M4 | Local (this machine) | Development, SSH client |
| Mac Mini M4 | Local network (SSH) | Data collection with robot arm |
| Jetson Orin Nano | `ssh m@100.98.191.120` (Tailscale) / `192.168.1.208` (LAN) | Current training (being replaced) |
| **New training PC** | TBD — need to set up SSH + Tailscale | ML training |

## Known gotchas from my Jetson experience

- NVIDIA drivers can be tricky — `ubuntu-drivers install` is usually safest on Ubuntu
- PyTorch must match CUDA version exactly — don't let pip install CPU-only torch
- numpy 2.x can break torch — may need to pin `numpy<2` like on the Jetson
- LeRobot v0.5.x requires Python 3.12 (uses `type` statement syntax)
- Feetech SDK import is `scservo_sdk`, not `feetech_servo_sdk`
- Don't install ffmpeg 8.x — LeRobot may need ffmpeg 7.x pinned

## How to help me

1. Give me commands one step at a time — don't dump a wall of commands
2. After each command, I'll paste the output so you can verify it worked
3. If something fails, help me diagnose before moving on
4. Keep a running checklist of what's done vs. what's left
5. Flag anything that differs from my Jetson setup (Python 3.12 vs 3.10, different torch version, etc.)
6. At the end, give me a summary of the final state (like my `docs/jetson-setup.md`)

## My background

I know Python, PyTorch, and basic Linux terminal. I've set up the Jetson Orin Nano (see `docs/jetson-setup.md` in my repo for reference). I'm not a sysadmin — explain anything non-obvious about drivers, kernel modules, or networking.

## First step

The PC is powered on with the Ubuntu USB plugged in. Tell me how to:
1. Enter BIOS and set USB as boot device
2. Install Ubuntu on the 2TB NVMe
3. Get SSH running so I can do the rest from my Mac Air
