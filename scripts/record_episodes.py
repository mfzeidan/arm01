#!/usr/bin/env python3
"""Custom episode recorder for SO-101 sock sorting training data.

Bypasses lerobot-record (which uses the broken teleop_loop that causes
Feetech bus corruption on SO-101). Uses the proven teleop.py approach
for arm control + OpenCV camera capture + saves in a format that
convert_dataset.py converts to LeRobot training format.

Usage:
    python scripts/record_episodes.py --session 1
    python scripts/record_episodes.py --session 2 --resume
    python scripts/record_episodes.py --session 3 --episodes 35

Keyboard controls during recording:
    SPACE   Start/stop recording an episode
    d       Discard the current episode (during recording)
    q       Quit (finishes current episode first)
    h       Home the arm (return to rest position)

Data saved to: data/sock_sorting/raw/episode_NNNN/
    - right.mp4, wrist.mp4, across.mp4  (camera recordings)
    - joints.npy    (joint positions at each timestep)
    - actions.npy   (leader/action positions at each timestep)
    - meta.json     (episode metadata — session, duration, timestamp)
"""
import argparse
import json
import os
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

# ── Session definitions ───────────────────────────────────────────────────
SESSIONS = {
    1: {
        "name": "Basic Pick-and-Place",
        "target_episodes": 40,
        "task": "Pick flat sock, place on empty mat",
        "tips": [
            "One flat sock on mat at a time",
            "Pick from every reachable grid zone (near, far, left, right)",
            "Place on empty mat squares",
            "Mix 4-5 different sock types (thin, thick, sizes)",
            "Vary approach angle and gripper height",
        ],
    },
    2: {
        "name": "Stacking Pairs",
        "target_episodes": 25,
        "task": "Pick sock, place on top of another sock",
        "tips": [
            "Pre-place a 'target' sock at destination before each episode",
            "Pick a matching sock and place ON TOP of the target",
            "Vary target sock state (flat vs slightly bunched)",
            "Different grid positions for the pair",
        ],
    },
    3: {
        "name": "Bunched Socks + Recovery",
        "target_episodes": 35,
        "task": "Pick bunched/folded socks with grasp recovery",
        "tips": [
            "Crumple/fold socks into different shapes before each episode",
            "Include INTENTIONAL failed grasps with re-approach and recovery",
            "Mix in some normal flat picks for variety",
            "Vary bunching: loosely folded, tightly balled, half-folded",
        ],
    },
}

# ── Constants ─────────────────────────────────────────────────────────────
FPS = 30
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
JOINT_IDS = list(range(1, 7))  # Motor IDs 1-6
JOINT_NAMES = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]

# Video codec — mp4v is widely compatible
FOURCC = cv2.VideoWriter_fourcc(*"mp4v")


def load_env():
    """Load .env from backend/.env."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    env_path = os.path.join(project_root, "backend", ".env")
    env = {}
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env


class CameraCapture:
    """Threaded camera capture for a single camera."""

    def __init__(self, name, index):
        self.name = name
        self.index = index
        self.cap = None
        self.frame = None
        self.lock = threading.Lock()
        self.running = False
        self.thread = None

    def start(self):
        self.cap = cv2.VideoCapture(self.index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        self.cap.set(cv2.CAP_PROP_FPS, FPS)

        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open {self.name} camera (index {self.index})")

        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def _capture_loop(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                with self.lock:
                    self.frame = frame
            time.sleep(1 / (FPS * 2))  # Oversample to avoid stale frames

    def get_frame(self):
        with self.lock:
            return self.frame.copy() if self.frame is not None else None

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        if self.cap:
            self.cap.release()


class ArmTeleop:
    """Leader-follower teleoperation using proven direct read/write approach."""

    def __init__(self, follower_port, leader_port):
        self.follower_port = follower_port
        self.leader_port = leader_port
        self.robot = None
        self.teleop = None
        self.ph = None  # follower port handler
        self.pkt = None  # follower packet handler

    def connect(self):
        from lerobot.robots.so_follower.so_follower import SOFollower, SOFollowerRobotConfig
        from lerobot.teleoperators.so_leader.so_leader import SOLeader, SOLeaderTeleopConfig

        self.robot = SOFollower(SOFollowerRobotConfig(port=self.follower_port))
        self.teleop = SOLeader(SOLeaderTeleopConfig(port=self.leader_port))

        self.teleop.connect()
        self.robot.connect()

        import scservo_sdk as scs
        self.ph = self.robot.bus.port_handler
        self.pkt = self.robot.bus.packet_handler

    def step(self):
        """Read leader, send to follower. Returns (action, state) arrays."""
        action = self.teleop.get_action()
        self.robot.send_action(action)

        # Action is what the leader commanded (used as training target)
        action_array = action.squeeze().cpu().numpy() if hasattr(action, 'cpu') else np.array(action)

        # Read follower's actual position (what the arm actually did)
        state = np.zeros(6, dtype=np.float32)
        for i, mid in enumerate(JOINT_IDS):
            pos, comm, _ = self.pkt.readTxRx(self.ph, mid, 56, 2)
            if comm == 0 and len(pos) >= 2:
                state[i] = float(pos[0] | (pos[1] << 8))

        return action_array, state

    def read_state(self):
        """Read current follower joint positions without commanding."""
        state = np.zeros(6, dtype=np.float32)
        for i, mid in enumerate(JOINT_IDS):
            pos, comm, _ = self.pkt.readTxRx(self.ph, mid, 56, 2)
            if comm == 0 and len(pos) >= 2:
                state[i] = float(pos[0] | (pos[1] << 8))
        return state

    def go_home(self, steps=50, delay=0.02):
        """Smoothly return to home position."""
        HOME_POS = {1: 1924, 2: 2050, 3: 3083, 4: 858, 5: 1981, 6: 2088}
        current = {}
        for mid in JOINT_IDS:
            pos, c, _ = self.pkt.readTxRx(self.ph, mid, 56, 2)
            if c == 0 and len(pos) >= 2:
                current[mid] = pos[0] | (pos[1] << 8)
        if len(current) < 6:
            return
        for step in range(1, steps + 1):
            t = step / steps
            for mid in JOINT_IDS:
                target = int(current[mid] + (HOME_POS[mid] - current[mid]) * t)
                self.pkt.writeTxRx(self.ph, mid, 42, 2,
                                   [target & 0xFF, (target >> 8) & 0xFF])
            time.sleep(delay)

    def disconnect(self):
        # Disable torque
        for mid in JOINT_IDS:
            for _ in range(3):
                try:
                    self.pkt.writeTxRx(self.ph, mid, 48, 1, [0])  # Lock = 0
                    self.pkt.writeTxRx(self.ph, mid, 40, 1, [0])  # Torque_Enable = 0
                    break
                except Exception:
                    time.sleep(0.05)
        try:
            self.teleop.disconnect()
        except Exception:
            pass
        try:
            self.robot.disconnect()
        except Exception:
            pass


class EpisodeRecorder:
    """Records a single episode: cameras + joint data."""

    def __init__(self, episode_dir, camera_names):
        self.episode_dir = Path(episode_dir)
        self.episode_dir.mkdir(parents=True, exist_ok=True)
        self.camera_names = camera_names

        # Video writers
        self.writers = {}
        for name in camera_names:
            path = str(self.episode_dir / f"{name}.mp4")
            self.writers[name] = cv2.VideoWriter(path, FOURCC, FPS,
                                                  (CAMERA_WIDTH, CAMERA_HEIGHT))

        self.states = []   # follower positions each frame
        self.actions = []  # leader positions each frame (training target)
        self.timestamps = []
        self.start_time = None
        self.frame_count = 0

    def add_frame(self, camera_frames, action, state):
        """Add one timestep of data."""
        if self.start_time is None:
            self.start_time = time.time()

        for name in self.camera_names:
            frame = camera_frames.get(name)
            if frame is not None:
                self.writers[name].write(frame)

        self.states.append(state.copy())
        self.actions.append(action.copy())
        self.timestamps.append(time.time() - self.start_time)
        self.frame_count += 1

    def save(self, session_num, task_description):
        """Finalize and save episode data."""
        for w in self.writers.values():
            w.release()

        duration = self.timestamps[-1] if self.timestamps else 0

        np.save(str(self.episode_dir / "states.npy"),
                np.array(self.states, dtype=np.float32))
        np.save(str(self.episode_dir / "actions.npy"),
                np.array(self.actions, dtype=np.float32))
        np.save(str(self.episode_dir / "timestamps.npy"),
                np.array(self.timestamps, dtype=np.float64))

        meta = {
            "session": session_num,
            "task": task_description,
            "frames": self.frame_count,
            "duration_s": round(duration, 2),
            "fps": FPS,
            "joint_names": JOINT_NAMES,
            "camera_names": self.camera_names,
            "camera_resolution": [CAMERA_WIDTH, CAMERA_HEIGHT],
            "recorded_at": datetime.now().isoformat(),
        }
        with open(self.episode_dir / "meta.json", "w") as f:
            json.dump(meta, f, indent=2)

        return meta

    def discard(self):
        """Remove all episode data."""
        for w in self.writers.values():
            w.release()
        import shutil
        if self.episode_dir.exists():
            shutil.rmtree(self.episode_dir)


def find_next_episode(data_dir):
    """Find the next episode number."""
    data_path = Path(data_dir)
    if not data_path.exists():
        return 0
    existing = [d.name for d in data_path.iterdir()
                if d.is_dir() and d.name.startswith("episode_")]
    if not existing:
        return 0
    nums = [int(d.split("_")[1]) for d in existing]
    return max(nums) + 1


def print_session_header(session_num, session_info, episode_start, data_dir):
    """Print session info and tips."""
    existing = find_next_episode(data_dir)
    print(f"\n{'=' * 60}")
    print(f"  SESSION {session_num}: {session_info['name']}")
    print(f"  Target: {session_info['target_episodes']} episodes")
    print(f"  Task: {session_info['task']}")
    print(f"  Existing episodes: {existing}")
    print(f"{'=' * 60}")
    print(f"\n  Tips for this session:")
    for tip in session_info["tips"]:
        print(f"    - {tip}")
    print(f"\n  Controls:")
    print(f"    SPACE  Start/stop recording an episode")
    print(f"    d      Discard current episode")
    print(f"    q      Quit")
    print(f"    h      Home the arm")
    print()


def main():
    parser = argparse.ArgumentParser(description="Record training episodes for SO-101")
    parser.add_argument("--session", type=int, choices=[1, 2, 3], default=1,
                        help="Recording session (1=basic, 2=stacking, 3=bunched+recovery)")
    parser.add_argument("--episodes", type=int, default=None,
                        help="Override target episode count")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from last episode number")
    parser.add_argument("--data-dir", default=None,
                        help="Data directory (default: data/sock_sorting/raw)")
    parser.add_argument("--follower-port", default=None)
    parser.add_argument("--leader-port", default=None)
    parser.add_argument("--no-cameras", action="store_true",
                        help="Record without cameras (joint data only, for testing)")
    parser.add_argument("--fps", type=int, default=FPS,
                        help=f"Recording FPS (default: {FPS})")
    args = parser.parse_args()

    # Load config
    env = load_env()
    follower_port = args.follower_port or env.get("FOLLOWER_PORT", "")
    leader_port = args.leader_port or env.get("LEADER_PORT", "")

    if not follower_port or not leader_port:
        print("ERROR: Set FOLLOWER_PORT and LEADER_PORT in backend/.env or pass --follower-port/--leader-port")
        sys.exit(1)

    # Setup data directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    data_dir = args.data_dir or os.path.join(project_root, "data", "sock_sorting", "raw")

    session = SESSIONS[args.session]
    target_eps = args.episodes or session["target_episodes"]
    fps = args.fps

    # Camera setup
    camera_names = ["right", "wrist", "across"]
    cameras = {}

    if not args.no_cameras:
        cam_indices = {
            "right": int(env.get("CAMERA_RIGHT_INDEX", 0)),
            "wrist": int(env.get("CAMERA_WRIST_INDEX", 1)),
            "across": int(env.get("CAMERA_ACROSS_INDEX", 2)),
        }
        print("Starting cameras...")
        for name, idx in cam_indices.items():
            cam = CameraCapture(name, idx)
            try:
                cam.start()
                cameras[name] = cam
                print(f"  {name} camera (index {idx}) — OK")
            except RuntimeError as e:
                print(f"  {name} camera (index {idx}) — FAILED: {e}")
                # Clean up already started cameras
                for c in cameras.values():
                    c.stop()
                sys.exit(1)

        # Let cameras warm up
        time.sleep(1.0)
    else:
        camera_names = []
        print("Running WITHOUT cameras (joint data only)")

    # Arm setup
    print("\nConnecting arms...")
    arm = ArmTeleop(follower_port, leader_port)
    try:
        arm.connect()
        print("  Leader + Follower connected")
    except Exception as e:
        print(f"  ARM CONNECTION FAILED: {e}")
        for cam in cameras.values():
            cam.stop()
        sys.exit(1)

    # Episode tracking
    episode_num = find_next_episode(data_dir) if args.resume else find_next_episode(data_dir)
    episodes_recorded = 0

    print_session_header(args.session, session, episode_num, data_dir)

    # Keyboard state (non-blocking via separate thread)
    key_pressed = {"value": None}
    key_lock = threading.Lock()

    def key_listener():
        """Listen for single keystrokes."""
        import tty
        import termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while True:
                ch = sys.stdin.read(1)
                with key_lock:
                    key_pressed["value"] = ch
                if ch == 'q':
                    break
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    key_thread = threading.Thread(target=key_listener, daemon=True)
    key_thread.start()

    def get_key():
        with key_lock:
            k = key_pressed["value"]
            key_pressed["value"] = None
            return k

    # Signal handling
    quit_flag = False
    def handle_signal(sig, frame):
        nonlocal quit_flag
        quit_flag = True
    signal.signal(signal.SIGINT, handle_signal)

    # Main recording loop
    recording = False
    recorder = None
    loop_errors = 0

    print("Ready. Press SPACE to start recording the first episode.\n")

    try:
        while not quit_flag:
            loop_start = time.perf_counter()

            # Check keyboard
            key = get_key()
            if key == 'q':
                if recording and recorder:
                    print("\nFinishing current episode before quitting...")
                    meta = recorder.save(args.session, session["task"])
                    episodes_recorded += 1
                    episode_num += 1
                    print(f"  Episode saved ({meta['frames']} frames, {meta['duration_s']}s)")
                break

            elif key == ' ':
                if not recording:
                    # Start recording
                    ep_dir = os.path.join(data_dir, f"episode_{episode_num:04d}")
                    recorder = EpisodeRecorder(ep_dir, camera_names)
                    recording = True
                    loop_errors = 0
                    print(f"● RECORDING episode {episode_num:04d}  "
                          f"[{episodes_recorded + 1}/{target_eps}]  "
                          f"(SPACE=stop, d=discard)")
                else:
                    # Stop recording
                    recording = False
                    meta = recorder.save(args.session, session["task"])
                    episodes_recorded += 1
                    episode_num += 1
                    print(f"\n  ✓ Episode saved: {meta['frames']} frames, "
                          f"{meta['duration_s']}s, {meta['frames']/max(meta['duration_s'],0.1):.0f} fps")

                    if episodes_recorded >= target_eps:
                        print(f"\n  Session {args.session} target reached! "
                              f"({episodes_recorded}/{target_eps} episodes)")
                        print("  Press SPACE to continue recording or q to quit.")
                    else:
                        remaining = target_eps - episodes_recorded
                        print(f"  {remaining} episodes remaining. "
                              f"Press SPACE for next episode.")

            elif key == 'd' and recording:
                recording = False
                recorder.discard()
                print(f"\n  ✗ Episode {episode_num:04d} discarded")
                print(f"  Press SPACE to retry.")

            elif key == 'h':
                if not recording:
                    print("  Homing arm...")
                    arm.go_home()
                    time.sleep(1.0)
                    print("  Arm at home position")

            # Teleop step (always running so operator feels the arm)
            try:
                action, state = arm.step()

                if recording and recorder:
                    # Capture camera frames
                    cam_frames = {}
                    for name, cam in cameras.items():
                        frame = cam.get_frame()
                        if frame is not None:
                            cam_frames[name] = frame

                    recorder.add_frame(cam_frames, action, state)

                    # Progress indicator every second
                    if recorder.frame_count % fps == 0:
                        elapsed = recorder.timestamps[-1] if recorder.timestamps else 0
                        sys.stdout.write(f"\r  ● {recorder.frame_count} frames "
                                         f"({elapsed:.0f}s) ")
                        sys.stdout.flush()

                loop_errors = 0
            except Exception as e:
                loop_errors += 1
                if loop_errors >= 10:
                    print(f"\n  FATAL: 10 consecutive teleop errors, last: {e}")
                    break
                time.sleep(0.01)
                continue

            # Rate limit
            elapsed = time.perf_counter() - loop_start
            remaining = max(1.0 / fps - elapsed, 0)
            if remaining > 0:
                time.sleep(remaining)

    finally:
        print("\n\nShutting down...")

        # Stop cameras
        for cam in cameras.values():
            cam.stop()

        # Home and disconnect arm
        print("Returning arm to home position...")
        try:
            arm.go_home()
            time.sleep(1.0)
        except Exception:
            pass
        arm.disconnect()

        # Summary
        print(f"\n{'=' * 60}")
        print(f"  Session {args.session} complete")
        print(f"  Episodes recorded: {episodes_recorded}")
        print(f"  Data saved to: {data_dir}")
        if episodes_recorded > 0:
            print(f"  Next step: python scripts/convert_dataset.py")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
