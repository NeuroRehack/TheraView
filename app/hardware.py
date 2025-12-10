import os
import subprocess
import threading
import time


try:
    import RPi.GPIO as GPIO
except ImportError:  # pragma: no cover - not available in dev environments
    GPIO = None

try:
    from evdev import InputDevice, ecodes, list_devices
except ImportError:  # pragma: no cover - not available in dev environments
    InputDevice = None
    ecodes = None
    list_devices = lambda: []


_remote_lock = threading.Lock()
_remote_connected = False


def set_remote_connected(state: bool):
    global _remote_connected
    with _remote_lock:
        changed = _remote_connected != state
        _remote_connected = state
    if changed:
        status = "connected" if state else "disconnected"
        print(f"Selfie remote {status}.")


def remote_status():
    with _remote_lock:
        return {
            "available": InputDevice is not None,
            "connected": _remote_connected,
        }


def rtc_status():
    """Check RTC availability and current time (if readable)."""

    rtc_device = None
    for candidate in ("/dev/rtc", "/dev/rtc0"):
        if os.path.exists(candidate):
            rtc_device = candidate
            break

    if rtc_device is None:
        return {"present": False, "time": None}

    try:
        output = subprocess.check_output(["hwclock", "-r"], text=True, stderr=subprocess.STDOUT)
        timestamp = output.strip()
        if timestamp:
            return {"present": True, "time": timestamp}
    except Exception as exc:  # pragma: no cover - hardware specific
        print(f"RTC detected at {rtc_device} but failed to read time: {exc}")

    return {"present": True, "time": None}


class LedIndicator:
    """Simple GPIO LED driver used for recording status."""

    def __init__(self, pin: int):
        self.pin = pin
        self.enabled = False

        if GPIO is None:
            print("RPi.GPIO not available; LED indicator disabled.")
            return

        try:
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.pin, GPIO.OUT, initial=GPIO.LOW)
            self.enabled = True
        except Exception as exc:  # pragma: no cover - hardware specific
            print(f"Failed to initialize LED on pin {self.pin}: {exc}")
            self.enabled = False

    def set(self, on: bool):
        if not self.enabled:
            return
        GPIO.output(self.pin, GPIO.HIGH if on else GPIO.LOW)

    def cleanup(self):
        if not self.enabled:
            return
        try:
            GPIO.output(self.pin, GPIO.LOW)
        finally:  # pragma: no cover - hardware specific
            GPIO.cleanup(self.pin)


class SelfieRemoteListener:
    """Listens for key presses from the 'Selfie' Bluetooth remote."""

    def __init__(self, toggle_callback, device_name="Selfie", device_path=None):
        self.toggle_callback = toggle_callback
        self.device_name = device_name
        self.device_path = device_path
        self.running = False
        self.thread = None
        self.available = InputDevice is not None
        self.connected = False

        if not self.available:
            print("evdev not available; Bluetooth remote control disabled.")
            set_remote_connected(False)

    def start(self):
        if not self.available or self.running:
            return
        self.running = True
        set_remote_connected(False)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        set_remote_connected(False)

    def _find_device(self):
        # If the user provided an explicit path, try that first.
        if self.device_path:
            try:
                dev = InputDevice(self.device_path)
                return dev
            except Exception:
                pass

        for path in list_devices():
            try:
                dev = InputDevice(path)
                if self.device_name in dev.name:
                    return dev
            except Exception:
                continue
        return None

    def _run(self):
        print("Press the button on the 'Selfie' Bluetooth remote to wake it.")

        while self.running:
            dev = self._find_device()
            if dev is None:
                if self.connected:
                    self.connected = False
                    set_remote_connected(False)
                time.sleep(2)
                continue

            self.connected = True
            set_remote_connected(True)
            print(f"Listening for remote keypresses from {dev.path} ({dev.name}).")

            try:
                for event in dev.read_loop():
                    if not self.running:
                        break

                    if event.type != ecodes.EV_KEY:
                        continue

                    if event.value == 1 and event.code in (
                        ecodes.KEY_VOLUMEUP,
                        ecodes.KEY_VOLUMEDOWN,
                        ecodes.KEY_ENTER,
                    ):
                        self.toggle_callback()
            except Exception:
                # Device disconnected or read failed; restart search
                self.connected = False
                set_remote_connected(False)
                time.sleep(1)

