#!/usr/bin/env python3
"""Fun demo moves for the SO-101 follower arm.

Calibration from manual range-finding (2026-03-25).
Uses raw scservo_sdk. Goal_Velocity=0 = max speed on STS3215.

Usage:
    python scripts/demo_moves.py                     # run all moves
    python scripts/demo_moves.py wave                # just wave
    python scripts/demo_moves.py nod wave circle dance bow
"""

import math
import sys
import time

import cv2
import scservo_sdk as scs

# ── Calibration (manual 2026-03-25) ────────────────────────────────────────
# Directions confirmed by user:
#   shoulder_pan:  MIN=left,         MAX=right
#   shoulder_lift: MIN=folded/home,  MAX=raised up
#   elbow_flex:    MIN=extended out,  MAX=folded/home
#   wrist_flex:    MIN=bent backward, MAX=folded/home
#   wrist_roll:    MIN=clockwise,     MAX=counter-clockwise
#   gripper:       MIN=closed/home,   MAX=open

PAN, LIFT, ELBOW, WRIST, ROLL, GRIP = 1, 2, 3, 4, 5, 6

JOINTS = {
    PAN:   {"min": 708,  "home": 2030, "max": 3100},
    LIFT:  {"min": 799,  "home": 909,  "max": 2095},
    ELBOW: {"min": 949,  "home": 3185, "max": 3188},
    WRIST: {"min": 6,    "home": 4007, "max": 4084},
    ROLL:  {"min": 23,   "home": 2033, "max": 3946},
    GRIP:  {"min": 899,  "home": 899,  "max": 2457},
}

# Semantic position helpers — all take 0-100 percentage
def pan_left(pct):   return int(JOINTS[PAN]["home"] - (JOINTS[PAN]["home"] - JOINTS[PAN]["min"]) * pct / 100)
def pan_right(pct):  return int(JOINTS[PAN]["home"] + (JOINTS[PAN]["max"] - JOINTS[PAN]["home"]) * pct / 100)
def pan_center():    return JOINTS[PAN]["home"]

def lift_up(pct):    return int(JOINTS[LIFT]["home"] + (JOINTS[LIFT]["max"] - JOINTS[LIFT]["home"]) * pct / 100)
def lift_home():     return JOINTS[LIFT]["home"]

def elbow_extend(pct): return int(JOINTS[ELBOW]["home"] - (JOINTS[ELBOW]["home"] - JOINTS[ELBOW]["min"]) * pct / 100)
def elbow_home():      return JOINTS[ELBOW]["home"]

def wrist_straight(pct): return int(JOINTS[WRIST]["home"] - (JOINTS[WRIST]["home"] - 2000) * pct / 100)  # ~2000 = straight
def wrist_back(pct):     return int(2000 - (2000 - JOINTS[WRIST]["min"]) * pct / 100)  # past straight toward backward
def wrist_home():        return JOINTS[WRIST]["home"]

def roll_cw(pct):    return int(JOINTS[ROLL]["home"] - (JOINTS[ROLL]["home"] - JOINTS[ROLL]["min"]) * pct / 100)
def roll_ccw(pct):   return int(JOINTS[ROLL]["home"] + (JOINTS[ROLL]["max"] - JOINTS[ROLL]["home"]) * pct / 100)
def roll_center():   return JOINTS[ROLL]["home"]

def grip_open(pct):  return int(JOINTS[GRIP]["min"] + (JOINTS[GRIP]["max"] - JOINTS[GRIP]["min"]) * pct / 100)
def grip_closed():   return JOINTS[GRIP]["min"]


# ── Globals ────────────────────────────────────────────────────────────────
_port = None
_ph = None
_cap = None
_abort = False


def r16(mid, addr):
    for _ in range(8):
        data, comm, _ = _ph.readTxRx(_port, mid, addr, 2)
        if comm == 0 and len(data) >= 2:
            return data[0] | (data[1] << 8)
        time.sleep(0.05)
    return None


def w16(mid, addr, val):
    val = max(0, min(4095, int(val)))
    _ph.writeTxRx(_port, mid, addr, 2, [val & 0xFF, (val >> 8) & 0xFF])
    time.sleep(0.01)


def w8(mid, addr, val):
    _ph.writeTxRx(_port, mid, addr, 1, [val & 0xFF])
    time.sleep(0.01)


def pump(duration: float, label: str = "") -> bool:
    global _abort
    if _abort:
        return True
    end = time.time() + duration
    while time.time() < end:
        if _cap is not None:
            ret, frame = _cap.read()
            if ret:
                if label:
                    cv2.putText(frame, label, (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                cv2.imshow("SO-101 Demo", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                _abort = True
                return True
        else:
            time.sleep(0.01)
    return False


def go(positions: dict, delay: float = 0.0, label: str = ""):
    if _abort:
        return
    for mid, val in positions.items():
        w16(mid, 42, val)
    if delay > 0:
        pump(delay, label)


def home(delay: float = 2.0):
    go({mid: JOINTS[mid]["home"] for mid in range(1, 7)}, delay, "Home")


def ready(delay: float = 1.2):
    """Neutral working position: arm raised, elbow out, wrist straight."""
    go({
        PAN:   pan_center(),
        LIFT:  lift_up(80),
        ELBOW: elbow_extend(60),
        WRIST: wrist_straight(80),
        ROLL:  roll_center(),
        GRIP:  grip_closed(),
    }, delay, "Ready")


# ── Moves ──────────────────────────────────────────────────────────────────

def wave():
    print("  Wave!")
    # Raise arm up tall, open gripper like a hand
    go({LIFT: lift_up(90), ELBOW: elbow_extend(45), WRIST: wrist_straight(80), GRIP: grip_open(70)}, 1.5, "Wave")
    # Wave: swing the whole arm left-right using shoulder pan
    for _ in range(4):
        go({PAN: pan_left(30)}, 0.45, "Wave")
        go({PAN: pan_right(30)}, 0.45, "Wave")
    go({PAN: pan_center()}, 0.4, "Wave")
    home()


def nod():
    print("  Nod!")
    ready()
    # Nod wrist up and down
    for _ in range(3):
        go({WRIST: wrist_straight(100)}, 0.3, "Nod")
        go({WRIST: wrist_back(30)}, 0.3, "Nod")
    go({WRIST: wrist_straight(80)}, 0.3, "Nod")
    home()


def shake():
    print("  Shake!")
    ready()
    # Shake pan left and right
    for _ in range(3):
        go({PAN: pan_left(50)}, 0.3, "Shake")
        go({PAN: pan_right(50)}, 0.3, "Shake")
    go({PAN: pan_center()}, 0.3, "Shake")
    home()


def circle():
    print("  Circle!")
    ready()
    steps = 40
    for i in range(steps + 1):
        angle = 2 * math.pi * i / steps
        # Pan oscillates left/right, lift oscillates up/down
        pan_val = pan_center() + int((pan_right(60) - pan_center()) * math.cos(angle))
        lift_val = lift_up(60) + int((lift_up(90) - lift_up(60)) * math.sin(angle))
        go({PAN: pan_val, LIFT: lift_val}, 0.06, "Circle")
    go({PAN: pan_center()}, 0.3, "Circle")
    home()


def figure_eight():
    print("  Figure 8!")
    ready()
    steps = 60
    for i in range(steps + 1):
        t = 2 * math.pi * i / steps
        pan_val = pan_center() + int((pan_right(60) - pan_center()) * math.sin(t))
        lift_val = lift_up(60) + int((lift_up(90) - lift_up(60)) * math.sin(2 * t))
        go({PAN: pan_val, LIFT: lift_val}, 0.05, "Figure 8")
    go({PAN: pan_center()}, 0.3, "Figure 8")
    home()


def peek():
    print("  Peek!")
    # Start from home (hiding)
    pump(0.5, "Peek - hiding...")
    # Rise up and look around
    go({LIFT: lift_up(90), ELBOW: elbow_extend(65), WRIST: wrist_straight(80)}, 1.2, "Peek - rising!")
    go({PAN: pan_left(60)}, 0.5, "Peek - look left")
    go({PAN: pan_right(60)}, 0.8, "Peek - look right")
    go({PAN: pan_center()}, 0.4, "Peek")
    pump(0.3, "Peek")
    home(1.5)


def dance():
    print("  Dance!")
    ready()

    # Bob and weave
    for _ in range(2):
        go({PAN: pan_left(50), LIFT: lift_up(90), ROLL: roll_cw(50)}, 0.35, "Dance")
        go({PAN: pan_right(50), LIFT: lift_up(50), ROLL: roll_ccw(50)}, 0.35, "Dance")

    # Wrist spins
    go({PAN: pan_center(), LIFT: lift_up(80)}, 0.3, "Dance")
    for _ in range(3):
        go({ROLL: roll_cw(80)}, 0.18, "Dance")
        go({ROLL: roll_ccw(80)}, 0.18, "Dance")

    # Gripper claps
    go({ROLL: roll_center()}, 0.2, "Dance")
    for _ in range(5):
        go({GRIP: grip_closed()}, 0.1, "Dance")
        go({GRIP: grip_open(80)}, 0.1, "Dance")
    go({GRIP: grip_closed()}, 0.2, "Dance")
    home()


def bow():
    print("  Bow!")
    # Stand tall
    go({LIFT: lift_up(90), ELBOW: elbow_extend(60), WRIST: wrist_straight(80)}, 1.0, "Bow")
    pump(0.5, "Bow")
    # Bow: lower lift, extend elbow more, wrist down
    go({LIFT: lift_up(30), ELBOW: elbow_extend(80), WRIST: wrist_straight(100)}, 1.0, "Bow")
    pump(0.8, "Bow")
    # Rise
    go({LIFT: lift_up(90), ELBOW: elbow_extend(60), WRIST: wrist_straight(80)}, 1.0, "Bow")
    pump(0.4, "Bow")
    home()


def grab():
    print("  Grab!")
    # Open gripper
    go({GRIP: grip_open(90)}, 0.5, "Grab")
    # Reach: raise shoulder, extend arm down toward table
    go({LIFT: lift_up(40), ELBOW: elbow_extend(75), WRIST: wrist_straight(90)}, 1.0, "Grab")
    pump(0.3, "Grab")
    # Close gripper
    go({GRIP: grip_closed()}, 0.5, "Grab")
    pump(0.3, "Grab")
    # Lift
    go({LIFT: lift_up(85), ELBOW: elbow_extend(50)}, 1.0, "Grab")
    # Swing to side
    go({PAN: pan_left(60)}, 0.7, "Grab")
    # Lower and release
    go({LIFT: lift_up(40), ELBOW: elbow_extend(70)}, 0.7, "Grab")
    go({GRIP: grip_open(90)}, 0.5, "Grab")
    pump(0.3, "Grab")
    # Return
    go({LIFT: lift_up(70)}, 0.5, "Grab")
    go({PAN: pan_center(), GRIP: grip_closed()}, 0.6, "Grab")
    home()


# ── Registry ───────────────────────────────────────────────────────────────

MOVES = {
    "wave": wave, "nod": nod, "shake": shake, "circle": circle,
    "eight": figure_eight, "peek": peek, "dance": dance,
    "bow": bow, "grab": grab,
}

ALL_SEQUENCE = ["wave", "nod", "shake", "circle", "eight", "peek", "dance", "grab", "bow"]


def main():
    global _port, _ph, _cap

    requested = sys.argv[1:] if len(sys.argv) > 1 else ALL_SEQUENCE
    for name in requested:
        if name not in MOVES:
            print(f"Unknown move: {name}")
            print(f"Available: {', '.join(MOVES.keys())}")
            sys.exit(1)

    import glob
    ports = sorted(glob.glob("/dev/tty.usbmodem*"))
    if not ports:
        print("No arm found!")
        sys.exit(1)

    print(f"Connecting to {ports[0]}...")
    _port = scs.PortHandler(ports[0])
    _port.openPort()
    _port.setBaudRate(1000000)
    _ph = scs.PacketHandler(0)

    # Setup motors
    for mid in range(1, 7):
        w8(mid, 55, 0)      # unlock
        w8(mid, 40, 0)      # torque off
        w16(mid, 19, 0)     # offset = 0
        w16(mid, 9, 0)      # min pos = 0
        w16(mid, 11, 4095)  # max pos = 4095
        w16(mid, 16, 1000)  # max torque
        time.sleep(0.05)
    time.sleep(0.3)

    # Enable at current position
    for mid in range(1, 7):
        cur = r16(mid, 56)
        w16(mid, 42, cur)
        w16(mid, 48, 700)
        w8(mid, 41, 20)
        w16(mid, 46, 0)     # max speed!
        w8(mid, 40, 1)
        time.sleep(0.05)
    time.sleep(0.3)

    # Camera disabled — re-enable when USB camera is connected
    _cap = None

    try:
        print(f"\nRunning {len(requested)} moves: {', '.join(requested)}")
        print("Press q to stop.\n")
        for name in requested:
            if _abort:
                break
            MOVES[name]()
            pump(0.5)

        print("\nReturning home...")
        home(2.0)
        print("Done!")
    except KeyboardInterrupt:
        print("\nInterrupted!")
    finally:
        print("Disabling torque...")
        for mid in range(1, 7):
            w8(mid, 40, 0)
            time.sleep(0.03)
        _port.closePort()
        if _cap is not None:
            _cap.release()
        cv2.destroyAllWindows()
        print("Disconnected.")


if __name__ == "__main__":
    main()
