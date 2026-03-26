# Jetson Orin Nano Setup Log

**Date:** 2026-03-19
**Device:** Jetson Orin Nano Super Developer Kit
**JetPack:** 6 (L4T R36.4.7)
**SSH:** `ssh m@100.98.191.120` (Tailscale) / `ssh m@192.168.1.208` (local WiFi, DHCP)
**Boot:** 256GB SD card, freshly flashed
**sudo password:** `password`
**Status:** ✅ Fully configured and verified — ready for arm tomorrow

---

## System Specs

| Component | Value |
|-----------|-------|
| OS | L4T R36.4.7 (Ubuntu 22.04 based, glibc 2.35) |
| Architecture | aarch64 |
| RAM | 7.4 GiB total |
| Swap | 3.7 GiB |
| Disk | 233 GiB total, ~191 GiB free |
| CUDA toolkit | 12.6.11 (`/usr/local/cuda-12.6/`) |
| cuDNN | 9.3.0 (reported by torch) |
| NVIDIA driver | 540.4.0 (Tegra integrated) |
| System Python | 3.10.12 (`/usr/bin/python3`) |
| GPU | Orin (SM 8.7 / compute capability 8.7) |

---

## What's Installed (Final Working State)

### 1. System Packages (apt) ✅

All installed via `apt`:
- `git`, `curl`, `wget`
- `build-essential`
- `python3-pip`, `python3-venv`
- `cmake` (3.22.1)
- `pkg-config`
- `libusb-1.0-0-dev`
- `v4l-utils`
- `libopenblas-base`, `libopenmpi-dev`, `libomp-dev` (required by Jetson PyTorch)

### 2. Miniforge (conda for aarch64) ✅

- Installed at `~/miniforge3/`
- Conda version: 26.1.0
- `conda init` has been run — available in future interactive shells
- **Note:** Non-interactive SSH commands need `source ~/miniforge3/etc/profile.d/conda.sh` first

### 3. Conda Environment: `lerobot` ✅

- Location: `/home/m/miniforge3/envs/lerobot`
- **Python: 3.10.20** (required for NVIDIA's Jetson PyTorch wheels)

### 4. PyTorch 2.8.0 ✅ (CUDA verified working)

- **Source:** `pypi.jetson-ai-lab.io/jp6/cu126` (Jetson-specific wheel with SM 8.7)
- **Wheel:** `torch-2.8.0-cp310-cp310-linux_aarch64.whl` (cached at `~/wheels/`)
- **Arch list:** `['sm_87']` — correct for Orin
- **CUDA operations:** Verified working (matmul, numpy→CUDA interop)
- **TorchVision:** 0.23.0 (from same Jetson index, cached at `~/wheels/`)

### 5. LeRobot v0.4.4 ✅

- Cloned at `~/lerobot/`
- Git: checked out at `v0.4.4` (detached HEAD)
- Installed as editable: `pip install -e ".[feetech]"`
- **Why v0.4.4 not v0.5.0:** v0.5.0 requires Python ≥3.12 (uses `type` statement syntax), which is incompatible with Jetson PyTorch wheels (cp310 only). v0.4.4 natively supports Python ≥3.10 and has all SO-101 motor control, calibration, and teleoperation features.
- CLI tools: `lerobot-find-port`, `lerobot-calibrate`, `lerobot-teleoperate`, `lerobot-record`, `lerobot-train`
- `FeetechMotorsBus` importable from `lerobot.motors.feetech.feetech`

### 6. Feetech Servo SDK ✅

- Pip package: `feetech-servo-sdk 1.0.0`
- **Import name: `scservo_sdk`** (NOT `feetech_servo_sdk`)
- Verified importable

### 7. Serial Port Access ✅

- User `m` is in the `dialout` group (and many others: `adm`, `sudo`, `audio`, `video`, `plugdev`, `render`, `i2c`, `gpio`)

### 8. OpenCV 4.12.0 ✅

- Installed: `opencv-python-headless`

### 9. numpy 1.26.4 ✅ (pinned)

- **Must stay <2.0** — Jetson PyTorch 2.8.0 wheel was compiled against numpy 1.x
- If `pip install` of any package upgrades numpy to 2.x, run: `pip install 'numpy==1.26.4' --force-reinstall --no-deps`

### 10. Python Dependencies ✅

| Package | Version |
|---------|---------|
| anthropic | 0.86.0 |
| httpx | 0.28.1 |
| fastapi | 0.135.1 |
| uvicorn | 0.42.0 |

### 11. LeRobot CLI Tools ✅

All installed at `/home/m/miniforge3/envs/lerobot/bin/`:
- `lerobot-find-port` — works (prompts for user input; errors on EOF in non-interactive SSH)
- `lerobot-calibrate`
- `lerobot-teleoperate`
- `lerobot-record`
- `lerobot-train`

### 12. Cached Wheels ✅

Downloaded to `~/wheels/` for offline reinstall:
- `torch-2.8.0-cp310-cp310-linux_aarch64.whl` (216 MB, from jetson-ai-lab.io cu126)
- `torchvision-0.23.0-cp310-cp310-linux_aarch64.whl` (1.5 MB, from jetson-ai-lab.io cu126)
- `torch-2.5.0a0+872d972e41.nv24.08.17622132-cp310-cp310-linux_aarch64.whl` (770 MB, NVIDIA official JP v61, backup)

---

## Lessons Learned (the hard way)

### Problem: Standard PyPI PyTorch lacks SM 8.7

Standard PyTorch wheels from PyPI are compiled for desktop GPUs only. The Jetson Orin's GPU (SM 8.7) is not included. `torch.cuda.is_available()` returns `True` (misleadingly), but any actual CUDA operation crashes:

```
RuntimeError: CUDA error: no kernel image is available for execution on the device
```

**This is the #1 most common Jetson Orin issue.** NVIDIA forums have dozens of threads about it.

### Problem: Python 3.12 wheels don't exist for CUDA 12.6

- `pypi.jetson-ai-lab.io/jp6/cu126` only has **cp310** (Python 3.10) wheels
- `pypi.jetson-ai-lab.io/jp6/cu129` has **cp312** wheels, but they require **glibc 2.38** (JetPack 6 has glibc 2.35 — Ubuntu 22.04)
- The cp312 cu129 wheel errors with: `GLIBC_2.38 not found`

### Problem: LeRobot v0.5.0 requires Python 3.12

v0.5.0 uses Python 3.12-only syntax (`type` statement for type aliases). Cannot be patched without rewriting code. **v0.4.4** is the last version supporting Python 3.10, and it has all SO-101 features.

### Problem: numpy version conflict

- Jetson PyTorch wheels: compiled against numpy 1.x, crash with numpy 2.x
- LeRobot pulls in numpy 2.x via `pip install -e ".[feetech]"`
- **Fix:** After LeRobot install, force downgrade: `pip install 'numpy==1.26.4' --force-reinstall --no-deps`

### Problem: Jetson AI Lab index is unreliable

- `pypi.jetson-ai-lab.dev` — DNS doesn't resolve (dead)
- `pypi.jetson-ai-lab.io` — intermittent 403 errors with `wget` (works with `curl`)
- **Always download wheels to `~/wheels/` first**, don't depend on the index being up at install time
- Use `curl -L -o file.whl 'URL'` instead of `wget` (different user-agent handling)

---

## Useful Paths on Jetson

| Path | Description |
|------|-------------|
| `/home/m/miniforge3/` | Conda install |
| `/home/m/miniforge3/envs/lerobot/` | lerobot conda env (Python 3.10) |
| `/home/m/lerobot/` | LeRobot v0.4.4 source (editable install) |
| `/home/m/wheels/` | Cached PyTorch/TorchVision wheels for offline reinstall |
| `/usr/local/cuda-12.6/` | CUDA toolkit |
| `~/.bashrc` | Has conda init block |

## SSH Tips

```bash
# Interactive shell (conda auto-activates base):
ssh m@100.98.191.120

# Non-interactive command (must source conda manually):
ssh m@100.98.191.120 "source ~/miniforge3/etc/profile.d/conda.sh && conda activate lerobot && python -c 'import torch; print(torch.__version__)'"
```

## Recovery: Rebuilding the Environment from Scratch

If the env gets corrupted, here's the full rebuild using cached wheels:

```bash
source ~/miniforge3/etc/profile.d/conda.sh
conda deactivate
conda env remove -n lerobot -y
conda create -n lerobot python=3.10 -y
conda activate lerobot

# Install from cached wheels (no network needed)
pip install --no-cache-dir ~/wheels/torch-2.8.0-cp310-cp310-linux_aarch64.whl
pip install --no-cache-dir ~/wheels/torchvision-0.23.0-cp310-cp310-linux_aarch64.whl

# Install LeRobot v0.4.4
cd ~/lerobot
git checkout v0.4.4
pip install -e ".[feetech]"

# Fix numpy (LeRobot pulls in 2.x, torch needs 1.x)
pip install 'numpy==1.26.4' --force-reinstall --no-deps

# Other deps
pip install anthropic httpx fastapi uvicorn

# Verify
python -c "
import numpy as np; print('numpy:', np.__version__)
import torch; print('PyTorch:', torch.__version__, '| CUDA:', torch.cuda.is_available())
t = torch.tensor([1.0]).cuda(); print('CUDA test:', t * 2)
import lerobot; print('LeRobot:', lerobot.__version__)
from lerobot.motors.feetech.feetech import FeetechMotorsBus; print('FeetechMotorsBus: OK')
import cv2; print('OpenCV:', cv2.__version__)
print('ALL GOOD')
"
```

## Key Gotchas for Future Agents

1. **Python 3.10 required on Jetson** — NVIDIA's PyTorch wheels are cp310 only for CUDA 12.6.
2. **`numpy==1.26.4` pinned** — torch 2.8.0 wheel crashes with numpy 2.x. Always force-reinstall after pip operations.
3. **LeRobot v0.4.4 on Jetson** — v0.5.0 uses Python 3.12 syntax. Mac dev uses v0.5.0, Jetson uses v0.4.4.
4. **`--no-cache-dir` for pip** — prevents pip from reusing wrong-arch cached wheels.
5. **SM 8.7 is Jetson-specific** — standard PyPI torch wheels do NOT include this arch.
6. **`scservo_sdk` not `feetech_servo_sdk`** — the Feetech SDK's Python import name differs from the pip package name.
7. **`conda init` only works in interactive shells** — for scripted SSH, source the conda.sh profile manually.
8. **Use `curl` not `wget`** for downloading from `pypi.jetson-ai-lab.io` — wget gets 403.
9. **Wheel cache at `~/wheels/`** — always keep local copies; the Jetson AI Lab index goes down frequently.
10. **glibc 2.35 limit** — JetPack 6 (Ubuntu 22.04) cannot run wheels built for manylinux_2_38+.
