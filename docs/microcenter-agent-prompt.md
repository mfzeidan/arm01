# Micro Center Shopping Agent Prompt

Copy-paste the below into a Claude cloud conversation when you're at the store.

---

I'm at Micro Center Fairfax (3089 Nutley St) buying parts for a custom ML training PC for robotics. I need you to help me make decisions on the fly as I find parts, compare prices, and deal with substitutions.

## What I'm building

A dedicated ML training rig for robotics vision-language-action (VLA) models. I'm building an autonomous sock-sorting robot using an SO-101 arm. Currently training on a Jetson Orin Nano (8GB shared VRAM) which is too limited. I need to train ACT, SmolVLA (450M params), and LoRA fine-tune pi0.5 (3B+ params) locally.

## My target parts list

| Part | Spec | Est. Price |
|------|------|-----------|
| **GPU** | PNY RTX Pro 4500 Blackwell — 32GB GDDR7, 10,496 CUDA cores, 200W, PCIe 5.0 | ~$2,700 |
| **CPU** | AMD Ryzen 9 9950X — 16-core, 5.7GHz, AM5, no stock cooler | ~$400-450 |
| **Motherboard** | X670E ATX (AM5) — must be X670E for full PCIe lanes (future second GPU) — 4 DIMM slots | ~$200-250 |
| **RAM** | 32GB DDR5 6000MHz (2x16GB) | ~$90 |
| **PSU** | 1000W 80+ Gold, fully modular, 2x 16-pin GPU connectors (12VHPWR/12V-2x6) | ~$150-170 |
| **Storage** | 2TB NVMe M.2 SSD | ~$120 |
| **Case** | Mid or full tower ATX — must fit 2 full-length GPUs (330mm+ clearance) | ~$80-100 |
| **Cooler** | 240mm AIO or large air tower — 9950X is 170W TDP | ~$60-100 |
| **Build service** | Express ProBuild (same-day) | ~$150 |
| **Total budget** | ~$3,950-4,100 | |

## Key constraints (non-negotiable)

- **GPU must have 24GB+ VRAM** — this is the whole point. 32GB on the Pro 4500 is ideal.
- **PSU must have 2x 16-pin GPU connectors** — for adding a second GPU later.
- **PSU must be 1000W+** — dual GPU headroom.
- **Motherboard must be X670E** (not B650) — full PCIe lanes for dual GPU.
- **Case must physically fit 2 full-length GPUs.**
- **CPU needs a separate cooler** — Ryzen 9 9950X does not include one.

## Where I'm flexible

- CPU: Could drop to Ryzen 7 9700X if 9950X is out of stock or not on sale.
- RAM: 32GB is fine for now (expandable to 128GB with 4 DIMM slots).
- Storage: 1TB acceptable if 2TB is overpriced, can add a second drive later.
- Cooler: Budget air ($35 Thermalright) is fine if AIO is out of stock.
- Case: Don't care about aesthetics, just needs GPU clearance and airflow.

## How to help me

I'll send you photos of price tags, spec sheets, and alternatives I find on the shelf. Help me:
1. Confirm parts are compatible
2. Evaluate substitutions (is this motherboard OK? is this PSU equivalent?)
3. Spot red flags (proprietary connectors, missing features, incompatible RAM speeds)
4. Compare prices to expected — flag if something seems overpriced
5. Keep a running total as I add parts

## Hardware advisor context

My friend Erik Rogers recommended:
- RTX Pro 4500 Blackwell for 32GB VRAM over consumer 5080/5090
- Ryzen 9 9950X (currently on sale)
- 1000W PSU with 2x 16-pin connectors for future second GPU
- Don't forget a cooler — Ryzen 9 doesn't include one

## My background

I'm building a sock-sorting robot (SO-101 arm + Claude Vision API). I have experience with the Jetson Orin Nano, Python/PyTorch ML stack, but I'm not a hardware expert. Explain compatibility issues plainly if they come up.
