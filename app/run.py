import socketserver
from .web import Handler
from .core import get_network_ip, PORT, LED_PIN
from .control import set_led_controller, set_recording_state, toggle_recording
from .hardware import LedIndicator, SelfieRemoteListener

def run():
    led = LedIndicator(LED_PIN)
    if getattr(led, "enabled", False):
        print(f"Recording LED ready on GPIO {LED_PIN}.")
    set_led_controller(led)

    remote_listener = SelfieRemoteListener(toggle_recording)
    remote_listener.start()

    with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), Handler) as httpd:
        ip = get_network_ip()
        if ip:
            print(f"Server reachable at http://{ip}:{PORT}")
        else:
            print("No network IP found. Device may not be connected.")

        set_recording_state(True)
        httpd.serve_forever()
