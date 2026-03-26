#!/usr/bin/env python3
"""Auto-calibrate SO-101 arms by driving joints to physical hard stops.

Adapted from umbra-robotics/lerobot auto_calibrate.ipynb for macOS.
Detects leader vs follower by motor voltage (~5V = leader, ~12V = follower).
Works from any starting position. Handles encoder boundary wrapping.

Usage:
    # Calibrate all connected arms:
    python scripts/auto_calibrate.py

    # Calibrate only follower:
    python scripts/auto_calibrate.py --arm follower

    # Calibrate only leader:
    python scripts/auto_calibrate.py --arm leader
"""

import argparse
import glob
import json
import time
from pathlib import Path

import scservo_sdk as scs
from lerobot.motors.feetech.feetech import FeetechMotorsBus
from lerobot.motors.motors_bus import Motor, MotorCalibration, MotorNormMode

# ── Constants ────────────────────────────────────────────────────────────────

VOLTAGE_ADDR = 62  # Present_Voltage register, 1 byte, unit = 0.1V
POS_MIN = 0
POS_MAX = 4095
MOVE_TORQUE = 600

# Per-joint tuning: max torque, load threshold for hard stop detection, grace period
JOINT_DEFAULTS = {
    "gripper":       {"max_torque": 400, "load_threshold": 250, "grace_s": 0.5},
    "wrist_flex":    {"max_torque": 500, "load_threshold": 350, "grace_s": 0.5},
    "elbow_flex":    {"max_torque": 800, "load_threshold": 400, "grace_s": 1.5},
    "shoulder_lift": {"max_torque": 800, "load_threshold": 450, "grace_s": 2.0},
    "shoulder_pan":  {"max_torque": 800, "load_threshold": 400, "grace_s": 1.5},
}

# SO-101 motor configuration (same for leader and follower)
SO101_MOTORS = {
    "shoulder_pan":  Motor(1, "sts3215", MotorNormMode.RANGE_M100_100),
    "shoulder_lift": Motor(2, "sts3215", MotorNormMode.RANGE_M100_100),
    "elbow_flex":    Motor(3, "sts3215", MotorNormMode.RANGE_M100_100),
    "wrist_flex":    Motor(4, "sts3215", MotorNormMode.RANGE_M100_100),
    "wrist_roll":    Motor(5, "sts3215", MotorNormMode.RANGE_M100_100),
    "gripper":       Motor(6, "sts3215", MotorNormMode.RANGE_0_100),
}


# ── Helper functions ─────────────────────────────────────────────────────────

MAX_RETRIES = 4
RETRY_DELAY = 0.15


def _safe_read(bus: FeetechMotorsBus, reg: str, motor: str, **kwargs) -> int:
    """Read a servo register with retries."""
    for attempt in range(MAX_RETRIES):
        try:
            return bus.read(reg, motor, normalize=False, **kwargs)
        except (RuntimeError, ConnectionError):
            time.sleep(RETRY_DELAY * (attempt + 1))
    raise ConnectionError(f"Failed to read {reg} on {motor} after {MAX_RETRIES} retries")


def _safe_write(bus: FeetechMotorsBus, reg: str, motor: str, value: int, **kwargs) -> None:
    """Write a servo register with retries."""
    for attempt in range(MAX_RETRIES):
        try:
            bus.write(reg, motor, value, normalize=False, **kwargs)
            return
        except (RuntimeError, ConnectionError):
            time.sleep(RETRY_DELAY * (attempt + 1))
    raise ConnectionError(f"Failed to write {reg}={value} on {motor} after {MAX_RETRIES} retries")


def _save_motor_settings(bus: FeetechMotorsBus, motor: str) -> dict:
    """Save current motor settings so we can restore them after calibration."""
    return {
        "Max_Torque_Limit": _safe_read(bus, "Max_Torque_Limit", motor),
        "Torque_Limit": _safe_read(bus, "Torque_Limit", motor),
        "Goal_Velocity": _safe_read(bus, "Goal_Velocity", motor),
        "Acceleration": _safe_read(bus, "Acceleration", motor),
        "P_Coefficient": _safe_read(bus, "P_Coefficient", motor),
        "I_Coefficient": _safe_read(bus, "I_Coefficient", motor),
    }


def _safe_disable_torque(bus: FeetechMotorsBus, motor: str | None = None) -> None:
    """Reliably disable torque, retrying to work around Lock register issues."""
    motors = [motor] if motor else list(bus.motors)
    for m in motors:
        mid = bus.motors[m].id
        for _ in range(5):
            bus.packet_handler.writeTxRx(bus.port_handler, mid, 55, 1, [0])  # Lock=0
            bus.packet_handler.writeTxRx(bus.port_handler, mid, 40, 1, [0])  # Torque_Enable=0
            time.sleep(0.02)
            data, comm, _ = bus.packet_handler.readTxRx(bus.port_handler, mid, 55, 1)
            if comm == 0 and data[0] == 0:
                break


def _hold_at_current(bus: FeetechMotorsBus, motor: str, torque: int = MOVE_TORQUE, verbose: bool = True) -> None:
    """Lock a joint at its current position."""
    pos = _safe_read(bus, "Present_Position", motor)
    _safe_write(bus, "Goal_Position", motor, pos)
    for attempt in range(MAX_RETRIES):
        try:
            bus.enable_torque(motor)
            break
        except (RuntimeError, ConnectionError):
            time.sleep(RETRY_DELAY * (attempt + 1))
    _safe_write(bus, "Torque_Limit", motor, torque)
    if verbose:
        print(f"    Holding {motor} at {pos}")


def _move_joint_to(
    bus: FeetechMotorsBus,
    motor: str,
    position: int,
    torque: int = MOVE_TORQUE,
    velocity: int = 200,
    acceleration: int = 10,
    settle_s: float = 1.5,
    verbose: bool = True,
) -> None:
    """Move a single joint to a target position and wait for it to settle."""
    position = max(POS_MIN, min(POS_MAX, position))
    if verbose:
        print(f"    Moving {motor} to {position}...")
    _safe_write(bus, "Torque_Limit", motor, torque)
    _safe_write(bus, "Goal_Velocity", motor, velocity)
    _safe_write(bus, "Acceleration", motor, acceleration)
    _safe_write(bus, "Goal_Position", motor, position)
    time.sleep(settle_s)
    try:
        actual = _safe_read(bus, "Present_Position", motor)
    except ConnectionError:
        actual = position
    if verbose:
        print(f"    {motor} at {actual} (target {position})")


def _find_hard_stop(
    bus: FeetechMotorsBus,
    motor: str,
    direction: int,
    baseline_load: float,
    load_threshold: int,
    step_size: int = 10,
    load_count: int = 4,
    stall_count: int = 15,
    grace_s: float = 0.5,
    timeout_s: float = 30.0,
    verbose: bool = True,
) -> tuple[int, str]:
    """Sweep a joint in one direction until hitting a physical hard stop.

    Detection uses two methods:
    1. Sustained opposing load exceeding threshold
    2. Stall detection (position not changing)
    """
    start_pos = bus.read("Present_Position", motor, normalize=False)
    goal = start_pos
    prev_pos = start_pos
    stalls = 0
    consecutive_loads = 0
    t0 = time.monotonic()
    stop_reason = "timeout"

    while time.monotonic() - t0 < timeout_s:
        goal += direction * step_size

        if goal < POS_MIN:
            goal = POS_MIN
            stop_reason = f"encoder boundary ({POS_MIN})"
            bus.write("Goal_Position", motor, goal, normalize=False)
            time.sleep(0.2)
            break
        if goal > POS_MAX:
            goal = POS_MAX
            stop_reason = f"encoder boundary ({POS_MAX})"
            bus.write("Goal_Position", motor, goal, normalize=False)
            time.sleep(0.2)
            break

        try:
            bus.write("Goal_Position", motor, goal, normalize=False)
        except (RuntimeError, ConnectionError):
            time.sleep(0.1)
            try:
                bus.write("Goal_Position", motor, goal, normalize=False)
            except (RuntimeError, ConnectionError):
                stop_reason = "write error"
                break
        time.sleep(0.05)

        try:
            cur_pos = bus.read("Present_Position", motor, normalize=False)
            cur_load = bus.read("Present_Load", motor, normalize=False)
        except (RuntimeError, ConnectionError) as e:
            stop_reason = f"servo error: {e}"
            break

        elapsed = time.monotonic() - t0
        opposing_load = (-direction) * (cur_load - baseline_load)

        if opposing_load > load_threshold:
            consecutive_loads += 1
            if consecutive_loads >= load_count:
                stop_reason = (
                    f"load={cur_load} sustained {consecutive_loads}x "
                    f"(baseline={baseline_load:.0f}, opposing={opposing_load:.0f})"
                )
                break
        else:
            consecutive_loads = 0

        if elapsed > grace_s:
            if abs(cur_pos - prev_pos) < 2:
                stalls += 1
                if stalls >= stall_count:
                    stop_reason = f"stall at {cur_pos}"
                    break
            else:
                stalls = 0

        prev_pos = cur_pos

    # Back off slightly from the hard stop to avoid overload
    backoff = goal - direction * step_size * 3
    backoff = max(POS_MIN, min(POS_MAX, backoff))
    try:
        bus.write("Goal_Position", motor, backoff, normalize=False)
    except (RuntimeError, ConnectionError):
        pass  # best effort backoff
    time.sleep(0.3)

    for _retry in range(3):
        try:
            final_pos = bus.read("Present_Position", motor, normalize=False)
            break
        except (RuntimeError, ConnectionError):
            time.sleep(0.3)
    else:
        final_pos = prev_pos

    if verbose:
        dir_label = "+" if direction > 0 else "-"
        elapsed = time.monotonic() - t0
        print(f"    [{dir_label}] stopped at {final_pos} after {elapsed:.1f}s ({stop_reason})")
    return final_pos, stop_reason


def _calibrate_joint(
    bus: FeetechMotorsBus,
    motor: str,
    step_size: int = 10,
    goal_velocity: int = 100,
    acceleration: int = 10,
    stall_count: int = 15,
    load_count: int = 4,
    timeout_s: float = 30.0,
    verbose: bool = True,
) -> tuple[MotorCalibration, int, int]:
    """Calibrate a single joint by sweeping to both hard stops."""
    defaults = JOINT_DEFAULTS.get(motor, {"max_torque": 400, "load_threshold": 350, "grace_s": 1.0})
    max_torque = defaults["max_torque"]
    load_threshold = defaults["load_threshold"]
    grace_s = defaults["grace_s"]

    if verbose:
        print(f"{'='*50}")
        print(f"  {motor} (torque={max_torque}, threshold={load_threshold}, grace={grace_s}s)")
        print(f"{'='*50}")

    _safe_disable_torque(bus, motor)
    bus.reset_calibration([motor])
    _safe_write(bus, "Min_Position_Limit", motor, 0)
    _safe_write(bus, "Max_Position_Limit", motor, 4095)
    ht_offsets = bus.set_half_turn_homings([motor])
    ht_offset = ht_offsets[motor]

    start_pos = _safe_read(bus, "Present_Position", motor)
    loads = []
    for _ in range(10):
        try:
            loads.append(_safe_read(bus, "Present_Load", motor))
        except ConnectionError:
            pass
        time.sleep(0.02)
    baseline_load = sum(loads) / len(loads) if loads else 0.0
    if verbose:
        print(f"    start_pos={start_pos} (ht_offset={ht_offset}), baseline_load={baseline_load:.1f}")

    _safe_write(bus, "Max_Torque_Limit", motor, max_torque)
    _safe_write(bus, "Acceleration", motor, acceleration)
    _safe_write(bus, "Goal_Velocity", motor, goal_velocity)
    _safe_write(bus, "Goal_Position", motor, start_pos)
    for attempt in range(MAX_RETRIES):
        try:
            bus.enable_torque(motor)
            break
        except (RuntimeError, ConnectionError):
            time.sleep(RETRY_DELAY * (attempt + 1))
    _safe_write(bus, "Torque_Limit", motor, max_torque)
    time.sleep(0.3)

    # Shoulder lift needs a kick to overcome static friction
    if motor == "shoulder_lift":
        kick = start_pos + 50
        kick = max(POS_MIN, min(POS_MAX, kick))
        _safe_write(bus, "Goal_Position", motor, kick)
        time.sleep(0.5)
        _safe_write(bus, "Goal_Position", motor, start_pos)
        time.sleep(0.3)
        if verbose:
            actual = _safe_read(bus, "Present_Position", motor)
            print(f"    after kick: pos={actual}")

    sweep_kw = dict(
        step_size=step_size, load_count=load_count, stall_count=stall_count,
        grace_s=grace_s, timeout_s=timeout_s, verbose=verbose,
    )

    # Sweep both directions, retry up to 3 times if zero range
    for _sweep_attempt in range(3):
        if verbose:
            print(f"    Searching negative direction...")
        limit_neg, reason_neg = _find_hard_stop(
            bus, motor, -1, baseline_load, load_threshold, **sweep_kw,
        )

        if verbose:
            print(f"    Searching positive direction...")
        limit_pos, reason_pos = _find_hard_stop(
            bus, motor, +1, baseline_load, load_threshold, **sweep_kw,
        )

        if abs(max(limit_neg, limit_pos) - min(limit_neg, limit_pos)) > 10:
            break
        if _sweep_attempt < 2:
            if verbose:
                print(f"    0 range detected — retrying sweep (attempt {_sweep_attempt+2}/3)...")
            _safe_disable_torque(bus, motor)
            time.sleep(0.3)
            _safe_write(bus, "Max_Torque_Limit", motor, max_torque)
            _safe_write(bus, "Min_Position_Limit", motor, 0)
            _safe_write(bus, "Max_Position_Limit", motor, 4095)
            _safe_write(bus, "Acceleration", motor, acceleration)
            _safe_write(bus, "Goal_Velocity", motor, goal_velocity)
            _safe_write(bus, "Goal_Position", motor, start_pos)
            for attempt in range(MAX_RETRIES):
                try:
                    bus.enable_torque(motor)
                    break
                except (RuntimeError, ConnectionError):
                    time.sleep(RETRY_DELAY * (attempt + 1))
            _safe_write(bus, "Torque_Limit", motor, max_torque)
            time.sleep(0.3)

    # Re-sweep if encoder boundary was hit
    for _resweep in range(5):
        if "encoder boundary" not in reason_neg and "encoder boundary" not in reason_pos:
            break
        # Accept result if we have a real stop on at least one side and range is reasonable
        current_range = abs(max(limit_neg, limit_pos) - min(limit_neg, limit_pos))
        has_real_neg = "encoder boundary" not in reason_neg
        has_real_pos = "encoder boundary" not in reason_pos
        if (has_real_neg or has_real_pos) and current_range > 200:
            if verbose:
                print(f"    Accepting partial result: range={current_range} ticks, "
                      f"neg={'real' if has_real_neg else 'boundary'}, "
                      f"pos={'real' if has_real_pos else 'boundary'}")
            break
        if verbose:
            print(f"    Encoder boundary hit — re-centering and re-sweeping (attempt {_resweep+1})...")
        eff_neg = POS_MIN if "encoder boundary" in reason_neg else limit_neg
        eff_pos = POS_MAX if "encoder boundary" in reason_pos else limit_pos
        mid = (eff_neg + eff_pos) // 2
        _safe_write(bus, "Goal_Velocity", motor, 40)
        _safe_write(bus, "Acceleration", motor, 5)
        _safe_write(bus, "Goal_Position", motor, mid)
        time.sleep(2.0)
        _safe_disable_torque(bus, motor)
        ht_offsets = bus.set_half_turn_homings([motor])
        ht_offset = ht_offsets[motor]
        new_start = _safe_read(bus, "Present_Position", motor)
        loads = []
        for _ in range(10):
            try:
                loads.append(_safe_read(bus, "Present_Load", motor))
            except ConnectionError:
                pass
            time.sleep(0.02)
        baseline_load = sum(loads) / len(loads) if loads else 0.0
        _safe_write(bus, "Goal_Position", motor, new_start)
        for attempt in range(MAX_RETRIES):
            try:
                bus.enable_torque(motor)
                break
            except (RuntimeError, ConnectionError):
                time.sleep(RETRY_DELAY * (attempt + 1))
        _safe_write(bus, "Torque_Limit", motor, max_torque)
        time.sleep(0.3)
        if verbose:
            print(f"    Re-centered at {new_start}, re-sweeping...")
        limit_neg, reason_neg = _find_hard_stop(
            bus, motor, -1, baseline_load, load_threshold, **sweep_kw,
        )
        limit_pos, reason_pos = _find_hard_stop(
            bus, motor, +1, baseline_load, load_threshold, **sweep_kw,
        )

    range_min = min(limit_neg, limit_pos)
    range_max = max(limit_neg, limit_pos)
    center = (range_min + range_max) // 2
    final_homing_offset = ht_offset + (center - 2047)
    final_homing_offset = max(-2047, min(2047, final_homing_offset))

    if verbose:
        total_range = range_max - range_min
        print(f"    range=[{range_min}, {range_max}] ({total_range} ticks)")
        print(f"    center={center}, final_offset={final_homing_offset}")

    cal = MotorCalibration(
        id=bus.motors[motor].id,
        drive_mode=0,
        homing_offset=final_homing_offset,
        range_min=range_min - (center - 2047),
        range_max=range_max - (center - 2047),
    )

    return cal, range_min, range_max


def auto_calibrate_from_home(
    bus: FeetechMotorsBus,
    continuous_joints: list[str] | None = None,
    step_size: int = 10,
    goal_velocity: int = 100,
    acceleration: int = 10,
    stall_count: int = 15,
    load_count: int = 4,
    timeout_per_direction_s: float = 30.0,
    save_path: Path | str | None = None,
    verbose: bool = True,
) -> dict[str, MotorCalibration]:
    """Auto-calibrate all joints from any starting position.

    Sequence:
    1. Gripper
    2. Elbow flex (gentle release, shoulder held)
    3. Wrist flex (elbow centered, shoulder held)
    4. Wrist roll (continuous joint, homing offset only)
    5. Shoulder lift (elbow stretched)
    6. Center all joints
    7. Shoulder pan (all joints locked)
    8. Victory pose + home
    """
    if continuous_joints is None:
        continuous_joints = ["wrist_roll"]

    calibration: dict[str, MotorCalibration] = {}
    joint_centers: dict[str, int] = {}
    joint_ranges: dict[str, tuple[int, int]] = {}

    all_saved = {}
    for motor in bus.motors:
        all_saved[motor] = _save_motor_settings(bus, motor)

    cal_kw = dict(
        step_size=step_size, goal_velocity=goal_velocity,
        acceleration=acceleration, stall_count=stall_count,
        load_count=load_count, timeout_s=timeout_per_direction_s,
        verbose=verbose,
    )

    try:
        _safe_disable_torque(bus)
        time.sleep(0.3)

        # ── 1. Gripper ──
        if "gripper" in bus.motors:
            if verbose:
                print(f"\n  1. gripper")
            cal, rmin, rmax = _calibrate_joint(bus, "gripper", **cal_kw)
            calibration["gripper"] = cal
            joint_centers["gripper"] = (rmin + rmax) // 2
            joint_ranges["gripper"] = (rmin, rmax)
            _move_joint_to(bus, "gripper", joint_centers["gripper"], verbose=verbose)

        # ── 2. Elbow flex ──
        if "elbow_flex" in bus.motors:
            if verbose:
                print(f"\n  2. elbow_flex (gentle release, hold shoulder)")
            if "shoulder_lift" in bus.motors:
                _hold_at_current(bus, "shoulder_lift", torque=800, verbose=verbose)
            if "shoulder_pan" in bus.motors:
                _hold_at_current(bus, "shoulder_pan", torque=600, verbose=verbose)
            if verbose:
                print(f"    Gently lowering elbow...")
            _hold_at_current(bus, "elbow_flex", torque=400, verbose=verbose)
            for t in [300, 200, 100, 50]:
                _safe_write(bus, "Torque_Limit", "elbow_flex", t)
                time.sleep(0.5)
            _safe_disable_torque(bus, "elbow_flex")
            time.sleep(1.5)
            if verbose:
                pos = _safe_read(bus, "Present_Position", "elbow_flex")
                print(f"    Elbow settled at {pos}")
            cal, rmin, rmax = _calibrate_joint(bus, "elbow_flex", **cal_kw)
            calibration["elbow_flex"] = cal
            joint_centers["elbow_flex"] = (rmin + rmax) // 2
            joint_ranges["elbow_flex"] = (rmin, rmax)
            _move_joint_to(bus, "elbow_flex", joint_centers["elbow_flex"], verbose=verbose)

        # ── 3. Wrist flex ──
        if "wrist_flex" in bus.motors:
            if verbose:
                print(f"\n  3. wrist_flex (hold shoulder + elbow)")
            if "shoulder_lift" in bus.motors:
                _hold_at_current(bus, "shoulder_lift", torque=800, verbose=verbose)
            if "shoulder_pan" in bus.motors:
                _hold_at_current(bus, "shoulder_pan", torque=600, verbose=verbose)
            if "elbow_flex" in joint_centers:
                _move_joint_to(bus, "elbow_flex", joint_centers["elbow_flex"], torque=800, settle_s=2.0, verbose=verbose)
            cal, rmin, rmax = _calibrate_joint(bus, "wrist_flex", **cal_kw)
            calibration["wrist_flex"] = cal
            joint_centers["wrist_flex"] = (rmin + rmax) // 2
            joint_ranges["wrist_flex"] = (rmin, rmax)
            _move_joint_to(bus, "wrist_flex", joint_centers["wrist_flex"], verbose=verbose)

        # ── 4. Wrist roll (continuous) ──
        for motor in continuous_joints:
            if motor not in bus.motors:
                continue
            if verbose:
                print(f"\n  4. {motor} (continuous)")
            _safe_disable_torque(bus, motor)
            bus.reset_calibration([motor])
            homing_offsets = bus.set_half_turn_homings([motor])
            calibration[motor] = MotorCalibration(
                id=bus.motors[motor].id, drive_mode=0,
                homing_offset=homing_offsets[motor], range_min=0, range_max=4095,
            )
            if verbose:
                print(f"    offset={homing_offsets[motor]}, range=0..4095")

        # ── 5. Stretch elbow for shoulder calibration ──
        if "elbow_flex" in joint_ranges:
            if verbose:
                print(f"\n  5. stretch elbow to max")
            if "shoulder_pan" in bus.motors:
                _hold_at_current(bus, "shoulder_pan", torque=600, verbose=verbose)
            _move_joint_to(bus, "elbow_flex", joint_ranges["elbow_flex"][0],
                           torque=800, settle_s=2.0, verbose=verbose)

        # ── 6. Shoulder lift ──
        if "shoulder_lift" in bus.motors:
            if verbose:
                print(f"\n  6. shoulder_lift")
            cal, rmin, rmax = _calibrate_joint(bus, "shoulder_lift", **cal_kw)
            calibration["shoulder_lift"] = cal
            shoulder_center = (rmin + rmax) // 2
            joint_centers["shoulder_lift"] = shoulder_center
            joint_ranges["shoulder_lift"] = (rmin, rmax)
            if verbose:
                print(f"    Returning shoulder_lift to center...")
            _move_joint_to(bus, "shoulder_lift", shoulder_center, torque=800, settle_s=2.5, verbose=verbose)
            actual = _safe_read(bus, "Present_Position", "shoulder_lift")
            if abs(actual - shoulder_center) > 100:
                if verbose:
                    print(f"    Retrying shoulder_lift centre...")
                _move_joint_to(bus, "shoulder_lift", shoulder_center, torque=800, settle_s=3.0, verbose=verbose)

        # ── 7. Centre all joints ──
        if verbose:
            print(f"\n  7. centre all joints")
        for jname, jcenter in joint_centers.items():
            t = 800 if "shoulder" in jname or "elbow" in jname else MOVE_TORQUE
            _move_joint_to(bus, jname, jcenter, torque=t, settle_s=1.0, verbose=verbose)

        # ── 8. Shoulder pan (all joints locked) ──
        if "shoulder_pan" in bus.motors:
            if verbose:
                print(f"\n  8. shoulder_pan")
                print(f"  Locking all joints before shoulder_pan sweep:")
            for jname in joint_centers:
                if jname == "shoulder_pan":
                    continue
                t = 800 if "shoulder" in jname or "elbow" in jname else MOVE_TORQUE
                _hold_at_current(bus, jname, torque=t, verbose=verbose)
            cal, rmin, rmax = _calibrate_joint(bus, "shoulder_pan", **cal_kw)
            calibration["shoulder_pan"] = cal
            joint_centers["shoulder_pan"] = (rmin + rmax) // 2
            joint_ranges["shoulder_pan"] = (rmin, rmax)
            _move_joint_to(bus, "shoulder_pan", joint_centers["shoulder_pan"], verbose=verbose)

        # ── Write calibration to EEPROM ──
        for motor in bus.motors:
            _safe_write(bus, "Lock", motor, 0)
        bus.write_calibration(calibration)
        if verbose:
            print(f"\n{'='*50}")
            print("  Calibration written to motors")
            print(f"{'='*50}")
            for name, c in calibration.items():
                rng = c.range_max - c.range_min
                print(f"    {name}: offset={c.homing_offset}, range=[{c.range_min}, {c.range_max}] ({rng} ticks)")

        # ── Victory pose + home ──
        if verbose:
            print(f"\n  Moving to home position...")
        for motor in bus.motors:
            pos = _safe_read(bus, "Present_Position", motor)
            _safe_write(bus, "Goal_Position", motor, pos)
        for attempt in range(MAX_RETRIES):
            try:
                bus.enable_torque()
                break
            except (RuntimeError, ConnectionError):
                time.sleep(RETRY_DELAY * (attempt + 1))
        for motor in bus.motors:
            t = 800 if "shoulder" in motor else MOVE_TORQUE
            _safe_write(bus, "Torque_Limit", motor, t)
            _safe_write(bus, "Goal_Velocity", motor, 40)
            _safe_write(bus, "Acceleration", motor, 5)

        if verbose:
            print(f"\n  Victory pose...")

        if "shoulder_pan" in calibration:
            cal_center = (calibration["shoulder_pan"].range_min + calibration["shoulder_pan"].range_max) // 2
            _move_joint_to(bus, "shoulder_pan", cal_center, torque=800, settle_s=1.5, verbose=verbose)

        if "shoulder_lift" in calibration:
            sl_center = (calibration["shoulder_lift"].range_min + calibration["shoulder_lift"].range_max) // 2
            _move_joint_to(bus, "shoulder_lift", sl_center, torque=800, settle_s=2.0, verbose=verbose)
        if "elbow_flex" in calibration:
            _move_joint_to(bus, "elbow_flex", calibration["elbow_flex"].range_min, torque=800, settle_s=2.0, verbose=verbose)
        if "wrist_flex" in calibration:
            wf_center = (calibration["wrist_flex"].range_min + calibration["wrist_flex"].range_max) // 2
            _move_joint_to(bus, "wrist_flex", wf_center, settle_s=1.0, verbose=verbose)

        if "gripper" in calibration:
            if verbose:
                print(f"    Gripper wave...")
            _move_joint_to(bus, "gripper", calibration["gripper"].range_max, settle_s=1.0, verbose=verbose)
            _move_joint_to(bus, "gripper", calibration["gripper"].range_min, settle_s=1.0, verbose=verbose)
            _move_joint_to(bus, "gripper", calibration["gripper"].range_max, settle_s=1.0, verbose=verbose)
            _move_joint_to(bus, "gripper", calibration["gripper"].range_min, settle_s=0.5, verbose=verbose)

        if verbose:
            print(f"\n  Moving to home position...")
        home_targets = {}
        if "shoulder_pan" in calibration:
            home_targets["shoulder_pan"] = (calibration["shoulder_pan"].range_min + calibration["shoulder_pan"].range_max) // 2
        if "shoulder_lift" in calibration:
            home_targets["shoulder_lift"] = calibration["shoulder_lift"].range_min
        if "elbow_flex" in calibration:
            home_targets["elbow_flex"] = calibration["elbow_flex"].range_max
        if "wrist_flex" in calibration:
            home_targets["wrist_flex"] = (calibration["wrist_flex"].range_min + calibration["wrist_flex"].range_max) // 2
        if "gripper" in calibration:
            home_targets["gripper"] = calibration["gripper"].range_min + int(
                (calibration["gripper"].range_max - calibration["gripper"].range_min) * 0.1
            )
        for motor, target in home_targets.items():
            t = 800 if "shoulder" in motor or "elbow" in motor else MOVE_TORQUE
            _safe_write(bus, "Torque_Limit", motor, t)
            _safe_write(bus, "Goal_Velocity", motor, 40)
            _safe_write(bus, "Acceleration", motor, 5)
            _safe_write(bus, "Goal_Position", motor, target)
        time.sleep(3.0)
        if verbose:
            for motor, target in home_targets.items():
                try:
                    actual = _safe_read(bus, "Present_Position", motor)
                except ConnectionError:
                    actual = "?"
                print(f"    {motor} -> {actual} (target {target})")
            print(f"    Home position reached, releasing torque...")

    except KeyboardInterrupt:
        print(f"\n  Interrupted! Disabling all torque...")
        _safe_disable_torque(bus)
        raise
    finally:
        _safe_disable_torque(bus)
        for motor, saved in all_saved.items():
            for reg, val in saved.items():
                try:
                    bus.write(reg, motor, val, normalize=False)
                except (RuntimeError, ConnectionError):
                    pass

    if save_path is not None:
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        cal_dict = {
            name: {
                "id": c.id, "drive_mode": c.drive_mode,
                "homing_offset": c.homing_offset,
                "range_min": c.range_min, "range_max": c.range_max,
            }
            for name, c in calibration.items()
        }
        save_path.write_text(json.dumps(cal_dict, indent=2))
        if verbose:
            print(f"  Saved to {save_path}")

    return calibration


# ── Port detection ───────────────────────────────────────────────────────────

def detect_ports() -> tuple[str | None, str | None]:
    """Detect leader and follower arms by reading motor voltage.

    Leader arm runs on ~5V (USB power), follower on ~12V (external PSU).
    Works on both macOS (/dev/tty.usbmodem*) and Linux (/dev/ttyACM*, /dev/ttyUSB*).
    """
    # macOS and Linux serial port patterns
    ports = sorted(
        glob.glob("/dev/tty.usbmodem*") +
        glob.glob("/dev/ttyACM*") +
        glob.glob("/dev/ttyUSB*")
    )

    if not ports:
        print("No serial ports found! Are the arms plugged in?")
        return None, None

    leader_port = None
    follower_port = None

    for port_path in ports:
        port = scs.PortHandler(port_path)
        if not port.openPort():
            print(f"  {port_path}: CANNOT OPEN")
            continue
        port.setBaudRate(1000000)
        ph = scs.PacketHandler(0)
        data, comm, _ = ph.readTxRx(port, 1, VOLTAGE_ADDR, 1)
        port.closePort()

        if comm != 0:
            print(f"  {port_path}: READ ERROR (comm={comm})")
            continue

        volts = data[0] / 10.0
        if volts > 6:
            label = "FOLLOWER (~12V)"
            follower_port = port_path
        else:
            label = "LEADER  (~5V)"
            leader_port = port_path
        print(f"  {port_path}: {volts:.1f}V  ->  {label}")

    return leader_port, follower_port


def calibrate_arm(port: str, arm_type: str, save_dir: Path | None = None) -> dict[str, MotorCalibration]:
    """Connect to an arm and run auto-calibration."""
    # Create fresh motor dict (Motor objects shouldn't be reused)
    motors = {
        "shoulder_pan":  Motor(1, "sts3215", MotorNormMode.RANGE_M100_100),
        "shoulder_lift": Motor(2, "sts3215", MotorNormMode.RANGE_M100_100),
        "elbow_flex":    Motor(3, "sts3215", MotorNormMode.RANGE_M100_100),
        "wrist_flex":    Motor(4, "sts3215", MotorNormMode.RANGE_M100_100),
        "wrist_roll":    Motor(5, "sts3215", MotorNormMode.RANGE_M100_100),
        "gripper":       Motor(6, "sts3215", MotorNormMode.RANGE_0_100),
    }

    bus = FeetechMotorsBus(port=port, motors=motors)
    bus.connect()
    print(f"\nConnected to {arm_type} on {port}")

    save_path = None
    if save_dir:
        save_path = save_dir / f"so101_{arm_type}.json"

    try:
        cal = auto_calibrate_from_home(bus, save_path=save_path)
    finally:
        bus.disconnect()
        print(f"\n{arm_type.capitalize()} disconnected.")

    return cal


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Auto-calibrate SO-101 arms")
    parser.add_argument(
        "--arm", choices=["leader", "follower", "both"], default="both",
        help="Which arm to calibrate (default: both)",
    )
    parser.add_argument(
        "--port", type=str, default=None,
        help="Override port (skip auto-detection). Use with --arm leader/follower.",
    )
    parser.add_argument(
        "--save-dir", type=str,
        default=str(Path.home() / ".cache/huggingface/lerobot/calibration/so101"),
        help="Directory to save calibration JSON files",
    )
    args = parser.parse_args()
    save_dir = Path(args.save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    results = {}

    if args.port:
        # Manual port override
        arm_type = args.arm if args.arm != "both" else "follower"
        results[arm_type] = calibrate_arm(args.port, arm_type, save_dir)
    else:
        # Auto-detect ports
        print("Detecting arms...")
        leader_port, follower_port = detect_ports()

        if args.arm in ("follower", "both") and follower_port:
            results["follower"] = calibrate_arm(follower_port, "follower", save_dir)
        elif args.arm in ("follower", "both") and not follower_port:
            print("No follower arm detected!")

        if args.arm in ("leader", "both") and leader_port:
            results["leader"] = calibrate_arm(leader_port, "leader", save_dir)
        elif args.arm in ("leader", "both") and not leader_port:
            print("No leader arm detected!")

    # Print summary
    if results:
        print(f"\n{'='*60}")
        print("  Calibration Summary")
        print(f"{'='*60}")
        for label, cal in results.items():
            print(f"\n  {label.upper()}:")
            print(f"    {'Joint':<15} {'ID':>3} {'Offset':>8} {'Min':>6} {'Max':>6} {'Range':>6}")
            print(f"    {'-'*15} {'-'*3} {'-'*8} {'-'*6} {'-'*6} {'-'*6}")
            for name, c in cal.items():
                rng = c.range_max - c.range_min
                print(f"    {name:<15} {c.id:>3} {c.homing_offset:>8} {c.range_min:>6} {c.range_max:>6} {rng:>6}")
        print(f"\n  Calibration files saved to: {save_dir}")
    else:
        print("\nNo arms were calibrated.")


if __name__ == "__main__":
    main()
