# Training PC Build — Micro Center Fairfax

**Date:** 2026-04-02
**Goal:** ML training rig for robotics models (ACT, SmolVLA, pi0.5, future VLAs)
**Build service:** Micro Center Express ProBuild (same-day, ~$150)

## Parts List

| Part | Spec | Est. Price | Notes |
|------|------|-----------|-------|
| **GPU** | PNY RTX Pro 4500 Blackwell | ~$2,700 | 32GB GDDR7 ECC, 10,496 CUDA cores, 200W, PCIe 5.0. The key piece — 32GB VRAM handles LoRA fine-tuning of 3B+ models (pi0.5, SmolVLA, future VLAs). |
| **CPU** | AMD Ryzen 9 9950X | ~$400-450 | 16-core, 5.7GHz boost. On sale currently. AM5 socket. **Does NOT come with a cooler.** |
| **Motherboard** | X670E ATX (AM5) | ~$200-250 | Must be **X670E** (not B650) for full PCIe lanes — needed if adding a second GPU later. 4 DIMM slots. |
| **RAM** | 32GB DDR5 6000MHz (2x16GB) | ~$90 | Expandable to 128GB later (4 DIMM slots on X670E). |
| **PSU** | 1000W 80+ Gold, modular, **2x 16-pin GPU connectors** | ~$150-170 | 2x 16-pin (12VHPWR/12V-2x6) connectors for current + future second GPU. 1000W covers dual GPU headroom. |
| **Storage** | 2TB NVMe M.2 SSD | ~$120 | Training datasets (video episodes from 2 cameras) get big fast. |
| **Case** | Mid or full tower ATX | ~$80-100 | Must fit **2 full-length GPUs** (330mm+ clearance). Ask associate specifically. |
| **Cooler** | 240mm AIO liquid cooler OR large air tower | ~$60-100 | 9950X is 170W, no stock cooler. Good options: Arctic Liquid Freezer III 240 (~$80), Thermalright Peerless Assassin 120 (~$35 budget), Noctua NH-D15 (~$100 premium). |
| **Build service** | Express ProBuild | ~$150 | Buy parts 4+ hrs before store close. 90-day labor warranty, 1-year parts warranty. |
| **Total** | | **~$3,950-4,100** | |

## Key Reminders for the Associate

- **X670E motherboard, not B650** — need full PCIe lanes for potential second GPU
- **Case must fit 2 full-length GPUs** — ask explicitly
- **1000W PSU with 2x 16-pin connectors** — for future second GPU
- **CPU needs a cooler** — Ryzen 9 9950X does not include one
- Sustained all-core ML training workloads — cooler must handle 170W continuous

## Why These Choices

### GPU: RTX Pro 4500 (32GB) over consumer cards
- 32GB VRAM is the growth factor — can't upgrade later
- Trains models that 12-16GB cards literally cannot fit
- 200W power draw = cool, quiet, fits in anything
- ~20% slower than RTX 5090 in raw compute, but 5090 is unavailable/overpriced
- ECC memory = more stable during long training runs
- Recommendation from Erik Rogers (hardware advisor)

### CPU: Ryzen 9 9950X over Ryzen 7
- Currently on sale
- 16 cores helps with data preprocessing and multitasking
- AM5 platform has long support runway

### PSU: 1000W over 850W
- Pro 4500 only draws 200W, but 1000W + 2x 16-pin allows adding a second GPU later
- Erik Rogers recommendation for dual-GPU future-proofing

## What This Rig Can Train

| Model | Params | Can train? | Notes |
|-------|--------|-----------|-------|
| ACT | ~20M | Yes | Current sock sorting policy |
| Diffusion Policy | ~100M | Yes | Alternative to ACT |
| SmolVLA | 450M | Yes | Next step — VLA on SO-101 data |
| pi0.5 | 3B+ | Yes (LoRA) | Fine-tune with 32GB VRAM |
| OpenVLA | 7B | Tight (QLoRA) | Would benefit from second GPU |
| Future VLAs | ? | 32GB covers most | Add second GPU for bigger models |

## Comparison to Current Setup

| | Jetson Orin Nano (current) | **New Training PC** |
|---|---|---|
| GPU VRAM | 8GB shared | **32GB dedicated** |
| System RAM | 8GB shared | **32GB (expandable to 128GB)** |
| CUDA cores | 1,024 | **10,496** |
| Storage | 64GB eMMC + NVMe | **2TB NVMe** |
| Power | 15W | ~300W total system |
| Can train SmolVLA | No | **Yes** |
| Can fine-tune pi0.5 | No | **Yes** |

## Micro Center Fairfax

- **Address:** 3089 Nutley St, Fairfax, VA
- **Store page:** https://www.microcenter.com/site/stores/fairfax.aspx
- **Build service:** https://www.microcenter.com/site/service/instore-service-complete-build.aspx
- **Pro 4500 product page:** https://www.microcenter.com/product/697034/pny-nvidia-rtx-pro-4500-blackwell-single-fan-32gb-gddr7-pcie-50-graphics-card

## Training Area Upgrades (while you're shopping)

| Item | Search Term | Est. Price | Why |
|------|-----------|-----------|-----|
| Overhead LED panel light | `LED video panel light` | ~$40 | Eliminates shadow variance during recording/eval |
| Desk clamp camera arms (x2) | `articulating camera arm clamp desk mount` | ~$30 | Rigid, repeatable camera positions |
| Black/white felt backdrop | `black felt fabric yard` | ~$10 | Better contrast for vision models |
| Tri-fold foam board | `tri-fold foam display board` | ~$10 | Three-sided enclosure for consistent lighting |
