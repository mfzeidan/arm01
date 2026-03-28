#!/usr/bin/env python3
"""Scan a servo bus and test sync_read under various conditions."""
import sys
import time
import scservo_sdk as scs

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/tty.usbmodem5AAF2633821"
BAUDRATE = 1_000_000

port_handler = scs.PortHandler(PORT)
packet_handler = scs.PacketHandler(0)  # protocol 0 for Feetech

if not port_handler.openPort():
    print(f"Failed to open port {PORT}")
    sys.exit(1)

port_handler.setBaudRate(BAUDRATE)

print(f"Scanning port {PORT} at {BAUDRATE} baud...\n")

for motor_id in range(1, 7):
    model, comm, error = packet_handler.ping(port_handler, motor_id)
    if comm == 0:
        pos, comm2, err2 = packet_handler.read2ByteTxRx(port_handler, motor_id, 56)
        volt, comm3, err3 = packet_handler.read1ByteTxRx(port_handler, motor_id, 62)
        delay, comm4, err4 = packet_handler.read1ByteTxRx(port_handler, motor_id, 7)  # Return_Delay_Time
        volt_str = f"{volt/10:.1f}V" if comm3 == 0 else "?"
        pos_str = str(pos) if comm2 == 0 else "?"
        delay_str = str(delay) if comm4 == 0 else "?"
        print(f"  ID {motor_id}: FOUND  model={model}  pos={pos_str}  voltage={volt_str}  return_delay={delay_str}")
    else:
        print(f"  ID {motor_id}: NOT FOUND  ({packet_handler.getTxRxResult(comm)})")


def test_sync_read(label):
    print(f"\n{label}")
    gr = scs.GroupSyncRead(port_handler, packet_handler, 56, 2)
    for mid in range(1, 7):
        gr.addParam(mid)
    for attempt in range(3):
        time.sleep(0.05)
        comm = gr.txRxPacket()
        if comm == 0:
            positions = {}
            for mid in range(1, 7):
                if gr.isAvailable(mid, 56, 2):
                    positions[mid] = gr.getData(mid, 56, 2)
                else:
                    positions[mid] = "N/A"
            print(f"  Attempt {attempt+1}: SUCCESS  positions={positions}")
        else:
            print(f"  Attempt {attempt+1}: FAILED  ({packet_handler.getTxRxResult(comm)})")
    gr.clearParam()


# Test 1: sync_read with current settings
test_sync_read("Test 1: sync_read with current Return_Delay_Time...")

# Test 2: Set Return_Delay_Time to 0 (what LeRobot configure_motors does)
print("\nSetting Return_Delay_Time=0 on all motors (like LeRobot does)...")
for motor_id in range(1, 7):
    # Must disable torque to write EEPROM
    packet_handler.write1ByteTxRx(port_handler, motor_id, 40, 0)
    time.sleep(0.01)
    packet_handler.write1ByteTxRx(port_handler, motor_id, 7, 0)
    time.sleep(0.01)

test_sync_read("Test 2: sync_read with Return_Delay_Time=0...")

# Test 3: Enable torque with Return_Delay_Time=0
print("\nEnabling torque with Return_Delay_Time=0...")
for motor_id in range(1, 7):
    packet_handler.write1ByteTxRx(port_handler, motor_id, 40, 1)
    time.sleep(0.2)

test_sync_read("Test 3: sync_read with torque ON + Return_Delay_Time=0...")

# Cleanup: disable torque, restore Return_Delay_Time
print("\nCleaning up: disabling torque, restoring Return_Delay_Time=250...")
for motor_id in range(1, 7):
    packet_handler.write1ByteTxRx(port_handler, motor_id, 40, 0)
    time.sleep(0.01)
    packet_handler.write1ByteTxRx(port_handler, motor_id, 7, 250)
    time.sleep(0.01)

port_handler.closePort()
print("\nDone.")
