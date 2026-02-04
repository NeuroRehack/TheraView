#!/bin/bash
set -euo pipefail

REPO_DIR=${REPO_DIR:-/home/pi/TheraView}
SYSTEMD_DIR=${SYSTEMD_DIR:-/etc/systemd/system}

if [[ ! -d "$REPO_DIR" ]]; then
  echo "Expected repo at $REPO_DIR. Set REPO_DIR to override." >&2
  exit 1
fi

sudo apt-get update
sudo apt-get install -y \
  gstreamer1.0-tools \
  gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad \
  gstreamer1.0-plugins-ugly \
  gstreamer1.0-libav \
  ffmpeg

mkdir -p "$REPO_DIR/recordings" "$REPO_DIR/logs"
chmod +x "$REPO_DIR/scripts/theraview_recorder.sh" \
  "$REPO_DIR/scripts/concat_and_convert.sh" \
  "$REPO_DIR/scripts/theraview_web.py" \
  "$REPO_DIR/scripts/setup_theraview.sh" \
  "$REPO_DIR/scripts/remove_theraview_services.sh" \
  "$REPO_DIR/scripts/setup_hotspot.sh"

sudo cp "$REPO_DIR/systemd/theraview-camera.service" "$SYSTEMD_DIR/"
sudo cp "$REPO_DIR/systemd/theraview-web.service" "$SYSTEMD_DIR/"

sudo systemctl daemon-reload
sudo systemctl enable --now theraview-camera.service
sudo systemctl enable --now theraview-web.service

echo "TheraView setup complete."
