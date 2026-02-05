# TheraView Recorder

This repository contains a crash-safe USB camera recorder using GStreamer, plus a helper script to concatenate MKV segments into MP4.

## How to use (quick start)
1. **Before anything**, make sure VLC is installed on your phone or laptop.

2. Turn on the Raspberry Pi and wait approximately **1 minute** for it to fully boot.

3. Once the camera is connected, recording and streaming will start automatically. You can confirm this by checking the **blue LED** on the camera.

4. Connect to the Pi’s hotspot network. It will be named:
   - `TheraView_TVA` **or**
   - Ends with `TVB`, `TVC`, or `TVD`

5. **Hotspot password:** `ritaengs`

6. To view the live feed in VLC:
   - Open **Network Stream** → enter:  
     `tcp://10.42.0.1:5000`  
     *(The live feed has approximately a 5-second delay.)*
   - Instead of the IP address, you can use (works on phone, not on QH laptops):
     - `tva.local` (for TVA)
     - `tvb.local` (for TVB)
     - etc.  


7. **Web UI (HTTP):**
   - Open:  
     `http://10.42.0.1:8080`  
     or  
     `http://tv?.local:8080`  (phone only)
   - Use this page to view recording files and download them.

8. To control recording (start/stop):
   - Plug in or unplug the USB webcam, **or**
   - Use the control button in the Web UI.

9. Recording files are saved as raw files and are very large.  
   Recording files are automatically created every **5 minutes** to prevent excessively large file sizes.    **DO NOT download the MKV files.**

   When you are finished recording:
   - Unplug the camera or stop the recording in the Web UI.
   - Click **Run concat_and_convert** to merge the files and convert the MKV chunks into an MP4 file.
   - Conversion may take some time (approximately **30 minutes for 1 hour of recording**). Monitor the status during processing.

11. Once conversion is complete, the filenames will change.  
    Download the `_checked.mp4` files and play them to verify they are correct.

    - If the filename does **not** include `_checked`, something went wrong and you should re-run **concat_and_convert**.

12. After downloading the files and confirming they are correct:
    - Click **Review MKV deletion** to see which MKV files will be deleted.
    - Delete them using the provided button.

13. You can also delete **all files**, including MP4 files, by clicking **Cleanup All Files**.  
    ⚠️ Use this option carefully.


    
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

## Behavior

- The recorder waits for the camera device to exist.
- If the camera is disconnected, GStreamer exits and the supervisor restarts after a short delay.
- Recordings are split into 5-minute MKV segments with continuous numbering.
- Run `scripts/concat_and_convert.sh` manually when you want to merge sequential segments into a single MP4, validate duration with `ffprobe`, and stamp the filename with `.checked.mp4` once validated.
- Use the web UI cleanup section to delete MKV chunks only after verified `.checked.mp4` files match the total MKV duration.


## Configuration

You can override defaults using environment variables (for systemd, set them in the service file or drop-in overrides):

- `CAMERA` (default `/dev/video0`)
- `OUTDIR` (default `/home/pi/TheraView/recordings`)
- `LOGDIR` (default `/home/pi/TheraView/logs`)
- `RECORD_WIDTH`, `RECORD_HEIGHT`, `FRAMERATE`, `RECORD_BITRATE`, `ROTATE_SECONDS`
- `STREAM_WIDTH`, `STREAM_HEIGHT`, `STREAM_BITRATE`, `STREAM_PORT`

