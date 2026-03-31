#!/usr/bin/env python3
"""Test all 3 cameras — verify they open and capture a frame."""
import cv2
import sys
import os

cameras = {
    "right": int(os.environ.get("CAMERA_RIGHT_INDEX", 0)),
    "wrist": int(os.environ.get("CAMERA_WRIST_INDEX", 1)),
    "across": int(os.environ.get("CAMERA_ACROSS_INDEX", 2)),
}

ok = True
for name, idx in cameras.items():
    cap = cv2.VideoCapture(idx)
    if not cap.isOpened():
        print(f"  FAIL: {name} (index {idx}) — could not open")
        ok = False
        continue
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    ret, frame = cap.read()
    if not ret or frame is None:
        print(f"  FAIL: {name} (index {idx}) — opened but no frame")
        ok = False
    else:
        h, w = frame.shape[:2]
        path = f"/tmp/cam_{name}.jpg"
        cv2.imwrite(path, frame)
        print(f"  OK:   {name} (index {idx}) — {w}x{h}, saved to {path}")
    cap.release()

if ok:
    print("\nAll 3 cameras working. Check /tmp/cam_*.jpg to verify each view.")
else:
    print("\nSome cameras failed. Try different indices or check USB connections.")
    sys.exit(1)
