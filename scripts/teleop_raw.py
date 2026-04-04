#!/usr/bin/env python3
"""Foolproof SO-101 teleoperation — zero calibration required.

Reads raw encoder positions from leader, writes directly to follower.
No LeRobot, no calibration files, no EEPROM writes, no hard-stop seeking.
Uses scservo_sdk only.

Usage:
    # Auto-detect leader (5V) vs follower (12V):
    python scripts/teleop_raw.py /dev/ttyUSB0 /dev/ttyUSB1

    # Explicit assignment:
    python scripts/teleop_raw.py --follower /dev/ttyUSB0 --leader /dev/ttyUSB1

    # Dry run — just scan motors, don't move anything:
    python scripts/teleop_raw.py /dev/ttyUSB0 /dev/ttyUSB1 --scan-only
"""

import argparse
import signal
import sys
import time

import scservo_sdk as scs

# ── Constants ────────────────────────────────────────────────────────────────

BAUDRATE = 1_000_000
MOTOR_IDS = [1, 2, 3, 4, 5, 6]
JOINT_NAMES = {1: "pan", 2: "lift", 3: "elbow", 4: "wrist", 5: "roll", 6: "grip"}

# Feetech STS3215 register addresses
PRESENT_POSITION = 56    # 2 bytes, read-only
GOAL_POSITION = 42       # 2 bytes
TORQUE_ENABLE = 40       # 1 byte
LOCK = 55                # 1 byte (must be 0 to write EEPROM)
PRESENT_VOLTAGE = 62     # 1 byte, unit = 0.1V
TORQUE_LIMIT = 48        # 2 bytes
MAX_TORQUE_LIMIT = 14    # 2 bytes (EEPROM)
ACCELERATION = 41        # 1 byte
GOAL_VELOCITY = 46       # 2 bytes
PRESENT_LOAD = 58        # 2 bytes (bits 0-9 = magnitude, bit 10 = direction)

# Safety limits
MAX_POSITION_JUMP = 200  # Max encoder ticks per cycle (prevents slamming)
RAMP_STEPS = 80          # Steps for initial ramp to match leader
RAMP_DELAY = 0.025       # Seconds per ramp step


# ── Helpers ──────────────────────────────────────────────────────────────────

def open_port(path: str) -> tuple[scs.PortHandler, scs.PacketHandler]:
    ph = scs.PortHandler(path)
    pkt = scs.PacketHandler(0)  # Protocol 0 for Feetech
    if not ph.openPort():
        print(f"ERROR: Cannot open {path}")
        sys.exit(1)
    ph.setBaudRate(BAUDRATE)
    return ph, pkt


def read_pos(pkt: scs.PacketHandler, ph: scs.PortHandler, mid: int) -> int | None:
    pos, comm, _ = pkt.read2ByteTxRx(ph, mid, PRESENT_POSITION)
    return pos if comm == 0 else None


def read_all_positions(pkt: scs.PacketHandler, ph: scs.PortHandler) -> dict[int, int] | None:
    """Read all 6 motor positions. Returns None if any motor fails."""
    positions = {}
    for mid in MOTOR_IDS:
        pos = read_pos(pkt, ph, mid)
        if pos is None:
            return None
        positions[mid] = pos
    return positions


def read_voltage(pkt: scs.PacketHandler, ph: scs.PortHandler, mid: int) -> float | None:
    v, comm, _ = pkt.read1ByteTxRx(ph, mid, PRESENT_VOLTAGE)
    return v / 10.0 if comm == 0 else None


def detect_arm_type(pkt: scs.PacketHandler, ph: scs.PortHandler) -> str | None:
    """Detect leader (~5V) vs follower (~12V) by motor voltage."""
    voltages = []
    for mid in MOTOR_IDS:
        v = read_voltage(pkt, ph, mid)
        if v is not None:
            voltages.append(v)
    if not voltages:
        return None
    avg_v = sum(voltages) / len(voltages)
    if avg_v < 8.0:
        return "leader"
    else:
        return "follower"


def scan_port(label: str, pkt: scs.PacketHandler, ph: scs.PortHandler) -> bool:
    """Scan a port for all 6 motors, print status. Returns True if all found."""
    print(f"\n  {label}:")
    all_ok = True
    for mid in MOTOR_IDS:
        model, comm, _ = pkt.ping(ph, mid)
        if comm == 0:
            pos = read_pos(pkt, ph, mid)
            v = read_voltage(pkt, ph, mid)
            pos_str = f"{pos:5d}" if pos is not None else "  err"
            v_str = f"{v:.1f}V" if v is not None else "?.?V"
            print(f"    ID {mid} ({JOINT_NAMES[mid]:6s}): pos={pos_str}  voltage={v_str}")
        else:
            print(f"    ID {mid} ({JOINT_NAMES[mid]:6s}): NOT FOUND")
            all_ok = False
    return all_ok


def disable_torque(pkt: scs.PacketHandler, ph: scs.PortHandler):
    """Disable torque on all motors (safe shutdown)."""
    for mid in MOTOR_IDS:
        for _ in range(3):
            try:
                pkt.write1ByteTxRx(ph, mid, LOCK, 0)
                pkt.write1ByteTxRx(ph, mid, TORQUE_ENABLE, 0)
                break
            except Exception:
                time.sleep(0.02)


def enable_follower_torque(pkt: scs.PacketHandler, ph: scs.PortHandler):
    """Enable torque on follower with conservative settings."""
    for mid in MOTOR_IDS:
        # Unlock EEPROM so we can write torque limit
        pkt.write1ByteTxRx(ph, mid, LOCK, 0)
        time.sleep(0.01)
        # Set conservative torque limit (not max — protects servos)
        pkt.write2ByteTxRx(ph, mid, TORQUE_LIMIT, 600)
        time.sleep(0.01)
        # Smooth acceleration
        pkt.write1ByteTxRx(ph, mid, ACCELERATION, 20)
        time.sleep(0.01)
        # Set goal to current position BEFORE enabling torque (prevents jump)
        pos = read_pos(pkt, ph, mid)
        if pos is not None:
            pkt.write2ByteTxRx(ph, mid, GOAL_POSITION, pos)
            time.sleep(0.01)
        # Enable torque
        pkt.write1ByteTxRx(ph, mid, TORQUE_ENABLE, 1)
        time.sleep(0.01)
        # Lock EEPROM to prevent accidental writes
        pkt.write1ByteTxRx(ph, mid, LOCK, 1)
        time.sleep(0.01)


def clamp_step(current: int, target: int, max_step: int) -> int:
    """Limit how far we move in a single cycle."""
    diff = target - current
    if abs(diff) > max_step:
        return current + (max_step if diff > 0 else -max_step)
    return target


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SO-101 raw teleoperation (no calibration)")
    parser.add_argument("ports", nargs="*", help="Two serial ports (auto-detects leader/follower)")
    parser.add_argument("--follower", help="Explicit follower port")
    parser.add_argument("--leader", help="Explicit leader port")
    parser.add_argument("--fps", type=int, default=30, help="Loop rate (default: 30)")
    parser.add_argument("--scan-only", action="store_true", help="Scan motors and exit")
    parser.add_argument("--max-step", type=int, default=MAX_POSITION_JUMP,
                        help=f"Max encoder ticks per cycle (default: {MAX_POSITION_JUMP})")
    args = parser.parse_args()

    # Resolve ports
    if args.follower and args.leader:
        follower_port = args.follower
        leader_port = args.leader
    elif len(args.ports) == 2:
        follower_port, leader_port = args.ports[0], args.ports[1]  # Will auto-detect
    else:
        parser.error("Provide two ports as arguments, or use --follower and --leader")

    # Open both ports
    f_ph, f_pkt = open_port(follower_port)
    l_ph, l_pkt = open_port(leader_port)

    # Scan both
    print("Scanning motors...")
    f_ok = scan_port(f"Port {follower_port}", f_pkt, f_ph)
    l_ok = scan_port(f"Port {leader_port}", l_pkt, l_ph)

    if not f_ok or not l_ok:
        print("\nERROR: Not all motors found. Check connections and try again.")
        f_ph.closePort()
        l_ph.closePort()
        sys.exit(1)

    # Auto-detect leader vs follower if ports were positional
    if not (args.follower and args.leader):
        type1 = detect_arm_type(f_pkt, f_ph)
        type2 = detect_arm_type(l_pkt, l_ph)
        print(f"\n  Port {follower_port} detected as: {type1}")
        print(f"  Port {leader_port} detected as: {type2}")

        if type1 == "follower" and type2 == "leader":
            pass  # Already correct
        elif type1 == "leader" and type2 == "follower":
            # Swap
            follower_port, leader_port = leader_port, follower_port
            f_ph, l_ph = l_ph, f_ph
            f_pkt, l_pkt = l_pkt, f_pkt
            print("  (Swapped: auto-detected correct assignment)")
        else:
            print(f"\n  WARNING: Could not auto-detect arm types ({type1}, {type2}).")
            print(f"  Assuming {follower_port} = follower, {leader_port} = leader.")
            print(f"  If wrong, use --follower and --leader flags.\n")

    if args.scan_only:
        print("\nScan complete. Exiting (--scan-only).")
        f_ph.closePort()
        l_ph.closePort()
        return

    # ── Startup: ramp follower to match leader ───────────────────────────────

    print(f"\nFollower: {follower_port}")
    print(f"Leader:   {leader_port}")

    leader_pos = read_all_positions(l_pkt, l_ph)
    follower_pos = read_all_positions(f_pkt, f_ph)
    if leader_pos is None or follower_pos is None:
        print("ERROR: Cannot read positions. Check connections.")
        f_ph.closePort()
        l_ph.closePort()
        sys.exit(1)

    print("\nCurrent positions:")
    print(f"  Leader:   {leader_pos}")
    print(f"  Follower: {follower_pos}")

    max_diff = max(abs(leader_pos[m] - follower_pos[m]) for m in MOTOR_IDS)
    print(f"  Max difference: {max_diff} ticks")

    if max_diff > 50:
        print(f"\nRamping follower to match leader ({RAMP_STEPS} steps)...")
        enable_follower_torque(f_pkt, f_ph)
        for step in range(1, RAMP_STEPS + 1):
            t = step / RAMP_STEPS
            for mid in MOTOR_IDS:
                target = int(follower_pos[mid] + (leader_pos[mid] - follower_pos[mid]) * t)
                f_pkt.write2ByteTxRx(f_ph, mid, GOAL_POSITION, target)
            time.sleep(RAMP_DELAY)
        print("  Ramp complete.")
    else:
        print("\nArms already close — enabling torque...")
        enable_follower_torque(f_pkt, f_ph)

    # ── Main teleop loop ─────────────────────────────────────────────────────

    print(f"\nTeleoperating at {args.fps} Hz. Ctrl-C to stop.\n")

    running = True
    def handle_sigint(sig, frame):
        nonlocal running
        running = False
    signal.signal(signal.SIGINT, handle_sigint)

    loop_count = 0
    error_count = 0
    consecutive_errors = 0
    last_follower_pos = {mid: follower_pos[mid] for mid in MOTOR_IDS}

    while running:
        t0 = time.perf_counter()

        # Read leader
        lpos = read_all_positions(l_pkt, l_ph)
        if lpos is None:
            error_count += 1
            consecutive_errors += 1
            if consecutive_errors >= 20:
                print(f"\nFATAL: {consecutive_errors} consecutive read errors.")
                break
            time.sleep(0.005)
            continue

        # Write to follower with step clamping
        write_ok = True
        for mid in MOTOR_IDS:
            target = clamp_step(last_follower_pos[mid], lpos[mid], args.max_step)
            try:
                f_pkt.write2ByteTxRx(f_ph, mid, GOAL_POSITION, target)
                last_follower_pos[mid] = target
            except Exception:
                write_ok = False

        if not write_ok:
            error_count += 1
            consecutive_errors += 1
            if consecutive_errors >= 20:
                print(f"\nFATAL: {consecutive_errors} consecutive write errors.")
                break
            time.sleep(0.005)
            continue

        consecutive_errors = 0
        loop_count += 1
        if loop_count % 300 == 0:
            print(f"  {loop_count} loops, {error_count} errors", end="\r")

        # Rate limit
        elapsed = time.perf_counter() - t0
        remaining = max(1.0 / args.fps - elapsed, 0)
        if remaining > 0:
            time.sleep(remaining)

    # ── Shutdown ─────────────────────────────────────────────────────────────

    print(f"\n\nStopped. {loop_count} loops, {error_count} errors.")
    print("Disabling follower torque...")
    disable_torque(f_pkt, f_ph)
    time.sleep(0.5)

    f_ph.closePort()
    l_ph.closePort()
    print("Done.")


if __name__ == "__main__":
    main()
