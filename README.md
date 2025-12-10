# TheraView
TheraView is a portable two angle capture system for physical therapy and occupational therapy. The goal is to build a simple and affordable kit that records sessions at high quality, offers a live preview, supports synchronized dual camera use, and later adds pose analysis and activity tools. TheraView is part of the RITA Project.

---


## Hardware

- **Raspberry Pi 4B**
- **Microsoft LifeCam Studio**  
  Any USB webcam that supports 1080p MJPG at 30 FPS can be used.
- **Power bank** 10,000 mAh, 22.5 W output (Anker)  
  *Operation duration: [to be tested]*
- **MicroSD card** 64 GB , class TBD
- **Cooling fan for Raspberry Pi**
- **3D printed enclosure:** [to be added]
- **Tripod mount**  
  This model (link TBA ) was used and the enclosure design follows this choice.
  It also includes a Bluetooth button used to trigger camera control.
- **Optional future processing unit**
- **SD card reader

---

## Software

- **Raspberry Pi OS Lite (Bookworm)**  
  - file name: 2024-07-04-raspios-bookworm-arm64-lite.img.xz 
  - Version: bookworm-arm64-lite
  - Release date: 2024-07-04
- **GStreamer**  
  - Version: [to be added]
- To be completed

---

## Setup Guide


Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/) with advanced settings before writing the SD cards.

Use the Raspberry Pi Imager with advanced settings before you write the SD cards.

### Hostnames
- **TVA** for unit one  
- **TVB** for unit two  

Set these exactly as shown because the setup process relies on them.

### Username
- **pi**

### Password
- Choose your own secure password.

### Wireless LAN
The device needs internet access during setup and the first test run, so configure WiFi here. A mobile hotspot works.  
If you use an iPhone hotspot, rename the phone. Default names such as `John's iPhone` include an apostrophe, which the Raspberry Pi rejects. Use a simple name such as `John iPhone`.

Select the wireless LAN country that matches your location.

### Locale
Choose your timezone and keyboard layout.

### Services
- Enable **SSH**  
- Use **password authentication**

### First Boot
After the SD card is ready, place it in the Raspberry Pi and power it on.

Allow a few minutes for the first boot, then connect from a computer on the same network:

```bash
ssh pi@TVA.local
# or
ssh pi@TVB.local
```
If hostname lookup does not work, find the device IP with a network scanner and connect to that address instead.


After you connect to the RPi

```
sudo apt update -y
sudo apt upgrade -y
sudo apt install git -y

git clone https://github.com/NeuroRehack/TheraView
cd TheraView
sudo chmod +x scripts/setup.sh 
./scripts/setup.sh
```

### Pair the "Selfie" Bluetooth remote
Run the pairing helper and press the button on the tripod Bluetooth module when prompted:

```
./scripts/setup_selfie.sh
```

The remote will appear as `Selfie` in Bluetooth scans. Once paired, pressing its button or the web UI button both start/stop recording.
If your device enumerates the input node at a fixed path (for example `/dev/input/event4`), set `SELFIE_DEVICE_PATH` in `config.conf` so
the listener can open it directly.

### Recording status LED
The recording status LED uses GPIO pin 21 by default. Change the pin assignment in `config.conf` under the `LED_PIN` setting if your wiring differs.
Running the server as `root` or a user with GPIO permissions is required for the LED to toggle.

Set `AUTO_START_RECORDING` to `true` to begin recording as soon as the app launches. Set it to `false` to start in preview-only mode and wait for the web UI or Bluetooth remote to toggle recording.

Recorded clips now include a time-of-day overlay for easier provenance, and the controller auto-recovers the preview pipeline if a recording unexpectedly stops. When recordings end, the app flushes the last file to disk to reduce the chance of corruption.

### Optional RTC module
Enable the DS3231 overlay (for example by adding `dtoverlay=i2c-rtc,ds3231` to `/boot/firmware/config.txt`). When an RTC is present, the web UI shows the current RTC time beneath the Bluetooth status.

Note: If you do not want the system to auto start on systemd or set up the hotspot, edit the config file at config/theraview.config and change these flags: ENABLE_SYSTEMD and ENABLE_HOTSPOT

---


## Usage

**[ instructions to be added]**




---




## Roadmap

### Stage 1: Single Camera Unit *(Current Stage)*
- Install Raspberry Pi OS Lite ✅
- Verify 1080p at 30 FPS capture with MJPG ✅
- Add GStreamer preview output to an HTML page ✅
- Add recording in segments
- Confirm recording stability 
- Test power bank duration
- Add status LED(s)
- Add the first enclosure design
- Use the Bluetooth button on the tripod mount to trigger camera recording
- Add an RTC module for reliable time tracking

### Stage 2: Dual Camera System
- Add a second camera setup
- Add synchronized start across both units
- Build a page that displays the two live previews
- Improve local network coordination
- Add a auto file transfer system when connected to an external HDD

### Stage 3: Synchronized Recording and Playback
- Align timelines between both units
- Create a playback layout with two camera angles
- Add session metadata
- Improve storage flow and file handling

### Stage 4: Pose Detection
- Apply pose models to recorded sessions
- Produce structured data for therapist review
- Add export and visualization tools
- Add a privacy layer that captures only pose and activity data instead of raw video when desired

### Stage 5: Activity and Game Layer
- Train models for specific therapy tasks
- Add workflow logic for guided activities
- Add simple games that respond to pose output

### Stage 6: External Processing Unit
- Add an external processor for real time analysis
- Offload compute tasks from Raspberry Pi units
- Improve overall performance of the streaming and analysis pipeline


*TheraView — A RITA Project initiative.*
