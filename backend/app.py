"""Sock sorting coordinator: camera -> Claude Vision API -> arm commands."""

import base64
import json
import logging
import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from calibration import GridCalibration

load_dotenv(Path(__file__).parent / ".env")

DRY_RUN = os.getenv("DRY_RUN", "true").lower() in ("true", "1", "yes")

log = logging.getLogger("coordinator")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

# ---------------------------------------------------------------------------
# Tool definitions for Claude
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "capture_workspace",
        "description": (
            "Take a photo of the workspace from the top-down camera. "
            "Returns the current camera image so you can see all socks "
            "and grid coordinates on the mat."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "move_to",
        "description": (
            "Move the robot gripper above a grid coordinate on the mat. "
            "The gripper will hover above the position, ready to pick or place."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "coord": {
                    "type": "string",
                    "description": "Grid coordinate, e.g. 'B3', 'D5', 'J2'",
                }
            },
            "required": ["coord"],
        },
    },
    {
        "name": "pick",
        "description": (
            "Lower the gripper, close it to grasp the sock, and lift. "
            "Call move_to first to position above the target sock."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "place",
        "description": (
            "Lower the gripper, open it to release the sock, and lift. "
            "Call move_to first to position above the target location."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "home",
        "description": "Return the arm to its home position, out of the way of the camera.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "done",
        "description": (
            "Signal that sorting is complete. Call this when all visible sock "
            "pairs have been matched and placed, or when no more pairs can be found."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Brief summary of what was sorted (pairs matched, any issues).",
                }
            },
            "required": ["summary"],
        },
    },
]

SYSTEM_PROMPT = """\
You are a sock sorting robot controller. You can see the workspace through a \
top-down camera and command a robot arm to pick and place socks.

The workspace has a grid mat with chess-style coordinates (letters across the \
top: A, B, C, ... and numbers down the side: 1, 2, 3, ...).

Your job:
1. Call capture_workspace to see the current state
2. Identify all socks and determine which ones are matching pairs (by color, \
pattern, size)
3. For each matching pair, pick one sock and place it on top of its match
4. Work systematically - identify all pairs first, then sort them one at a time
5. After each pick-and-place, capture again to verify success
6. If a grasp fails (sock not picked up), retry once then move on

Call done with a summary when you have sorted all visible pairs.\
"""

# ---------------------------------------------------------------------------
# Hardware interface (stubs — wire to real hardware later)
# ---------------------------------------------------------------------------


class Camera:
    """OpenCV camera capture."""

    def __init__(self, index: int = 0, dry_run: bool = False, test_image: str | None = None):
        self.index = index
        self.dry_run = dry_run
        self.test_image = test_image  # Path to a static image for testing
        self.cap = None

    def open(self):
        if self.dry_run:
            log.info("[CAM] Dry run — skipping camera open")
            return
        import cv2
        self.cap = cv2.VideoCapture(self.index)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open camera {self.index}")

    def capture_base64_jpeg(self) -> str:
        """Capture a frame and return as base64-encoded JPEG."""
        if self.test_image:
            log.info(f"[CAM] Using test image: {self.test_image}")
            return self._load_and_resize_image(self.test_image)
        if self.dry_run:
            log.info("[CAM] Dry run — returning placeholder image")
            return base64.standard_b64encode(self._placeholder_jpeg()).decode("utf-8")
        import cv2
        if self.cap is None:
            self.open()
        ret, frame = self.cap.read()
        if not ret:
            raise RuntimeError("Failed to capture frame")
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return base64.standard_b64encode(buf).decode("utf-8")

    @staticmethod
    def _load_and_resize_image(path: str, max_bytes: int = 4_000_000) -> str:
        """Load an image, resize if needed to stay under API size limit."""
        from PIL import Image
        import io
        img = Image.open(path)
        quality = 85
        while quality >= 20:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality)
            data = buf.getvalue()
            if len(data) <= max_bytes:
                return base64.standard_b64encode(data).decode("utf-8")
            quality -= 10
        # Last resort: resize down
        img = img.resize((img.width // 2, img.height // 2))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return base64.standard_b64encode(buf.getvalue()).decode("utf-8")

    @staticmethod
    def _placeholder_jpeg() -> bytes:
        """Minimal valid JPEG for dry-run mode."""
        import numpy as np
        try:
            import cv2
            img = np.zeros((480, 640, 3), dtype=np.uint8)
            _, buf = cv2.imencode(".jpg", img)
            return buf.tobytes()
        except ImportError:
            # If cv2 not available, return a tiny valid JPEG
            from PIL import Image
            import io
            img = Image.new("RGB", (640, 480), (0, 0, 0))
            buf = io.BytesIO()
            img.save(buf, format="JPEG")
            return buf.getvalue()

    def close(self):
        if self.cap:
            self.cap.release()


class Arm:
    """Robot arm control via LeRobot. Stubbed for now."""

    def __init__(self, port: str, calibration: GridCalibration, dry_run: bool = False):
        self.port = port
        self.calibration = calibration
        self.dry_run = dry_run
        self.robot = None  # Will be a LeRobot SO101Follower instance

    def connect(self):
        if self.dry_run:
            log.info("[ARM] Dry run — skipping arm connect")
            return
        # TODO: Initialize LeRobot SO101Follower
        # from lerobot.common.robots.so101_follower import SO101Follower
        # self.robot = SO101Follower(port=self.port)
        # self.robot.connect()
        log.info(f"[ARM] Connected on {self.port}")

    def move_to(self, coord: str):
        """Move gripper above a grid coordinate."""
        if self.dry_run:
            log.info(f"[ARM] move_to {coord} (dry run — no calibration lookup)")
            return
        joint_angles = self.calibration.get_joint_angles(coord)
        log.info(f"[ARM] move_to {coord} -> joints {joint_angles}")
        # TODO: self.robot.send_action({"shoulder_pan.pos": joint_angles[0], ...})

    def pick(self):
        """Lower gripper, close, lift."""
        log.info("[ARM] pick (lower -> close gripper -> lift)")
        # TODO: Execute pick sequence

    def place(self):
        """Lower gripper, open, lift."""
        log.info("[ARM] place (lower -> open gripper -> lift)")
        # TODO: Execute place sequence

    def home(self):
        """Return to home position."""
        log.info("[ARM] home")
        # TODO: Move to predefined home joint angles

    def disconnect(self):
        if self.robot:
            self.robot.disconnect()


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------


def execute_tool(tool_name: str, tool_input: dict, camera: Camera, arm: Arm) -> dict:
    """Execute a tool call and return the result."""
    if tool_name == "capture_workspace":
        image_b64 = camera.capture_base64_jpeg()
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": image_b64,
            },
        }

    elif tool_name == "move_to":
        coord = tool_input["coord"]
        arm.move_to(coord)
        return {"type": "text", "text": f"Moved to {coord}"}

    elif tool_name == "pick":
        arm.pick()
        return {"type": "text", "text": "Pick executed"}

    elif tool_name == "place":
        arm.place()
        return {"type": "text", "text": "Place executed"}

    elif tool_name == "home":
        arm.home()
        return {"type": "text", "text": "Arm returned to home position"}

    elif tool_name == "done":
        arm.home()
        return {"type": "text", "text": "Sort complete. Arm returned to home."}

    else:
        return {"type": "text", "text": f"Unknown tool: {tool_name}"}


# ---------------------------------------------------------------------------
# Main sorting loop
# ---------------------------------------------------------------------------


def run_sort(camera: Camera, arm: Arm):
    """Run the sock sorting loop with Claude as the brain."""
    client = anthropic.Anthropic()

    messages = [{
        "role": "user",
        "content": (
            "Please sort the socks on the workspace. Start by capturing an image "
            "to see what's there."
        ),
    }]

    log.info("=== Starting sock sort ===")

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        assistant_content = response.content
        messages.append({"role": "assistant", "content": assistant_content})

        # Check if Claude ended without tool calls
        if response.stop_reason == "end_turn":
            for block in assistant_content:
                if hasattr(block, "text"):
                    log.info(f"[CLAUDE] {block.text}")
            log.info("=== Sort complete ===")
            break

        # Process tool calls
        tool_results = []
        sort_done = False
        for block in assistant_content:
            if block.type == "tool_use":
                log.info(f"[CLAUDE] {block.name}({json.dumps(block.input)})")
                result = execute_tool(block.name, block.input, camera, arm)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": [result],
                })
                if block.name == "done":
                    log.info(f"[DONE] {block.input.get('summary', '')}")
                    sort_done = True
            elif hasattr(block, "text") and block.text:
                log.info(f"[CLAUDE] {block.text}")

        messages.append({"role": "user", "content": tool_results})

        if sort_done:
            log.info("=== Sort complete ===")
            break


def main():
    import sys

    cam_index = int(os.getenv("CAMERA_TOP_INDEX", "0"))
    follower_port = os.getenv("FOLLOWER_PORT", "/dev/tty.usbmodemXXXXX")
    test_image = sys.argv[1] if len(sys.argv) > 1 else None

    log.info(f"DRY_RUN={DRY_RUN}")
    if test_image:
        log.info(f"Using test image: {test_image}")

    calibration = GridCalibration()
    if not calibration.is_calibrated:
        log.warning("Grid calibration not found. Run calibration first.")

    camera = Camera(index=cam_index, dry_run=DRY_RUN, test_image=test_image)
    arm = Arm(port=follower_port, calibration=calibration, dry_run=DRY_RUN)

    try:
        camera.open()
        arm.connect()
        run_sort(camera, arm)
    except KeyboardInterrupt:
        log.info("Interrupted by user")
    finally:
        arm.home()
        arm.disconnect()
        camera.close()


if __name__ == "__main__":
    main()
