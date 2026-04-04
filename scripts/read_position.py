"""Read and print the current position of all 6 servos."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from arm_skills import Arm, PAN, LIFT, ELBOW, WRIST, ROLL, GRIP

NAMES = {PAN: "PAN", LIFT: "LIFT", ELBOW: "ELBOW", WRIST: "WRIST", ROLL: "ROLL", GRIP: "GRIP"}

arm = Arm()
arm.connect()
try:
    positions = {}
    for mid in range(1, 7):
        val = arm.read_position(mid)
        positions[mid] = val
        print(f"  {NAMES[mid]:6s} (ID {mid}): {val}")
    print()
    print("As HOME dict:")
    print(f"HOME = {{PAN: {positions[PAN]}, LIFT: {positions[LIFT]}, ELBOW: {positions[ELBOW]}, WRIST: {positions[WRIST]}, ROLL: {positions[ROLL]}, GRIP: {positions[GRIP]}}}")
finally:
    arm.disconnect()
