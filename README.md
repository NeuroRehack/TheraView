# TheraView Recorder

This repository contains a crash-safe USB camera recorder using FFmpeg + MediaMTX, plus a helper script to concatenate TS segments into MP4.

## How to use (quick start)
1. **Before anything**, make sure VLC is installed on your phone or laptop.

2. Turn on the Raspberry Pi and wait approximately **1 minute** for it to fully boot.

3. Once the camera is connected, recording and streaming will start automatically. You can confirm this by checking the **blue LED** on the camera.

4. Connect to the Pi’s hotspot network. It will be named:
   - `TheraView_TVA` **or**
   - Ends with `TVB`, `TVC`, or `TVD`

5. **Hotspot password:** `ritaengs`

6. To view the live feed (**main method**):
   - Open a browser and go to:  
     `http://10.42.0.1:8888/live/`
   - VLC RTSP option: `rtsp://10.42.0.1:8554/live`
   - VLC may have lower latency than some browsers
   - Instead of the IP address, you can use (works on phone, not on QH laptops):
     - `tva.local` (for TVA)
     - `tvb.local` (for TVB)
     - etc.  


7. **Web UI (HTTP):**
   - Open:  
     `http://10.42.0.1:8080`  
     or  
     `http://tv?.local:8080`  (phone only)
   - Use this page to view recording files, download them, delete specific files, and open log files.

8. To control recording (start/stop):
   - Plug in or unplug the USB webcam, **or**
   - Use the control button in the Web UI.

9. Recording files are saved as raw files and are very large.  
   Recording files are automatically created every **5 minutes** to prevent excessively large file sizes.    **DO NOT download the TS files.**

   When you are finished recording:
   - Unplug the camera or stop the recording in the Web UI.
   - Click **Create Checked MP4** in the Web UI to merge files and build the verified MP4 output.

11. Once conversion is complete, the filenames will change.  
    Download the `_checked.mp4` files and play them to verify they are correct.

    - If the filename does **not** include `_checked`, something went wrong and you should run **Create Checked MP4** again.

12. After downloading the files and confirming they are correct, you can delete specific recording files directly from the files table in the Web UI.

13. The Web UI lists log files so you can open them in-browser for troubleshooting.


    
## Structure

- `scripts/theraview_recorder.sh` - main recorder supervisor loop
- `scripts/concat_and_convert.sh` - concatenates TS chunks and converts to MP4
- `systemd/theraview-camera.service` - systemd unit to run recorder at boot
- `systemd/mediamtx.service` - systemd unit to run local RTSP server (MediaMTX)
- `config/mediamtx.yml` - MediaMTX path configuration (`live` publish path)
- `scripts/concat_and_convert.sh` - run manually when you want to merge TS chunks into MP4
- `scripts/theraview_web.py` - lightweight web UI to view files and trigger concat
- `systemd/theraview-web.service` - systemd unit to run the web UI at boot
- `scripts/setup_theraview.sh` - one-shot setup for dependencies + systemd units
- `scripts/remove_theraview_services.sh` - stops and removes systemd units
- `scripts/setup_hotspot.sh` - configure the Pi as a Wi-Fi hotspot



## Requirements

- Raspberry Pi OS (or another Debian-based distro with systemd).
- USB camera available at `/dev/video0` (or set `CAMERA`).
- Packages: `ffmpeg`, `curl`, `tar`, and `network-manager` (for hotspot). MediaMTX is installed by the setup script.

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
- If the camera is disconnected, FFmpeg exits and the supervisor restarts after a short delay.
- Recorder log entries include CPU temperature, load average, and throttle status when available.
- Recordings are split into 5-minute TS segments with continuous numbering.
- Run `scripts/concat_and_convert.sh` manually when you want to merge sequential segments into a single MP4. The script now uses a fast H.264 stream-copy concat path first and falls back to re-encode only if needed, then validates duration with `ffprobe` and stamps the filename with `.checked.mp4`.
- Use the web UI cleanup section to delete TS chunks only after verified `.checked.mp4` files match the total TS duration.


## Configuration

You can override defaults using environment variables (for systemd, set them in the service file or drop-in overrides):

- `CAMERA` (default `/dev/video0`)
- `OUTDIR` (default `/home/pi/TheraView/recordings`)
- `LOGDIR` (default `/home/pi/TheraView/logs`)
- `RECORD_WIDTH`, `RECORD_HEIGHT`, `FRAMERATE`, `RECORD_BITRATE`, `ROTATE_SECONDS`
- `STREAM_BITRATE`, `RTSP_HOST`, `RTSP_PORT`, `RTSP_PATH`

## Real-Time Clock (RTC) Module

TheraView units can use a Gravity I2C DS1307 RTC module to keep accurate system time when the Raspberry Pi is not connected to the internet. This is useful because recording filenames, logs, and timestamps depend on the Pi’s system clock.

> A schematic of the RTC wiring can be added here.

#### RTC wiring

Connect the Gravity I2C DS1307 RTC module to the Raspberry Pi as follows:

| Gravity RTC pin |  Function | Raspberry Pi pin    |
| --------------- | --------: | ------------------- |
| Pin 6 `+`       |  5V power | Pin 2 — 5V          |
| Pin 7 `-`       |    Ground | Pin 9 — GND         |
| Pin 8 `C`       | I2C clock | Pin 5 — SCL / GPIO3 |
| Pin 9 `D`       |  I2C data | Pin 3 — SDA / GPIO2 |

#### Install I2C tools

```bash
sudo apt install -y python3-smbus i2c-tools
```

Check that the RTC is visible on the I2C bus:

```bash
i2cdetect -y 1
```

The DS1307 RTC normally appears at address `0x68`.

#### Enable the DS1307 RTC overlay

Edit the Raspberry Pi boot configuration:

```bash
sudo nano /boot/firmware/config.txt
```

Add this line at the end of the file:

```ini
dtoverlay=i2c-rtc,ds1307
```

On some older Raspberry Pi OS setups, the file may be located at:

```bash
/boot/config.txt
```

After saving the change, reboot the Pi:

```bash
sudo reboot
```

#### Test the RTC

After reboot, check that the RTC device exists:

```bash
ls -l /dev/rtc*
```

Read the current RTC time:

```bash
sudo hwclock -r
```

If the RTC is detected correctly, set the RTC from the Pi’s current system time:

```bash
sudo hwclock -w
```

Then read it back to confirm:

```bash
sudo hwclock -r
```

Once configured, the RTC helps the Pi keep time between boots, even when the TheraView unit is offline.

