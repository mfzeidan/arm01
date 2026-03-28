#!/usr/bin/env python3
"""Show live servo positions. Move joints to ~2048 before calibration."""
import sys
import time
import scservo_sdk as scs

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/tty.usbmodem5B140314811"

ph = scs.PortHandler(PORT)
pkt = scs.PacketHandler(0)
ph.openPort()
ph.setBaudRate(1_000_000)

names = ['pan', 'lift', 'elbow', 'wflex', 'wroll', 'grip']
print(f"Port: {PORT}")
print("Move all joints to ~2048 before calibration. Ctrl-C when done.\n")

try:
    while True:
        parts = []
        for mid in range(1, 7):
            try:
                pos, c, e = pkt.read2ByteTxRx(ph, mid, 56)
                if c != 0:
                    parts.append(f"{names[mid-1]}= err ")
                    continue
                ok = ' ok ' if abs(pos - 2048) <= 2047 else ' BAD'
                parts.append(f"{names[mid-1]}={pos:5d}{ok}")
            except Exception:
                parts.append(f"{names[mid-1]}= err ")
        print("  ".join(parts), end="\r")
        time.sleep(0.2)
except KeyboardInterrupt:
    print()

ph.closePort()
