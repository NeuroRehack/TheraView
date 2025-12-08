import socketserver
from .web import Handler
from .core import (
    AUTO_START_RECORDING,
    get_network_ip,
    LED_PIN,
    PORT,
    SELFIE_DEVICE_PATH,
)
from .control import set_led_controller, set_recording_state, toggle_recording
from .hardware import LedIndicator, SelfieRemoteListener

def run():
    led = LedIndicator(LED_PIN)
    if getattr(led, "enabled", False):
        print(f"Recording LED ready on GPIO {LED_PIN}.")
    set_led_controller(led)

    path = SELFIE_DEVICE_PATH if SELFIE_DEVICE_PATH else None
    remote_listener = SelfieRemoteListener(toggle_recording, device_path=path)
    remote_listener.start()

    with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), Handler) as httpd:
        ip = get_network_ip()
        if ip:
            print(f"Server reachable at http://{ip}:{PORT}")
        else:
            print("No network IP found. Device may not be connected.")

        set_recording_state(AUTO_START_RECORDING)
        httpd.serve_forever()
