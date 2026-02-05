# TheraView Recorder

This repository contains a crash-safe USB camera recorder using GStreamer, plus a helper script to concatenate MKV segments into MP4.

## How to use (quick start)

1. **Before anything**, make sure you have VLC installed on your phone or laptop.
2. Turn the Raspberry Pi on and wait ~1 minute for it to boot.
3. Connect to the Pi's hotspot network. It is named:
   - `TheraView_TVA` **or** ends with `TVB`, `TVC`, or `TVD`
4. Hotspot password: `ritaengs`
5. Open the live feed in VLC:
   - Phone: you can use `tva.local:<port>` (mDNS). Some QH laptops do **not** resolve this name.
   - If `tva.local` fails, use the IP address: `10.42.0.1:<port>`
   - Default stream address is `tcp://10.42.0.1:5000` unless `STREAM_PORT` is overridden.
6. Web UI (HTTP):
   - Open `http://10.42.0.1:8080` (or `http://tva.local:8080` if mDNS works) to view recordings and trigger concat.
7. To control start/stop of recording, simply plug in and unplug the USB webcam.
   - **Whenever the webcam light is on, it is both recording and streaming.**

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

## Detailed usage

1. Plug in the camera and ensure it appears as `/dev/video0` (or set `CAMERA`).
2. The recorder service will start automatically and write MKV chunks to `recordings/`.
   - Large MKV files are the recordings, and a new one starts every 5 minutes.
3. Open the web UI at `http://<pi-ip>:8080`.
   - The HTML page is a simple dashboard: it lists files for download, shows live status/logs,
     and provides buttons to run concat/convert or cleanup files.
4. When you are done recording, click **Run concat_and_convert** to concat and convert the MKV
   chunks into an MP4 file. It may take a while—keep an eye on the status.
5. When conversion is done, filenames change. You can download the `_checked.mp4` files.
   - If there is no `_checked` in the filename, something is wrong.
6. After you download and review a `_checked.mp4` and are happy with it, remove the MKV files
   (marked as converted) using the cleanup button.
7. You can also delete **all** files including MP4 files using **Cleanup All Files**, but be careful.
8. If you want to run concat manually, use `scripts/concat_and_convert.sh` (see below).
9. To view the live feed in VLC, open **Media → Open Network Stream** and enter
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
