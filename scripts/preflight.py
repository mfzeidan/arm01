#!/usr/bin/env python3
"""Pre-recording hardware checks for SO-101 training data collection.

Verifies cameras, arm ports, .env configuration, and workspace readiness
before starting a recording session. Run this BEFORE every session.

Usage:
    python scripts/preflight.py
    python scripts/preflight.py --env backend/.env
"""
import argparse
import os
import sys
import time

# ── Colors ────────────────────────────────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"

def ok(msg):
    print(f"  {GREEN}✓{RESET} {msg}")

def fail(msg):
    print(f"  {RED}✗{RESET} {msg}")

def warn(msg):
    print(f"  {YELLOW}!{RESET} {msg}")


def load_env(env_path):
    """Load key=value pairs from .env file."""
    env = {}
    if not os.path.exists(env_path):
        return env
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                env[key.strip()] = val.strip()
    return env


def check_env(env_path):
    """Check .env file exists and has required values."""
    print(f"\n{BOLD}1. Environment (.env){RESET}")
    errors = 0

    if not os.path.exists(env_path):
        fail(f"{env_path} not found — copy from .env.example")
        return {}, 1

    env = load_env(env_path)
    ok(f"{env_path} loaded")

    required = {
        "FOLLOWER_PORT": "arm follower USB port",
        "LEADER_PORT": "arm leader USB port",
        "CAMERA_RIGHT_INDEX": "right camera index",
        "CAMERA_WRIST_INDEX": "wrist camera index",
        "CAMERA_ACROSS_INDEX": "across camera index",
    }

    for key, desc in required.items():
        val = env.get(key, "")
        if not val or "XXXXX" in val or val == "":
            fail(f"{key} not configured ({desc})")
            errors += 1
        else:
            ok(f"{key} = {val}")

    return env, errors


def check_cameras(env):
    """Verify all 3 cameras open and capture frames."""
    print(f"\n{BOLD}2. Cameras{RESET}")
    errors = 0

    try:
        import cv2
    except ImportError:
        fail("OpenCV not installed (pip install opencv-python)")
        return 3

    cameras = {
        "right": int(env.get("CAMERA_RIGHT_INDEX", 0)),
        "wrist": int(env.get("CAMERA_WRIST_INDEX", 1)),
        "across": int(env.get("CAMERA_ACROSS_INDEX", 2)),
    }

    for name, idx in cameras.items():
        cap = cv2.VideoCapture(idx)
        if not cap.isOpened():
            fail(f"{name} camera (index {idx}) — cannot open")
            errors += 1
            continue

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        # Read a few frames to let the camera stabilize
        for _ in range(5):
            ret, frame = cap.read()
            time.sleep(0.05)

        if not ret or frame is None:
            fail(f"{name} camera (index {idx}) — opened but no frames")
            errors += 1
        else:
            h, w = frame.shape[:2]
            ok(f"{name} camera (index {idx}) — {w}x{h}")

        cap.release()

    if errors == 0:
        ok("All 3 cameras capturing")
    else:
        warn("Cameras must be plugged DIRECTLY into USB ports (no hubs)")

    return errors


def check_arm_ports(env):
    """Verify arm serial ports exist."""
    print(f"\n{BOLD}3. Arm Ports{RESET}")
    errors = 0

    follower = env.get("FOLLOWER_PORT", "")
    leader = env.get("LEADER_PORT", "")

    for name, port in [("Follower", follower), ("Leader", leader)]:
        if not port:
            fail(f"{name} port not set in .env")
            errors += 1
        elif not os.path.exists(port):
            fail(f"{name} port {port} — device not found")
            errors += 1
        else:
            ok(f"{name} port {port}")

    if follower and leader and follower == leader:
        fail("Follower and leader ports are the same!")
        errors += 1

    return errors


def check_arm_connectivity(env):
    """Try to ping a servo on each arm to verify serial communication."""
    print(f"\n{BOLD}4. Servo Communication{RESET}")
    errors = 0

    follower = env.get("FOLLOWER_PORT", "")
    leader = env.get("LEADER_PORT", "")

    try:
        import scservo_sdk as scs
    except ImportError:
        warn("scservo_sdk not installed — skipping servo ping")
        return 0

    for name, port in [("Follower", follower), ("Leader", leader)]:
        if not port or not os.path.exists(port):
            continue

        try:
            ph = scs.PortHandler(port)
            ph.openPort()
            ph.setBaudRate(1000000)
            pkt = scs.PacketHandler(0)

            # Try to read position of motor ID 1
            data, comm, err = pkt.readTxRx(ph, 1, 56, 2)  # Present_Position
            ph.closePort()

            if comm == 0 and len(data) >= 2:
                pos = data[0] | (data[1] << 8)
                ok(f"{name} servo 1 responds (pos={pos})")
            else:
                fail(f"{name} servo 1 — no response (comm={comm})")
                errors += 1
        except Exception as e:
            fail(f"{name} serial error: {e}")
            errors += 1

    return errors


def check_workspace():
    """Remind about workspace setup."""
    print(f"\n{BOLD}5. Workspace (manual checks){RESET}")
    checks = [
        "Grid mat flat on workspace, coordinates visible to cameras",
        "No clutter visible in camera views",
        "Consistent lighting — no moving shadows",
        "Socks ready (4-5 distinct colors for this session)",
        "Camera mounts are rigid and stable (right + across)",
        "Wrist camera cable has slack, won't snag",
    ]
    for check in checks:
        print(f"  [ ] {check}")
    return 0


def check_disk_space():
    """Verify enough disk space for recording."""
    print(f"\n{BOLD}6. Disk Space{RESET}")
    import shutil
    total, used, free = shutil.disk_usage(os.path.expanduser("~"))
    free_gb = free / (1024 ** 3)
    if free_gb < 5:
        fail(f"Only {free_gb:.1f} GB free — need at least 5 GB for recording")
        return 1
    ok(f"{free_gb:.1f} GB free")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Pre-recording hardware checks")
    parser.add_argument("--env", default=None,
                        help="Path to .env file (default: backend/.env)")
    args = parser.parse_args()

    # Find .env relative to project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    if args.env:
        env_path = args.env
    else:
        env_path = os.path.join(project_root, "backend", ".env")

    print(f"{BOLD}SO-101 Pre-Recording Preflight Check{RESET}")
    print("=" * 45)

    total_errors = 0

    env, errors = check_env(env_path)
    total_errors += errors

    total_errors += check_cameras(env)
    total_errors += check_arm_ports(env)
    total_errors += check_arm_connectivity(env)
    check_workspace()
    total_errors += check_disk_space()

    # Summary
    print(f"\n{'=' * 45}")
    if total_errors == 0:
        print(f"{GREEN}{BOLD}ALL CHECKS PASSED{RESET} — ready to record!")
        print(f"\nNext: python scripts/record_episodes.py --session 1")
    else:
        print(f"{RED}{BOLD}{total_errors} CHECK(S) FAILED{RESET} — fix before recording")
        sys.exit(1)


if __name__ == "__main__":
    main()
