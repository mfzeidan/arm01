#!/usr/bin/env python3
"""Visual auto-calibration: sweep the arm while a camera tracks the gripper tip.

Moves the SO-101 follower arm through a grid of shoulder_pan × shoulder_lift
positions, captures camera frames at each one, detects a brightly colored marker
on the gripper tip, and builds a joint-angles-to-pixel mapping.  After the sweep
the detected positions are mapped to grid cells (A1, B2, …) using the physical
mat lines visible in the frame, and the result is saved in GridCalibration format.

Usage:
    # Full sweep (auto-detect arm port + camera 0):
    python scripts/visual_calibrate.py

    # Preview camera only (check marker detection, no arm movement):
    python scripts/visual_calibrate.py --preview

    # Dry run (print planned positions, no arm movement or camera):
    python scripts/visual_calibrate.py --dry-run

    # Override port / camera / grid size:
    python scripts/visual_calibrate.py --port /dev/tty.usbmodem1234 --camera 1 --grid 8x8

    # Adjust marker color range (HSV lower/upper):
    python scripts/visual_calibrate.py --hsv-lower 35,100,100 --hsv-upper 85,255,255
"""

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

# ── Reuse motor helpers from auto_calibrate ─────────────────────────────────
# Append the scripts/ dir so we can import from sibling module.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from auto_calibrate import (
    SO101_MOTORS,
    _move_joint_to,
    _safe_disable_torque,
    _safe_read,
    _safe_write,
    detect_ports,
)

import scservo_sdk as scs
from lerobot.motors.feetech.feetech import FeetechMotorsBus
from lerobot.motors.motors_bus import Motor, MotorNormMode

# ── Defaults ────────────────────────────────────────────────────────────────

# Marker detection: pink marker on gripper tips (HSV range).  Adjust with CLI flags.
DEFAULT_HSV_LOWER = (140, 50, 80)
DEFAULT_HSV_UPPER = (175, 255, 255)

# Sweep parameters
SWEEP_VELOCITY = 120
SWEEP_ACCELERATION = 15
SETTLE_TIME = 0.3  # seconds after each move before capture

# Fixed joint positions for elbow / wrist / gripper during sweep.
# These keep the arm extended forward at a comfortable height.
# Values are raw encoder ticks — will be overridden if we can read current
# calibration, but these are reasonable for a freshly calibrated SO-101.
FIXED_ELBOW = 2048       # roughly centered
FIXED_WRIST_FLEX = 2048
FIXED_WRIST_ROLL = 2048
FIXED_GRIPPER = 2048     # partially open

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
CALIBRATION_OUT = BACKEND_DIR / "calibration_data.json"
SWEEP_OUT = BACKEND_DIR / "sweep_data.json"


# ── Marker detection ────────────────────────────────────────────────────────

def detect_marker(frame: np.ndarray, hsv_lower: tuple, hsv_upper: tuple,
                  min_area: int = 80) -> tuple[int, int] | None:
    """Detect the largest blob matching the HSV range.  Returns (x, y) or None."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(hsv_lower), np.array(hsv_upper))

    # Morphological cleanup
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < min_area:
        return None

    M = cv2.moments(largest)
    if M["m00"] == 0:
        return None
    cx = int(M["m10"] / M["m00"])
    cy = int(M["m01"] / M["m00"])
    return (cx, cy)


def draw_detection(frame: np.ndarray, point: tuple[int, int] | None,
                   hsv_lower: tuple, hsv_upper: tuple) -> np.ndarray:
    """Draw marker detection overlay on frame (for preview)."""
    display = frame.copy()
    if point is not None:
        cv2.circle(display, point, 12, (0, 255, 0), 2)
        cv2.circle(display, point, 3, (0, 0, 255), -1)
        cv2.putText(display, f"({point[0]}, {point[1]})", (point[0] + 15, point[1] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    else:
        cv2.putText(display, "No marker detected", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    # Show HSV range in corner
    cv2.putText(display, f"HSV: {hsv_lower}-{hsv_upper}", (10, display.shape[0] - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
    return display


# ── Camera helpers ──────────────────────────────────────────────────────────

def open_camera(index: int) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera {index}.  Check macOS Privacy > Camera.")
    # Set 720p
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    # Burn a few frames so auto-exposure settles
    for _ in range(10):
        cap.read()
    return cap


def capture_frame(cap: cv2.VideoCapture) -> np.ndarray:
    """Read a frame, retrying once on failure."""
    ret, frame = cap.read()
    if not ret:
        time.sleep(0.1)
        ret, frame = cap.read()
    if not ret:
        raise RuntimeError("Camera read failed")
    return frame


# ── Arm helpers ─────────────────────────────────────────────────────────────

def make_bus(port: str) -> FeetechMotorsBus:
    """Create a fresh FeetechMotorsBus for the follower arm."""
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
    return bus


def read_all_joints(bus: FeetechMotorsBus) -> list[float]:
    """Read current raw positions of all 6 joints."""
    names = ["shoulder_pan", "shoulder_lift", "elbow_flex",
             "wrist_flex", "wrist_roll", "gripper"]
    return [float(_safe_read(bus, "Present_Position", n)) for n in names]


def move_to_position(bus: FeetechMotorsBus, shoulder_pan: int, shoulder_lift: int,
                     elbow_flex: int, wrist_flex: int, wrist_roll: int, gripper: int,
                     verbose: bool = True) -> None:
    """Move all joints to target positions — commands all joints at once."""
    targets = {
        "shoulder_pan": shoulder_pan,
        "shoulder_lift": shoulder_lift,
        "elbow_flex": elbow_flex,
        "wrist_flex": wrist_flex,
        "wrist_roll": wrist_roll,
        "gripper": gripper,
    }
    # Command all joints without per-joint settle
    for motor, pos in targets.items():
        _safe_write(bus, "Goal_Position", motor, pos)
    if verbose:
        actual_pan = _safe_read(bus, "Present_Position", "shoulder_pan")
        actual_lift = _safe_read(bus, "Present_Position", "shoulder_lift")
        print(f"  -> pan={actual_pan} lift={actual_lift}")


def enable_all_torque(bus: FeetechMotorsBus) -> None:
    """Enable torque on all motors with gentle settings."""
    for motor in bus.motors:
        pos = _safe_read(bus, "Present_Position", motor)
        _safe_write(bus, "Goal_Position", motor, pos)
    for attempt in range(4):
        try:
            bus.enable_torque()
            break
        except (RuntimeError, ConnectionError):
            time.sleep(0.15 * (attempt + 1))
    for motor in bus.motors:
        torque = 600 if "shoulder" in motor or "elbow" in motor else 400
        _safe_write(bus, "Torque_Limit", motor, torque)
        _safe_write(bus, "Goal_Velocity", motor, SWEEP_VELOCITY)
        _safe_write(bus, "Acceleration", motor, SWEEP_ACCELERATION)


# ── Grid cell mapping ───────────────────────────────────────────────────────

def detect_grid_bounds(frame: np.ndarray) -> tuple[tuple[int,int], tuple[int,int]] | None:
    """Try to detect grid mat bounds from a frame using line detection.

    Returns ((x_min, x_max), (y_min, y_max)) of the grid area in pixels,
    or None if detection fails.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)

    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80,
                            minLineLength=100, maxLineGap=10)
    if lines is None or len(lines) < 4:
        return None

    # Separate horizontal and vertical lines
    h_lines = []
    v_lines = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = abs(np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi)
        if angle < 15 or angle > 165:  # horizontal
            h_lines.append((min(y1, y2), max(y1, y2)))
        elif 75 < angle < 105:  # vertical
            v_lines.append((min(x1, x2), max(x1, x2)))

    if len(h_lines) < 2 or len(v_lines) < 2:
        return None

    y_coords = [y for y1, y2 in h_lines for y in (y1, y2)]
    x_coords = [x for x1, x2 in v_lines for x in (x1, x2)]

    return ((min(x_coords), max(x_coords)), (min(y_coords), max(y_coords)))


def pixel_to_grid_cell(px: int, py: int,
                       grid_x_range: tuple[int,int], grid_y_range: tuple[int,int],
                       cols: int = 10, rows: int = 12) -> str:
    """Map a pixel coordinate to a grid cell label like 'B3'."""
    x_min, x_max = grid_x_range
    y_min, y_max = grid_y_range

    # Clamp
    px = max(x_min, min(x_max, px))
    py = max(y_min, min(y_max, py))

    col = int((px - x_min) / (x_max - x_min) * cols)
    row = int((py - y_min) / (y_max - y_min) * rows)
    col = max(0, min(cols - 1, col))
    row = max(0, min(rows - 1, row))

    letter = chr(ord("A") + col)
    number = row + 1
    return f"{letter}{number}"


# ── Sweep plan ──────────────────────────────────────────────────────────────

def plan_sweep(bus: FeetechMotorsBus | None, grid_rows: int, grid_cols: int,
               ) -> list[dict]:
    """Generate the list of positions to visit.

    The sweep covers shoulder_pan and shoulder_lift ranges evenly.
    Elbow / wrist / gripper are held at fixed (centered) positions.

    If a bus is provided, reads calibration-based range limits.  Otherwise uses
    conservative defaults.
    """
    # Default conservative ranges (raw encoder ticks, 0-4095)
    pan_min, pan_max = 1024, 3072       # ~90° of pan each side of center
    lift_min, lift_max = 1200, 2800     # avoid extremes to keep arm safe

    if bus is not None:
        # Try to read tighter ranges from the arm's current calibration
        try:
            cur_pan = _safe_read(bus, "Present_Position", "shoulder_pan")
            cur_lift = _safe_read(bus, "Present_Position", "shoulder_lift")
            # Use 80% of full range centered on current position
            pan_min = max(0, cur_pan - 900)
            pan_max = min(4095, cur_pan + 900)
            lift_min = max(0, cur_lift - 700)
            lift_max = min(4095, cur_lift + 700)
        except ConnectionError:
            pass

    positions = []
    pan_steps = np.linspace(pan_min, pan_max, grid_cols, dtype=int)
    lift_steps = np.linspace(lift_min, lift_max, grid_rows, dtype=int)

    # Serpentine pattern to minimize travel
    for i, lift in enumerate(lift_steps):
        pans = pan_steps if i % 2 == 0 else pan_steps[::-1]
        for pan in pans:
            positions.append({
                "shoulder_pan": int(pan),
                "shoulder_lift": int(lift),
                "elbow_flex": FIXED_ELBOW,
                "wrist_flex": FIXED_WRIST_FLEX,
                "wrist_roll": FIXED_WRIST_ROLL,
                "gripper": FIXED_GRIPPER,
            })

    return positions


# ── Modes ───────────────────────────────────────────────────────────────────

def run_preview(camera_index: int, hsv_lower: tuple, hsv_upper: tuple) -> None:
    """Camera-only preview: show live feed with marker detection.  Press q to quit."""
    print("Opening camera for preview (press q to quit)...")
    cap = open_camera(camera_index)

    try:
        while True:
            frame = capture_frame(cap)
            point = detect_marker(frame, hsv_lower, hsv_upper)
            display = draw_detection(frame, point, hsv_lower, hsv_upper)

            # Also show the HSV mask in a second window for tuning
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, np.array(hsv_lower), np.array(hsv_upper))
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            mask_color = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)

            cv2.imshow("Visual Calibration — Preview", display)
            cv2.imshow("HSV Mask", mask_color)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


def run_dry_run(grid_rows: int, grid_cols: int) -> None:
    """Print planned positions without moving anything."""
    positions = plan_sweep(None, grid_rows, grid_cols)
    print(f"Planned sweep: {grid_cols}×{grid_rows} = {len(positions)} positions\n")
    print(f"{'#':>4}  {'Pan':>6}  {'Lift':>6}  {'Elbow':>6}  {'WFlex':>6}  {'WRoll':>6}  {'Grip':>6}")
    print(f"{'─'*4}  {'─'*6}  {'─'*6}  {'─'*6}  {'─'*6}  {'─'*6}  {'─'*6}")
    for i, pos in enumerate(positions):
        print(f"{i+1:4d}  {pos['shoulder_pan']:6d}  {pos['shoulder_lift']:6d}  "
              f"{pos['elbow_flex']:6d}  {pos['wrist_flex']:6d}  "
              f"{pos['wrist_roll']:6d}  {pos['gripper']:6d}")
    print(f"\nTotal: {len(positions)} positions")


def run_sweep(port: str, camera_index: int,
              grid_rows: int, grid_cols: int,
              hsv_lower: tuple, hsv_upper: tuple) -> None:
    """Full sweep: move arm through positions, detect marker, save calibration."""
    print(f"Connecting to follower arm on {port}...")
    bus = make_bus(port)

    print(f"Opening camera {camera_index}...")
    cap = open_camera(camera_index)

    positions = plan_sweep(bus, grid_rows, grid_cols)
    total = len(positions)
    print(f"Sweep plan: {grid_cols}×{grid_rows} = {total} positions")

    sweep_data = []  # raw data for debugging
    detected_points = []  # (pixel_xy, joint_angles) for successful detections
    skipped = 0

    try:
        # Enable torque and move to first position gently
        enable_all_torque(bus)
        first = positions[0]
        print("Moving to start position...")
        move_to_position(bus, **first, verbose=True)
        time.sleep(1.0)  # extra settle at start

        for i, pos in enumerate(positions):
            pct = (i + 1) / total * 100
            print(f"[{i+1}/{total}] ({pct:.0f}%) pan={pos['shoulder_pan']} lift={pos['shoulder_lift']}", end="")

            # Command move (non-blocking — joints move simultaneously)
            move_to_position(bus, **pos, verbose=False)

            # Stream camera frames while arm settles
            abort = False
            settle_end = time.time() + SETTLE_TIME
            while time.time() < settle_end:
                frame = capture_frame(cap)
                point = detect_marker(frame, hsv_lower, hsv_upper)
                display = draw_detection(frame, point, hsv_lower, hsv_upper)
                for prev_pt, _ in detected_points:
                    cv2.circle(display, prev_pt, 4, (255, 200, 0), -1)
                cv2.putText(display, f"{i+1}/{total}  skip={skipped}", (10, 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
                cv2.imshow("Visual Calibration — Sweep", display)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    abort = True
                    break

            if abort:
                print("\nSweep aborted by user (q pressed).")
                break

            # Final capture after settling for calibration data
            frame = capture_frame(cap)
            point = detect_marker(frame, hsv_lower, hsv_upper)
            joints = read_all_joints(bus)

            record = {
                "index": i,
                "target": pos,
                "actual_joints": joints,
                "pixel_xy": list(point) if point else None,
            }
            sweep_data.append(record)

            if point is not None:
                detected_points.append((point, joints))
                print(f"  -> pixel ({point[0]}, {point[1]})")
            else:
                skipped += 1
                print(f"  -> SKIP (no marker)")

            # Show final detection
            display = draw_detection(frame, point, hsv_lower, hsv_upper)
            for prev_pt, _ in detected_points[:-1]:
                cv2.circle(display, prev_pt, 4, (255, 200, 0), -1)
            cv2.putText(display, f"{i+1}/{total}  skip={skipped}", (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            cv2.imshow("Visual Calibration — Sweep", display)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                print("\nSweep aborted by user (q pressed).")
                break

        print(f"\nSweep complete: {len(detected_points)} detected, {skipped} skipped")

        # ── Save raw sweep data ─────────────────────────────────────────
        BACKEND_DIR.mkdir(parents=True, exist_ok=True)
        with open(SWEEP_OUT, "w") as f:
            json.dump({"metadata": {
                "grid_cols": grid_cols, "grid_rows": grid_rows,
                "total_positions": total, "detected": len(detected_points),
                "skipped": skipped,
                "hsv_lower": list(hsv_lower), "hsv_upper": list(hsv_upper),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }, "data": sweep_data}, f, indent=2)
        print(f"Raw sweep data saved to {SWEEP_OUT}")

        if len(detected_points) < 4:
            print("ERROR: Too few detections to build calibration.  Check marker/HSV range.")
            return

        # ── Map to grid cells ───────────────────────────────────────────
        # Capture a clean frame with arm out of the way for grid detection
        print("Moving arm out of camera view for grid snapshot...")
        # Move shoulder_lift to its minimum (arm folded down/back)
        _move_joint_to(bus, "shoulder_lift", 800,
                       torque=800, velocity=SWEEP_VELOCITY,
                       acceleration=SWEEP_ACCELERATION, settle_s=2.0, verbose=False)
        time.sleep(1.0)
        grid_frame = capture_frame(cap)

        # Try automatic grid detection
        grid_bounds = detect_grid_bounds(grid_frame)

        if grid_bounds is not None:
            (gx_min, gx_max), (gy_min, gy_max) = grid_bounds
            print(f"Grid detected: x=[{gx_min}, {gx_max}], y=[{gy_min}, {gy_max}]")
        else:
            # Fallback: use the bounding box of all detected marker positions
            print("Grid lines not detected — using marker bounding box as grid extent")
            all_px = [p[0] for p, _ in detected_points]
            all_py = [p[1] for p, _ in detected_points]
            margin = 20
            gx_min = min(all_px) - margin
            gx_max = max(all_px) + margin
            gy_min = min(all_py) - margin
            gy_max = max(all_py) + margin

        grid_x_range = (gx_min, gx_max)
        grid_y_range = (gy_min, gy_max)

        # ── Build GridCalibration ───────────────────────────────────────
        # For each grid cell, find the closest detected point and assign its
        # joint angles.  Multiple detections in the same cell are averaged.
        cell_joints: dict[str, list[list[float]]] = {}
        for (px, py), joints in detected_points:
            cell = pixel_to_grid_cell(px, py, grid_x_range, grid_y_range,
                                      cols=10, rows=12)
            cell_joints.setdefault(cell, []).append(joints)

        calibration_points: dict[str, list[float]] = {}
        for cell, joints_list in cell_joints.items():
            avg = np.mean(joints_list, axis=0).tolist()
            calibration_points[cell] = avg

        calibration_data = {
            "metadata": {
                "method": "visual_auto_calibration",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "grid_cols": grid_cols,
                "grid_rows": grid_rows,
                "detected_positions": len(detected_points),
                "grid_cells_mapped": len(calibration_points),
                "grid_x_range": list(grid_x_range),
                "grid_y_range": list(grid_y_range),
                "hsv_lower": list(hsv_lower),
                "hsv_upper": list(hsv_upper),
            },
            "points": calibration_points,
        }

        with open(CALIBRATION_OUT, "w") as f:
            json.dump(calibration_data, f, indent=2)
        print(f"Calibration saved to {CALIBRATION_OUT}")
        print(f"  {len(calibration_points)} grid cells mapped")

        # ── Overlay visualization ───────────────────────────────────────
        overlay = grid_frame.copy()
        for (px, py), joints in detected_points:
            cell = pixel_to_grid_cell(px, py, grid_x_range, grid_y_range)
            cv2.circle(overlay, (px, py), 5, (0, 255, 0), -1)
            cv2.putText(overlay, cell, (px + 8, py - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

        # Draw grid bounds
        cv2.rectangle(overlay, (gx_min, gy_min), (gx_max, gy_max), (255, 0, 0), 2)

        overlay_path = BACKEND_DIR / "calibration_overlay.jpg"
        cv2.imwrite(str(overlay_path), overlay)
        print(f"Overlay image saved to {overlay_path}")

        cv2.imshow("Calibration Result", overlay)
        print("Press any key to close...")
        cv2.waitKey(0)

    except KeyboardInterrupt:
        print("\nInterrupted! Disabling torque...")
    finally:
        _safe_disable_torque(bus)
        bus.disconnect()
        cap.release()
        cv2.destroyAllWindows()
        print("Arm disconnected, camera released.")


# ── CLI ─────────────────────────────────────────────────────────────────────

def parse_hsv(s: str) -> tuple[int, int, int]:
    parts = [int(x.strip()) for x in s.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("Expected 3 comma-separated integers (H,S,V)")
    return tuple(parts)


def main():
    parser = argparse.ArgumentParser(
        description="Visual auto-calibration: camera-tracked arm sweep",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--preview", action="store_true",
                        help="Camera preview only — check marker detection, no arm movement")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print planned positions without moving")
    parser.add_argument("--port", type=str, default=None,
                        help="Follower arm serial port (auto-detect if omitted)")
    parser.add_argument("--camera", type=int, default=0,
                        help="Camera index (default: 0)")
    parser.add_argument("--grid", type=str, default="10x10",
                        help="Sweep grid as COLSxROWS, e.g. 10x10 (default)")
    parser.add_argument("--hsv-lower", type=parse_hsv,
                        default=DEFAULT_HSV_LOWER,
                        help=f"Marker HSV lower bound (default: {','.join(map(str, DEFAULT_HSV_LOWER))})")
    parser.add_argument("--hsv-upper", type=parse_hsv,
                        default=DEFAULT_HSV_UPPER,
                        help=f"Marker HSV upper bound (default: {','.join(map(str, DEFAULT_HSV_UPPER))})")
    args = parser.parse_args()

    # Parse grid size
    try:
        cols, rows = [int(x) for x in args.grid.split("x")]
    except ValueError:
        parser.error("--grid must be COLSxROWS, e.g. 10x10")

    if args.dry_run:
        run_dry_run(rows, cols)
        return

    if args.preview:
        run_preview(args.camera, args.hsv_lower, args.hsv_upper)
        return

    # Full sweep — need arm port
    port = args.port
    if port is None:
        print("Detecting arms...")
        _, follower_port = detect_ports()
        if follower_port is None:
            print("ERROR: No follower arm detected.  Use --port to specify manually.")
            sys.exit(1)
        port = follower_port

    run_sweep(port, args.camera, rows, cols, args.hsv_lower, args.hsv_upper)


if __name__ == "__main__":
    main()
