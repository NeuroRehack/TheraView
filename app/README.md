# TheraView Recorder

This repository contains a crash-safe USB camera recorder using GStreamer, plus a helper script to concatenate MKV segments into MP4.

## Structure

- `scripts/theraview_recorder.sh` - main recorder supervisor loop
- `scripts/concat_and_convert.sh` - concatenates MKV chunks and converts to MP4
- `systemd/theraview-camera.service` - systemd unit to run recorder at boot
- `scripts/concat_and_convert.sh` - run manually when you want to merge MKV chunks into MP4
- `scripts/theraview_web.py` - lightweight web UI to view files and trigger concat
- `systemd/theraview-web.service` - systemd unit to run the web UI at boot
- `scripts/setup_theraview.sh` - one-shot setup for dependencies + systemd units
- `scripts/remove_theraview_services.sh` - stops and removes systemd units
- `scripts/setup_hotspot.sh` - configure the Pi as a Wi-Fi hotspot

## Requirements

- Raspberry Pi OS (or another Debian-based distro with systemd).
- USB camera available at `/dev/video0` (or set `CAMERA`).
- Packages: `gstreamer1.0-tools`, `gstreamer1.0-plugins-good`, `gstreamer1.0-plugins-bad`,
  `gstreamer1.0-plugins-ugly`, `gstreamer1.0-libav`, `ffmpeg`, and `network-manager` (for hotspot).

## Setup

1. Clone this repo on the Pi and enter it:

```bash
git clone <repo-url> /home/pi/TheraView
cd /home/pi/TheraView
```

2. Run the one-shot setup helper (installs packages and enables services):

```bash
./scripts/setup_theraview.sh
```

3. (Optional) Configure the Pi as a Wi-Fi hotspot:

```bash
./scripts/setup_hotspot.sh
```

To stop and remove services:

```bash
./scripts/remove_theraview_services.sh
```

## How to use

1. Plug in the camera and ensure it appears as `/dev/video0` (or set `CAMERA`).
2. The recorder service will start automatically and write MKV chunks to `recordings/`.
3. Open the web UI at `http://<pi-ip>:8080` to:
   - View recording status.
   - Trigger concat/convert to MP4.
   - Review and delete MKV chunks once `.checked.mp4` exists.
4. If you want to run concat manually, use `scripts/concat_and_convert.sh` (see below).
5. To view the live feed in VLC, open **Media → Open Network Stream** and enter
   `tcp://<pi-ip>:5000` (or your `STREAM_PORT`). Expect a 5+ second delay due to buffering. The
   web UI also shows the current `tcp://` stream link in the System card.

## Behavior

- The recorder waits for the camera device to exist.
- If the camera is disconnected, GStreamer exits and the supervisor restarts after a short delay.
- Recordings are split into 5-minute MKV segments with continuous numbering.
- Run `scripts/concat_and_convert.sh` manually when you want to merge sequential segments into a single MP4, validate duration with `ffprobe`, and stamp the filename with `.checked.mp4` once validated.
- Use the web UI cleanup section to delete MKV chunks only after verified `.checked.mp4` files match the total MKV duration.

## Web viewer

Start the web viewer service and open `http://<pi-ip>:8080` to view recordings and trigger the concat job. The UI shows the current status and recent log output.

## Manual concatenation (SSH-safe)

If you want the concat job to keep running even if your SSH session disconnects, launch it with `nohup` or inside a `tmux` session:

```bash
nohup /home/pi/TheraView/scripts/concat_and_convert.sh > /home/pi/TheraView/logs/concat_and_convert.log 2>&1 &
```

## Configuration

You can override defaults using environment variables (for systemd, set them in the service file or drop-in overrides):

- `CAMERA` (default `/dev/video0`)
- `OUTDIR` (default `/home/pi/TheraView/recordings`)
- `LOGDIR` (default `/home/pi/TheraView/logs`)
- `RECORD_WIDTH`, `RECORD_HEIGHT`, `FRAMERATE`, `RECORD_BITRATE`, `ROTATE_SECONDS`
- `STREAM_WIDTH`, `STREAM_HEIGHT`, `STREAM_BITRATE`, `STREAM_PORT`

## Hotspot setup

The hotspot script uses NetworkManager (`nmcli`) to create an AP connection. The SSID defaults to
`TheraView_<hostname>`.

```bash
./scripts/setup_hotspot.sh
```

You can override defaults with environment variables like `SSID`, `WPA_PASSPHRASE`, `INTERFACE`,
`HOTSPOT_IP`, and `CONNECTION_NAME`.
