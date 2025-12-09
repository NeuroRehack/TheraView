import http.server
import json
import time
import threading
import os
import socketserver

from .ui import HTML_PAGE
from .core import get_network_ip, get_free_space_gb, PORT
from .hardware import remote_status, rtc_status
from . import control

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(HTML_PAGE)
            return

        if self.path == "/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            status = {
                **control.status_snapshot(),
                **remote_status(),
                "rtc": rtc_status(),
            }
            self.wfile.write(json.dumps(status).encode("utf8"))
            return

        if self.path == "/toggle_record":
            control.toggle_recording()
            self._simple(b"ok")
            return

        if self.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()

            while True:
                with control.proc_lock:
                    proc = control.current_pipe()

                if proc is None:
                    time.sleep(0.05)
                    continue

                try:
                    chunk = proc.stdout.read(4096)
                except:
                    time.sleep(0.02)
                    continue

                if not chunk:
                    time.sleep(0.02)
                    continue

                try:
                    self.wfile.write(chunk)
                except BrokenPipeError:
                    return

        if self.path == "/exit":
            with control.proc_lock:
                control.stop_pipelines()
            self._simple(b"Exiting")

            def stop_server():
                time.sleep(0.3)
                os._exit(0)

            threading.Thread(target=stop_server).start()
            return

        if self.path == "/mem":
            free = get_free_space_gb()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"free_gb": round(free, 2)}).encode("utf8"))
            return

        if self.path == "/filename":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"name": control.status_snapshot()["filename"]}).encode("utf8"))
            return

        self.send_error(404)

    def _simple(self, msg):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(msg)
