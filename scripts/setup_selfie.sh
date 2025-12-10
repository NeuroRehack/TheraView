#!/usr/bin/env bash

set -e

echo "======================================="
echo "  Selfie Bluetooth Remote Setup"
echo "======================================="

echo "Put the 'Selfie' remote into pairing mode and press the button when prompted."
echo "If the remote is already paired, this will refresh the connection."

sudo systemctl enable bluetooth.service >/dev/null 2>&1 || true
sudo systemctl start bluetooth.service

echo "Scanning for the 'Selfie' remote (press the button now)..."

MAC=$(sudo timeout 20 bluetoothctl --timeout 20 scan on | awk '/Selfie/{print $3; exit}')

if [ -z "$MAC" ]; then
    echo "Could not find a device named 'Selfie'. Press the button and run again."
    exit 1
fi

echo "Found device $MAC. Pairing and trusting..."

sudo bluetoothctl << EOF
power on
agent on
default-agent
pair $MAC
trust $MAC
connect $MAC
EOF

echo "Remote connected. It should now trigger recording when you press the button."
