#!/usr/bin/env python3
"""Serve live camera feeds from all 3 cameras on a web page."""
import cv2
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import os

CAM_RIGHT = int(os.environ.get("CAMERA_RIGHT_INDEX", 0))
CAM_WRIST = int(os.environ.get("CAMERA_WRIST_INDEX", 1))
CAM_ACROSS = int(os.environ.get("CAMERA_ACROSS_INDEX", 2))

PORT = 8889

frames = {"right": None, "wrist": None, "across": None}
lock = threading.Lock()


def capture_loop(name, idx):
    cap = cv2.VideoCapture(idx)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    if not cap.isOpened():
        print(f"FAIL: {name} (index {idx})")
        return
    print(f"OK: {name} (index {idx})")
    while True:
        ret, frame = cap.read()
        if ret:
            _, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            with lock:
                frames[name] = jpg.tobytes()
        time.sleep(1 / 15)  # ~15 fps refresh


HTML = b"""<!DOCTYPE html>
<html><head><title>Camera Preview</title>
<style>
body { background: #1a1a1a; color: #fff; font-family: sans-serif; margin: 20px; }
h1 { margin-bottom: 10px; }
.grid { display: flex; flex-wrap: wrap; gap: 16px; }
.cam { flex: 1; min-width: 300px; }
.cam h2 { margin: 0 0 4px 0; font-size: 16px; }
.cam img { width: 100%%; border: 2px solid #444; border-radius: 4px; }
</style></head><body>
<h1>3-Camera Preview</h1>
<div class="grid">
  <div class="cam"><h2>Right (index %(right)d)</h2><img id="right" src="/feed/right"></div>
  <div class="cam"><h2>Wrist (index %(wrist)d)</h2><img id="wrist" src="/feed/wrist"></div>
  <div class="cam"><h2>Across (index %(across)d)</h2><img id="across" src="/feed/across"></div>
</div>
<script>
setInterval(() => {
  document.querySelectorAll('.cam img').forEach(img => {
    const src = img.getAttribute('src').split('?')[0];
    img.src = src + '?t=' + Date.now();
  });
}, 200);
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/feed/"):
            name = self.path.split("/feed/")[1].split("?")[0]
            with lock:
                data = frames.get(name)
            if data:
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.write(data)
            else:
                self.send_response(503)
                self.end_headers()
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(HTML % {b"right": CAM_RIGHT, b"wrist": CAM_WRIST, b"across": CAM_ACROSS})

    def write(self, data):
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass  # suppress request logs


for name, idx in [("right", CAM_RIGHT), ("wrist", CAM_WRIST), ("across", CAM_ACROSS)]:
    t = threading.Thread(target=capture_loop, args=(name, idx), daemon=True)
    t.start()

print(f"Camera preview at http://localhost:{PORT}")
print("Ctrl-C to stop")
HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
