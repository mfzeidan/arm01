#!/usr/bin/env python3
"""Check firmware versions on all servos."""
import sys
import scservo_sdk as scs

ports = sys.argv[1:] if len(sys.argv) > 1 else ["/dev/tty.usbmodem5AAF2633821", "/dev/tty.usbmodem5B140314811"]
labels = ["Follower", "Leader"] if len(ports) == 2 else ["Arm"] * len(ports)

for port, label in zip(ports, labels):
    ph = scs.PortHandler(port)
    pkt = scs.PacketHandler(0)
    if not ph.openPort():
        print(f"Failed to open {port}")
        continue
    ph.setBaudRate(1_000_000)
    print(f"\n{label} ({port}):")
    for mid in range(1, 7):
        # Firmware major: addr 0, 1 byte; Firmware minor: addr 1, 1 byte
        major, c1, _ = pkt.read1ByteTxRx(ph, mid, 0)
        minor, c2, _ = pkt.read1ByteTxRx(ph, mid, 1)
        model, c3, _ = pkt.read2ByteTxRx(ph, mid, 3)
        if c1 == 0 and c2 == 0:
            print(f"  ID {mid}: firmware v{major}.{minor}  model={model}")
        else:
            print(f"  ID {mid}: read failed")
    ph.closePort()
