#!/bin/bash
set -euo pipefail

INTERFACE=${INTERFACE:-wlan0}
HOSTNAME=$(hostname)
SSID=${SSID:-TheraView_${HOSTNAME}}
WPA_PASSPHRASE=${WPA_PASSPHRASE:-theraview1234}
HOTSPOT_IP=${HOTSPOT_IP:-192.168.50.1}
CHANNEL=${CHANNEL:-7}
CONNECTION_NAME=${CONNECTION_NAME:-theraview-hotspot}

if [[ ${#WPA_PASSPHRASE} -lt 8 ]]; then
  echo "WPA_PASSPHRASE must be at least 8 characters." >&2
  exit 1
fi

sudo apt-get update
sudo apt-get install -y network-manager

sudo systemctl enable --now NetworkManager

if nmcli -t -f NAME connection show | grep -qx "${CONNECTION_NAME}"; then
  sudo nmcli connection delete "${CONNECTION_NAME}"
fi

sudo nmcli connection add type wifi ifname "${INTERFACE}" con-name "${CONNECTION_NAME}" autoconnect yes ssid "${SSID}"
sudo nmcli connection modify "${CONNECTION_NAME}" \
  802-11-wireless.mode ap \
  802-11-wireless.band bg \
  802-11-wireless.channel "${CHANNEL}" \
  ipv4.method shared \
  ipv4.addresses "${HOTSPOT_IP}/24" \
  wifi-sec.key-mgmt wpa-psk \
  wifi-sec.psk "${WPA_PASSPHRASE}"

sudo nmcli connection up "${CONNECTION_NAME}"

echo "Hotspot configured via NetworkManager: SSID ${SSID} on ${INTERFACE} (${HOTSPOT_IP})."
