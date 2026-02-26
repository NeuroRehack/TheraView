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
  ffmpeg \
  curl \
  tar

if ! command -v mediamtx >/dev/null 2>&1; then
  tmpdir=$(mktemp -d)
  arch=$(uname -m)
  case "$arch" in
    aarch64|arm64) mediamtx_arch="linux_arm64" ;;
    armv7l|armv6l|armhf) mediamtx_arch="linux_armv7" ;;
    x86_64|amd64) mediamtx_arch="linux_amd64" ;;
    *)
      echo "Unsupported architecture for MediaMTX install: $arch" >&2
      exit 1
      ;;
  esac
  mediamtx_url="https://github.com/bluenviron/mediamtx/releases/latest/download/mediamtx_${mediamtx_arch}.tar.gz"
  curl -fsSL "$mediamtx_url" -o "$tmpdir/mediamtx.tar.gz"
  tar -xzf "$tmpdir/mediamtx.tar.gz" -C "$tmpdir"
  sudo install -m 0755 "$tmpdir/mediamtx" /usr/local/bin/mediamtx
  rm -rf "$tmpdir"
fi

mkdir -p "$REPO_DIR/recordings" "$REPO_DIR/logs"
mkdir -p "$REPO_DIR/config"
chmod +x "$REPO_DIR/scripts/theraview_recorder.sh" \
  "$REPO_DIR/scripts/concat_and_convert.sh" \
  "$REPO_DIR/scripts/theraview_web.py" \
  "$REPO_DIR/scripts/setup_theraview.sh" \
  "$REPO_DIR/scripts/remove_theraview_services.sh" \
  "$REPO_DIR/scripts/setup_hotspot.sh"

sudo cp "$REPO_DIR/systemd/theraview-camera.service" "$SYSTEMD_DIR/"
sudo cp "$REPO_DIR/systemd/theraview-web.service" "$SYSTEMD_DIR/"
sudo cp "$REPO_DIR/systemd/mediamtx.service" "$SYSTEMD_DIR/"

sudo systemctl daemon-reload
sudo systemctl enable --now mediamtx.service
sudo systemctl enable --now theraview-camera.service
sudo systemctl enable --now theraview-web.service

echo "TheraView setup complete."
