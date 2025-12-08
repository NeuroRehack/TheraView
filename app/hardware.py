import threading
import time


try:
    import RPi.GPIO as GPIO
except ImportError:  # pragma: no cover - not available in dev environments
    GPIO = None

try:
    from evdev import InputDevice, categorize, ecodes, list_devices
except ImportError:  # pragma: no cover - not available in dev environments
    InputDevice = None
    categorize = None
    ecodes = None
    list_devices = lambda: []


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

    def __init__(self, toggle_callback):
        self.toggle_callback = toggle_callback
        self.running = False
        self.thread = None
        self.available = InputDevice is not None

        if not self.available:
            print("evdev not available; Bluetooth remote control disabled.")

    def start(self):
        if not self.available or self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False

    def _find_device(self):
        for path in list_devices():
            try:
                dev = InputDevice(path)
                if "Selfie" in dev.name:
                    return dev
            except Exception:
                continue
        return None

    def _run(self):
        print("Press the button on the 'Selfie' Bluetooth remote to wake it.")

        while self.running:
            dev = self._find_device()
            if dev is None:
                time.sleep(2)
                continue

            try:
                for event in dev.read_loop():
                    if not self.running:
                        break

                    if event.type != ecodes.EV_KEY:
                        continue

                    key_event = categorize(event)
                    if key_event.keystate == key_event.key_down:
                        self.toggle_callback()
            except Exception:
                # Device disconnected or read failed; restart search
                time.sleep(1)

