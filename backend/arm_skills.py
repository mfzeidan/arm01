"""SO-101 arm movement skills for sock sorting.

Calibrated positions from manual range-finding (2026-03-25/26).
All positions are raw encoder values, no homing offsets.
Goal_Velocity=0 = max speed on STS3215.

Key positions:
    HOME:     Arm collapsed/parked, gripper closed
    TABLE:    Gripper at table level, ready to grab (forward of arm)
    VERTICAL: Arm pointing straight up — safe transit position

Movement pattern for pick-and-place:
    home -> open gripper -> lower to table -> grab -> lift to vertical
    -> rotate to new position -> lower to table -> release -> lift to vertical
    -> rotate back -> home

Camera mount is 3 inches to the right — pan MAX capped at 3100.
"""

import time
import scservo_sdk as scs

# ── Motor IDs ──────────────────────────────────────────────────────────────
PAN, LIFT, ELBOW, WRIST, ROLL, GRIP = 1, 2, 3, 4, 5, 6

# ── Key positions (raw encoder) ───────────────────────────────────────────
HOME = {PAN: 2017, LIFT: 803, ELBOW: 3190, WRIST: 4067, ROLL: 2038, GRIP: 913}
TABLE = {LIFT: 2481, ELBOW: 1786, WRIST: 4300}  # bottom jaw flat on table as backstop
VERTICAL = {LIFT: 2056, ELBOW: 1360, WRIST: 3140}  # no PAN — preserves current rotation
# HOVER: just above the table — same approach angle as TABLE but a bit higher
# This ensures consistent grab angle regardless of where we transit from
HOVER = {LIFT: 2300, ELBOW: 1786, WRIST: 4300}  # same angle as TABLE, just higher
GRIP_OPEN = 2200
GRIP_CLOSED = 899

# ── Safe pan limits ────────────────────────────────────────────────────────
PAN_MIN = 708      # full left
PAN_MAX = 3100     # right (camera mount limit)
PAN_CENTER = 2017  # home/center


# ── Low-level helpers ──────────────────────────────────────────────────────

class Arm:
    def __init__(self, port_path: str = None):
        self.port = None
        self.ph = None
        self.port_path = port_path

    def connect(self, port_path: str = None):
        import glob
        path = port_path or self.port_path
        if path is None:
            ports = sorted(glob.glob("/dev/tty.usbmodem*"))
            if not ports:
                raise RuntimeError("No arm found")
            path = ports[0]
        self.port_path = path
        self.port = scs.PortHandler(path)
        self.port.openPort()
        self.port.setBaudRate(1000000)
        self.ph = scs.PacketHandler(0)

        # Setup motors: unlock, clear offsets/limits, max torque
        for mid in range(1, 7):
            self._w8(mid, 55, 0)   # unlock
            self._w8(mid, 40, 0)   # torque off
            self._w16(mid, 19, 0)  # offset = 0
            self._w16(mid, 9, 0)   # min pos = 0
            self._w16(mid, 11, 4095)  # max pos = 4095
            self._w16(mid, 16, 1000)  # max torque
            time.sleep(0.05)
        time.sleep(0.3)

        # Enable torque at current position, max speed
        for mid in range(1, 7):
            cur = self._r16(mid, 56)
            self._w16(mid, 42, cur)
            self._w16(mid, 48, 700)
            self._w8(mid, 41, 15)
            self._w16(mid, 46, 0)   # max speed!
            self._w8(mid, 40, 1)
            time.sleep(0.05)
        time.sleep(0.3)
        print(f"Arm connected on {path}")

    def disconnect(self):
        for mid in range(1, 7):
            self._w8(mid, 40, 0)
            time.sleep(0.03)
        self.port.closePort()
        print("Arm disconnected.")

    def _r16(self, mid, addr):
        for _ in range(8):
            data, comm, _ = self.ph.readTxRx(self.port, mid, addr, 2)
            if comm == 0 and len(data) >= 2:
                return data[0] | (data[1] << 8)
            time.sleep(0.05)
        return 0

    def _w16(self, mid, addr, val):
        val = max(0, min(4095, int(val)))
        self.ph.writeTxRx(self.port, mid, addr, 2, [val & 0xFF, (val >> 8) & 0xFF])
        time.sleep(0.01)

    def _w8(self, mid, addr, val):
        self.ph.writeTxRx(self.port, mid, addr, 1, [val & 0xFF])
        time.sleep(0.01)

    def read_position(self, mid):
        return self._r16(mid, 56)

    def move(self, positions: dict, duration: float = 2.0):
        """Move joints to target positions. Only moves joints specified — others hold."""
        for mid, val in positions.items():
            self._w16(mid, 42, val)
        time.sleep(duration)

    # ── Skills ─────────────────────────────────────────────────────────────

    def home(self):
        """Return to collapsed/parked position."""
        self.move(HOME, 2.5)

    def open_gripper(self):
        """Open gripper to grab a sock."""
        self.move({GRIP: GRIP_OPEN}, 0.8)

    def close_gripper(self):
        """Close gripper to hold a sock. Slow and firm."""
        self.move({GRIP: GRIP_CLOSED}, 2.0)

    def go_to_table(self):
        """Lower gripper to table level. Preserves current pan rotation."""
        self.move(TABLE, 2.5)

    def go_to_hover(self):
        """Move to hover position just above table. Same approach angle as table grab.
        Call this before go_to_table for consistent grab angle."""
        self.move(HOVER, 2.0)

    def go_to_vertical(self):
        """Lift arm to vertical (safe transit). Preserves current pan rotation."""
        self.move(VERTICAL, 2.5)

    def rotate_to(self, pan_value: int):
        """Rotate base to a pan position. Only call when arm is in VERTICAL."""
        pan_value = max(PAN_MIN, min(PAN_MAX, pan_value))
        self.move({PAN: pan_value}, 2.0)

    def pick(self):
        """Pick up a sock at the current pan position.

        Sequence: open gripper -> hover -> lower to table -> close gripper -> lift to vertical
        """
        self.open_gripper()
        self.go_to_hover()
        self.go_to_table()
        time.sleep(0.5)  # settle before grabbing
        self.close_gripper()
        time.sleep(0.5)  # hold firm before lifting
        self.go_to_vertical()

    def place(self):
        """Place a sock at the current pan position.

        Drops from hover height (couple inches above table) to avoid
        disturbing already-sorted socks.

        Sequence: hover -> open gripper (drop) -> lift to vertical
        """
        self.go_to_hover()
        self.open_gripper()
        self.go_to_vertical()

    def pick_and_place(self, pick_pan: int, place_pan: int):
        """Full pick-and-place: pick sock at one position, place at another.

        Sequence:
            1. Lift to vertical (safe transit)
            2. Rotate to pick position
            3. Pick (lower, grab, lift)
            4. Rotate to place position (sock is high in the air)
            5. Place (lower, release, lift)
            6. Rotate back to center
            7. Home
        """
        pick_pan = max(PAN_MIN, min(PAN_MAX, pick_pan))
        place_pan = max(PAN_MIN, min(PAN_MAX, place_pan))

        print(f"  Pick at pan={pick_pan}, place at pan={place_pan}")

        self.go_to_vertical()
        self.rotate_to(pick_pan)
        self.pick()
        self.rotate_to(place_pan)
        self.place()
        self.rotate_to(PAN_CENTER)
        self.home()


if __name__ == "__main__":
    arm = Arm()
    arm.connect()
    try:
        print("Pick and place: center -> left")
        arm.pick_and_place(PAN_CENTER, 1400)
        print("Done!")
    except KeyboardInterrupt:
        print("Interrupted!")
    finally:
        arm.disconnect()
