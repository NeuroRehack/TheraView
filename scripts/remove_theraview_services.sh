#!/bin/bash
set -euo pipefail

SYSTEMD_DIR=${SYSTEMD_DIR:-/etc/systemd/system}

sudo systemctl disable --now theraview-camera.service || true
sudo systemctl disable --now theraview-web.service || true
sudo systemctl disable --now mediamtx.service || true

sudo rm -f "$SYSTEMD_DIR/theraview-camera.service"
sudo rm -f "$SYSTEMD_DIR/theraview-web.service"
sudo rm -f "$SYSTEMD_DIR/mediamtx.service"

sudo systemctl daemon-reload

echo "TheraView services removed."
