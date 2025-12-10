#!/usr/bin/env bash

set -e

echo "======================================="
echo "      TheraView Setup Script"
echo "======================================="

TV_PATH="$(pwd)"
HOSTNAME="$(hostname)"
CONFIG_FILE="./config.conf"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Missing config file: $CONFIG_FILE"
    exit 1
fi

source "$CONFIG_FILE"

# Detect WiFi device
WIFI_IFACE=$(nmcli device | awk '/wifi/ {print $1}' | head -n 1)

echo "[1] Updating system..."
sudo apt update -y
sudo apt upgrade -y

echo "[2] Installing system packages..."
sudo apt install -y \
    python3 python3-pip python3-venv python3-gst-1.0 \
    python3-rpi.gpio python3-evdev \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    network-manager \
    bluez bluetooth pi-bluetooth

echo "[3] Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo "[4] Upgrading pip inside the venv..."
pip install --upgrade pip

echo "[5] Creating recordings directory..."
mkdir -p recordings

# ---------------------
# Systemd setup
# ---------------------

SERVICE_FILE="/etc/systemd/system/theraview.service"

if [ "$ENABLE_SYSTEMD" = "true" ]; then
    echo "[6] Creating systemd service..."

    sudo bash -c "cat > $SERVICE_FILE" << EOF
[Unit]
Description=TheraView Capture Server
After=network.target

[Service]
ExecStart=${TV_PATH}/scripts/theraview
WorkingDirectory=${TV_PATH}
User=${USER}
Restart=always
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable theraview.service
    sudo systemctl restart theraview.service

    echo "Systemd service active."

else
    echo "[6] Systemd disabled. Checking for existing service..."

    if [ -f "$SERVICE_FILE" ]; then
        echo "Service found. Removing it."
        sudo systemctl stop theraview.service 2>/dev/null || true
        sudo systemctl disable theraview.service 2>/dev/null || true
        sudo rm -f "$SERVICE_FILE"
        sudo systemctl daemon-reload
        echo "Systemd service removed."
    else
        echo "No service found."
    fi
fi

# ---------------------
# Hotspot setup
# ---------------------
THERA_NET="TheraView"
PRECONFIGURED_NET="preconfigured"

if [ "$ENABLE_HOTSPOT" = "true" ]; then
    echo "[7] Hotspot enabled."

    sudo nmcli device wifi rescan

    if [ "$HOSTNAME" = "TVA" ]; then
        echo "TVA detected. Creating hotspot."

        sudo nmcli connection delete "$THERA_NET" 2>/dev/null || true

        sudo nmcli connection add type wifi ifname "$WIFI_IFACE" \
            con-name "$THERA_NET" autoconnect yes ssid "$THERA_NET"

        sudo nmcli connection modify "$THERA_NET" wifi.mode ap
        sudo nmcli connection modify "$THERA_NET" wifi.band bg
        sudo nmcli connection modify "$THERA_NET" wifi.channel 6
        sudo nmcli connection modify "$THERA_NET" wifi-sec.key-mgmt wpa-psk
        sudo nmcli connection modify "$THERA_NET" wifi-sec.psk "ritaengs"

        sudo nmcli connection modify "$THERA_NET" ipv4.method manual
        sudo nmcli connection modify "$THERA_NET" ipv4.addresses "10.10.10.1/24"
        sudo nmcli connection modify "$THERA_NET" ipv4.gateway ""
        sudo nmcli connection modify "$THERA_NET" ipv4.dns "8.8.8.8 1.1.1.1"

        sudo nmcli connection up "$THERA_NET"

    elif [ "$HOSTNAME" = "TVB" ]; then
        echo "TVB detected. Setting up hotspot client."

        sudo nmcli connection delete "$THERA_NET" 2>/dev/null || true

        sudo nmcli connection add type wifi ifname "$WIFI_IFACE" \
            con-name "$THERA_NET" ssid "$THERA_NET" \
            wifi-sec.key-mgmt wpa-psk wifi-sec.psk "ritaengs" autoconnect yes

        sudo nmcli connection modify "$THERA_NET" ipv4.method manual
        sudo nmcli connection modify "$THERA_NET" ipv4.addresses "10.10.10.2/24"
        sudo nmcli connection modify "$THERA_NET" ipv4.gateway "10.10.10.1"
        sudo nmcli connection modify "$THERA_NET" ipv4.dns "8.8.8.8 1.1.1.1"

        sudo nmcli connection up "$THERA_NET" || true
    fi

else
    echo "[7] Hotspot disabled. Removing hotspot profiles if present."

    if sudo nmcli connection show | grep -q "$THERA_NET"; then
        echo "Removing TheraView connection."
        sudo nmcli connection delete "$THERA_NET" 2>/dev/null || true
    fi

    sudo nmcli device wifi rescan

    if sudo nmcli device wifi list | grep -q "$PRECONFIGURED_NET"; then
        echo "Preconfigured network found. Connecting."
        sudo nmcli connection up "$PRECONFIGURED_NET" || true
    else
        echo "Preconfigured network not found."
    fi
fi

echo ""
echo "======================================="
echo "      TheraView setup complete"
echo "======================================="

