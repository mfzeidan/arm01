#!/usr/bin/env python3
"""Simple teleoperation script that bypasses lerobot's teleop_loop."""
import sys
import time
import signal

FOLLOWER_PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/tty.usbmodem5AAF2633821"
LEADER_PORT = sys.argv[2] if len(sys.argv) > 2 else "/dev/tty.usbmodem5B140314811"
FPS = int(sys.argv[3]) if len(sys.argv) > 3 else 30

from lerobot.robots.so_follower.so_follower import SOFollower, SOFollowerRobotConfig
from lerobot.teleoperators.so_leader.so_leader import SOLeader, SOLeaderTeleopConfig

robot = SOFollower(SOFollowerRobotConfig(port=FOLLOWER_PORT))
teleop = SOLeader(SOLeaderTeleopConfig(port=LEADER_PORT))

teleop.connect()
robot.connect()

import scservo_sdk as scs
ph = robot.bus.port_handler
pkt = robot.bus.packet_handler

# Home position — safe resting pose (protects wrist camera)
HOME_POS = {1: 1924, 2: 2050, 3: 3083, 4: 858, 5: 1981, 6: 2088}

def go_home(steps=50, delay=0.02):
    """Smoothly move follower to home position."""
    # Read current positions
    current = {}
    for mid in range(1, 7):
        pos, c, e = pkt.read2ByteTxRx(ph, mid, 56)
        if c == 0:
            current[mid] = pos
    if len(current) < 6:
        return
    # Interpolate
    for step in range(1, steps + 1):
        t = step / steps
        for mid in range(1, 7):
            target = int(current[mid] + (HOME_POS[mid] - current[mid]) * t)
            pkt.write2ByteTxRx(ph, mid, 42, target)  # Goal_Position
        time.sleep(delay)

print(f"Connected. Teleoperating at {FPS} Hz. Ctrl-C to stop.")

running = True
def handle_sigint(sig, frame):
    global running
    running = False
signal.signal(signal.SIGINT, handle_sigint)

loop_count = 0
error_count = 0
consecutive_errors = 0

while running:
    loop_start = time.perf_counter()

    # Read leader position
    try:
        action = teleop.get_action()
    except Exception as e:
        error_count += 1
        consecutive_errors += 1
        if consecutive_errors >= 10:
            print(f"\n  FATAL: {consecutive_errors} consecutive errors, last: {e}")
            break
        print(f"\n  leader read error #{error_count}: {e}")
        time.sleep(0.01)
        continue

    # Send to follower
    try:
        robot.send_action(action)
        consecutive_errors = 0
    except Exception as e:
        error_count += 1
        consecutive_errors += 1
        if consecutive_errors >= 10:
            print(f"\n  FATAL: {consecutive_errors} consecutive errors, last: {e}")
            break
        print(f"\n  follower write error #{error_count}: {e}")
        time.sleep(0.01)
        continue

    loop_count += 1
    if loop_count % 100 == 0:
        print(f"  {loop_count} loops, {error_count} errors")

    # Rate limit
    elapsed = time.perf_counter() - loop_start
    remaining = max(1.0 / FPS - elapsed, 0)
    if remaining > 0:
        time.sleep(remaining)

print(f"\nStopped. {loop_count} loops, {error_count} errors.")

# Return to home position before disabling torque
print("Returning to home position...")
try:
    go_home()
    # Hold position briefly so joints settle
    time.sleep(1.0)
except Exception:
    pass

# Force disable torque on all follower motors before disconnect
for mid in range(1, 7):
    for _ in range(3):
        try:
            pkt.write1ByteTxRx(ph, mid, 48, 0)  # Lock = 0
            pkt.write1ByteTxRx(ph, mid, 40, 0)  # Torque_Enable = 0
            break
        except Exception:
            time.sleep(0.05)

try:
    teleop.disconnect()
except Exception:
    pass
try:
    robot.disconnect()
except Exception:
    pass
