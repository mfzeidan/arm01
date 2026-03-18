#!/bin/bash
# Quick check: are the arms connected via USB?
echo "=== USB Serial Devices ==="
ls /dev/tty.usbmodem* 2>/dev/null || echo "No USB modem devices found"
echo ""
echo "=== All USB Devices ==="
system_profiler SPUSBDataType 2>/dev/null | grep -A 5 "Serial\|Feetech\|CH340\|CP210"
