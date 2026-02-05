#!/usr/bin/env python3
import json
import os
import re
import signal
import socket
import subprocess
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from subprocess import Popen
from urllib.parse import parse_qs, urlparse

OUTDIR = os.environ.get("OUTDIR", "/home/pi/TheraView/recordings")
LOGDIR = os.environ.get("LOGDIR", "/home/pi/TheraView/logs")
CONCAT_SCRIPT = os.environ.get(
    "CONCAT_SCRIPT", "/home/pi/TheraView/scripts/concat_and_convert.sh"
)
STATUS_FILE = os.environ.get("STATUS_FILE", os.path.join(LOGDIR, "concat_status.json"))
LOG_FILE = os.environ.get("LOG_FILE", os.path.join(LOGDIR, "concat_and_convert.log"))
HOST = os.environ.get("WEB_HOST", "0.0.0.0")
PORT = int(os.environ.get("WEB_PORT", "8080"))
RECORDER_SERVICE = os.environ.get(
    "RECORDER_SERVICE", "theraview-camera.service"
)
CAMERA_DEVICE = os.environ.get("CAMERA_DEVICE", os.environ.get("CAMERA", "/dev/video0"))
FFPROBE = os.environ.get("FFPROBE", "ffprobe")
STREAM_PORT = int(os.environ.get("STREAM_PORT", "5000"))
HOSTNAME = socket.gethostname()

os.makedirs(OUTDIR, exist_ok=True)
os.makedirs(LOGDIR, exist_ok=True)

RUN_LOCK = threading.Lock()
CPU_STATE = {"total": None, "idle": None, "percent": None}


def read_status():
    if not os.path.exists(STATUS_FILE):
        return {
            "running": False,
            "last_exit": None,
            "start_time": None,
            "end_time": None,
            "pid": None,
            "stop_requested": False,
        }
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
            payload.setdefault("pid", None)
            payload.setdefault("stop_requested", False)
            return payload
    except (OSError, json.JSONDecodeError):
        return {
            "running": False,
            "last_exit": None,
            "start_time": None,
            "end_time": None,
            "pid": None,
            "stop_requested": False,
        }


def write_status(data):
    with open(STATUS_FILE, "w", encoding="utf-8") as handle:
        json.dump(data, handle)


def tail_log(lines=40):
    if not os.path.exists(LOG_FILE):
        return ""
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as handle:
            content = handle.readlines()
        return "".join(content[-lines:])
    except OSError:
        return ""


def read_cpu_times():
    try:
        with open("/proc/stat", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("cpu "):
                    parts = line.split()
                    values = list(map(int, parts[1:]))
                    total = sum(values)
                    idle = values[3] + values[4] if len(values) > 4 else values[3]
                    return total, idle
    except OSError:
        return None, None
    return None, None


def get_cpu_usage_percent():
    total, idle = read_cpu_times()
    if total is None or idle is None:
        return None
    prev_total = CPU_STATE["total"]
    prev_idle = CPU_STATE["idle"]
    CPU_STATE["total"] = total
    CPU_STATE["idle"] = idle
    if prev_total is None or prev_idle is None:
        return CPU_STATE["percent"]
    total_delta = total - prev_total
    idle_delta = idle - prev_idle
    if total_delta <= 0:
        return CPU_STATE["percent"]
    usage = (total_delta - idle_delta) / total_delta * 100.0
    CPU_STATE["percent"] = max(0.0, min(100.0, usage))
    return CPU_STATE["percent"]


def get_clock_time():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def get_rtc_status():
    rtc_path = "/sys/class/rtc/rtc0"
    if not os.path.exists(rtc_path):
        return {"detected": False, "name": None}
    name_path = os.path.join(rtc_path, "name")
    rtc_name = None
    try:
        with open(name_path, "r", encoding="utf-8") as handle:
            rtc_name = handle.read().strip()
    except OSError:
        rtc_name = None
    return {"detected": True, "name": rtc_name}


def get_service_status(service_name):
    if not service_name:
        return {
            "service": None,
            "active": "not configured",
            "enabled": "not configured",
            "error": None,
        }
    try:
        active = subprocess.run(
            ["systemctl", "is-active", service_name],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        enabled = subprocess.run(
            ["systemctl", "is-enabled", service_name],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return {
            "service": service_name,
            "active": active.stdout.strip() or active.stderr.strip(),
            "enabled": enabled.stdout.strip() or enabled.stderr.strip(),
            "error": None,
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "service": service_name,
            "active": "unknown",
            "enabled": "unknown",
            "error": str(exc),
        }


def control_service(service_name, action):
    if not service_name:
        return {"ok": False, "message": "Service not configured."}
    if action not in {"start", "stop", "restart"}:
        return {"ok": False, "message": "Unsupported action."}
    try:
        result = subprocess.run(
            ["systemctl", action, service_name],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "Command failed."
            return {"ok": False, "message": message}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "message": f"{action} requested."}


def is_pid_running(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def ensure_concat_status_current():
    with RUN_LOCK:
        status = read_status()
        if status.get("running"):
            pid = status.get("pid")
            if not pid or not is_pid_running(pid):
                status.update(
                    {
                        "running": False,
                        "end_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "last_exit": status.get("last_exit") or -1,
                        "pid": None,
                        "stop_requested": False,
                    }
                )
                write_status(status)
        return status


def get_recorder_summary(service_status):
    device_present = os.path.exists(CAMERA_DEVICE)
    active = service_status.get("active") == "active"
    if active and device_present:
        message = f"Recording active - {CAMERA_DEVICE}"
        state = "active"
    elif device_present:
        message = "Recording inactive - service stopped"
        state = "inactive"
    else:
        message = f"Recording inactive - camera disconnected ({CAMERA_DEVICE})"
        state = "inactive"
    return {
        "message": message,
        "state": state,
        "device": CAMERA_DEVICE,
        "device_present": device_present,
    }


def run_command(args, timeout=2):
    try:
        result = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def get_hotspot_ssid():
    output = run_command(["nmcli", "-t", "-f", "NAME,TYPE,ACTIVE", "connection", "show", "--active"])
    if not output:
        return None
    for line in output.splitlines():
        parts = line.split(":")
        if len(parts) < 3:
            continue
        name, conn_type, active = parts[0], parts[1], parts[2]
        if conn_type != "wifi" or active.lower() != "yes":
            continue
        mode = run_command(["nmcli", "-t", "-f", "802-11-wireless.mode", "connection", "show", name])
        if mode.strip().lower() != "ap":
            continue
        ssid = run_command(["nmcli", "-t", "-f", "802-11-wireless.ssid", "connection", "show", name])
        if ssid:
            return ssid.strip()
    return None


def get_wifi_info():
    ssid = run_command(["iwgetid", "-r"])
    if ssid:
        return {"ssid": ssid, "mode": "client"}
    hotspot_ssid = get_hotspot_ssid()
    if hotspot_ssid:
        return {"ssid": hotspot_ssid, "mode": "hotspot"}
    return {"ssid": None, "mode": None}


def get_ip_addresses():
    output = run_command(["ip", "-4", "addr", "show"])
    addresses = {}
    current_iface = None
    for line in output.splitlines():
        if line and line[0].isdigit():
            parts = line.split(":", 2)
            if len(parts) >= 2:
                current_iface = parts[1].strip()
                addresses.setdefault(current_iface, [])
        elif "inet " in line and current_iface:
            inet = line.strip().split()
            if len(inet) >= 2:
                ip = inet[1].split("/")[0]
                addresses.setdefault(current_iface, []).append(ip)
    return addresses


def get_primary_ip_info():
    route = run_command(["ip", "route", "get", "1.1.1.1"])
    interface = None
    if route:
        parts = route.split()
        if "dev" in parts:
            interface = parts[parts.index("dev") + 1]
    addresses = get_ip_addresses()
    if not interface:
        for candidate in ("wlan0", "ap0", "uap0"):
            if candidate in addresses and addresses[candidate]:
                interface = candidate
                break
    ip = None
    if interface and addresses.get(interface):
        ip = addresses[interface][0]
    return {"interface": interface, "ip": ip, "addresses": addresses}


def get_cleanup_plan():
    converted_tag = "_converted.mkv"
    prefixes = {}
    for name in os.listdir(OUTDIR):
        if not name.endswith(converted_tag):
            continue
        match = re.match(r"^(.*)_[0-9]{5}_converted\.mkv$", name)
        if not match:
            continue
        base = match.group(1)
        prefixes.setdefault(base, []).append(os.path.join(OUTDIR, name))
    candidates = []
    for prefix, chunks in sorted(prefixes.items()):
        chunks = sorted(chunks)
        candidates.append(
            {
                "prefix": prefix,
                "chunks": chunks,
            }
        )
    return {"candidates": candidates, "blocked": []}


def delete_mkv_chunks(prefixes):
    plan = get_cleanup_plan()
    allowed = {item["prefix"]: item for item in plan["candidates"]}
    deleted = []
    skipped = []
    for prefix in prefixes:
        item = allowed.get(prefix)
        if not item:
            skipped.append(prefix)
            continue
        for chunk in item["chunks"]:
            try:
                os.remove(chunk)
                deleted.append(chunk)
            except OSError:
                skipped.append(prefix)
                break
    return {"deleted": deleted, "skipped": skipped}


def delete_all_files():
    deleted = []
    skipped = []
    for name in sorted(os.listdir(OUTDIR)):
        path = os.path.join(OUTDIR, name)
        if not os.path.isfile(path):
            continue
        try:
            os.remove(path)
            deleted.append(name)
        except OSError:
            skipped.append(name)
    return {"deleted": deleted, "skipped": skipped}


def run_concat():
    with RUN_LOCK:
        status = read_status()
        if status.get("running"):
            return False
        status.update(
            {
                "running": True,
                "start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "end_time": None,
                "last_exit": None,
                "pid": None,
                "stop_requested": False,
            }
        )
        write_status(status)

    exit_code = None
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as log_handle:
            process = Popen([CONCAT_SCRIPT], stdout=log_handle, stderr=log_handle)
            with RUN_LOCK:
                status = read_status()
                status["pid"] = process.pid
                write_status(status)
            exit_code = process.wait()
    except OSError:
        exit_code = -1
    finally:
        with RUN_LOCK:
            status = read_status()
            status.update(
                {
                    "running": False,
                    "end_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "last_exit": exit_code,
                    "pid": None,
                    "stop_requested": False,
                }
            )
            write_status(status)

    return True


def request_stop_concat():
    with RUN_LOCK:
        status = read_status()
        if not status.get("running"):
            return {"ok": False, "message": "Concat job is not running."}
        pid = status.get("pid")
        if not pid:
            status.update(
                {
                    "running": False,
                    "end_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "last_exit": status.get("last_exit") or -1,
                    "pid": None,
                    "stop_requested": False,
                }
            )
            write_status(status)
            return {"ok": False, "message": "Concat PID missing; status reset."}
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError as exc:
            return {"ok": False, "message": str(exc)}
        status["stop_requested"] = True
        write_status(status)
        return {"ok": True, "message": "Stop requested."}


def list_files():
    entries = []
    for name in sorted(os.listdir(OUTDIR)):
        path = os.path.join(OUTDIR, name)
        if not os.path.isfile(path):
            continue
        stat = os.stat(path)
        entries.append(
            {
                "name": name,
                "size": stat.st_size,
                "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
            }
        )
    return entries


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html):
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/status":
            status = ensure_concat_status_current()
            status["log_tail"] = tail_log()
            status["cpu_usage"] = get_cpu_usage_percent()
            status["clock_time"] = get_clock_time()
            status["rtc"] = get_rtc_status()
            recorder_service = get_service_status(RECORDER_SERVICE)
            status["recorder_service"] = recorder_service
            status["recorder_summary"] = get_recorder_summary(recorder_service)
            status["hostname"] = HOSTNAME
            status["wifi"] = get_wifi_info()
            status["network"] = get_primary_ip_info()
            status["stream_port"] = STREAM_PORT
            status["elapsed_seconds"] = None
            if status.get("running") and status.get("start_time"):
                try:
                    start_tuple = time.strptime(status["start_time"], "%Y-%m-%d %H:%M:%S")
                    status["elapsed_seconds"] = int(time.time() - time.mktime(start_tuple))
                except ValueError:
                    status["elapsed_seconds"] = None
            self._send_json(status)
            return
        if parsed.path == "/files":
            self._send_json({"files": list_files()})
            return
        if parsed.path == "/cleanup-plan":
            self._send_json(get_cleanup_plan())
            return
        if parsed.path == "/download":
            params = parse_qs(parsed.query)
            name = params.get("name", [None])[0]
            if not name:
                self.send_error(HTTPStatus.BAD_REQUEST, "Missing name")
                return
            safe_name = os.path.basename(name)
            if safe_name != name:
                self.send_error(HTTPStatus.BAD_REQUEST, "Invalid name")
                return
            path = os.path.join(OUTDIR, safe_name)
            if not os.path.isfile(path):
                self.send_error(HTTPStatus.NOT_FOUND, "Not found")
                return
            try:
                with open(path, "rb") as handle:
                    data = handle.read()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.send_header(
                    "Content-Disposition", f'attachment; filename="{safe_name}"'
                )
                self.end_headers()
                self.wfile.write(data)
            except OSError:
                self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "Read failed")
            return
        if parsed.path == "/":
            self._send_html(render_index())
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/run-concat":
            ensure_concat_status_current()
            with RUN_LOCK:
                if read_status().get("running"):
                    self._send_json(
                        {"started": False, "message": "Already running"},
                        status=HTTPStatus.CONFLICT,
                    )
                    return
            thread = threading.Thread(target=run_concat, daemon=True)
            thread.start()
            self._send_json({"started": True})
            return
        if parsed.path == "/stop-concat":
            result = request_stop_concat()
            status_code = HTTPStatus.OK if result["ok"] else HTTPStatus.BAD_REQUEST
            self._send_json(result, status=status_code)
            return
        if parsed.path == "/cleanup":
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            body = self.rfile.read(length).decode("utf-8") if length else ""
            try:
                payload = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self._send_json(
                    {"ok": False, "message": "Invalid JSON"},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return
            prefixes = payload.get("prefixes", [])
            if not isinstance(prefixes, list) or not prefixes:
                self._send_json(
                    {"ok": False, "message": "No prefixes provided."},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return
            result = delete_mkv_chunks(prefixes)
            self._send_json({"ok": True, **result})
            return
        if parsed.path == "/cleanup-all":
            result = delete_all_files()
            self._send_json({"ok": True, **result})
            return
        if parsed.path == "/service":
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            body = self.rfile.read(length).decode("utf-8") if length else ""
            try:
                payload = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self._send_json(
                    {"ok": False, "message": "Invalid JSON"},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return
            target = payload.get("service")
            action = payload.get("action")
            service_name = {
                "recorder": RECORDER_SERVICE,
            }.get(target)
            if service_name is None:
                self._send_json(
                    {"ok": False, "message": "Unknown service"},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return
            result = control_service(service_name, action)
            status_code = HTTPStatus.OK if result["ok"] else HTTPStatus.BAD_REQUEST
            self._send_json(result, status=status_code)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")


INDEX_HTML = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <title>TheraView - __HOSTNAME__</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f7fb;
      --card: #ffffff;
      --border: #e0e6ef;
      --text: #1f2937;
      --muted: #6b7280;
      --primary: #2563eb;
      --primary-dark: #1d4ed8;
      --danger: #dc2626;
      --danger-dark: #b91c1c;
      --shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
    }
    * { box-sizing: border-box; }
    body { font-family: "Inter", "Segoe UI", sans-serif; margin: 0; background: var(--bg); color: var(--text); }
    .page { max-width: 1200px; margin: 0 auto; padding: 2.5rem 2rem 3rem; }
    header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; gap: 1rem; }
    h1 { font-size: 1.9rem; margin: 0; letter-spacing: -0.02em; display: flex; align-items: baseline; gap: 0.5rem; }
    h1 span { font-size: 1rem; font-weight: 500; color: var(--muted); }
    h2 { margin-top: 2.5rem; font-size: 1.3rem; }
    p { margin: 0.35rem 0; color: var(--muted); }
    table { border-collapse: collapse; width: 100%; margin-top: 1rem; background: var(--card); border-radius: 12px; overflow: hidden; box-shadow: var(--shadow); }
    th, td { padding: 0.75rem 1rem; text-align: left; border-bottom: 1px solid var(--border); }
    th { background: #f8fafc; font-weight: 600; color: var(--muted); }
    tr:last-child td { border-bottom: none; }
    pre { background: #0f172a; color: #e2e8f0; padding: 1rem; border-radius: 12px; box-shadow: var(--shadow); overflow: auto; }
    button { padding: 0.55rem 1.1rem; border-radius: 8px; border: 1px solid transparent; background: var(--primary); color: white; font-weight: 600; cursor: pointer; transition: all 0.15s ease; }
    button:hover { background: var(--primary-dark); }
    button:disabled { background: #cbd5f5; color: #6b7280; cursor: not-allowed; }
    .secondary { background: white; border-color: var(--border); color: var(--text); }
    .secondary:hover { background: #f1f5f9; }
    .danger { background: var(--danger); }
    .danger:hover { background: var(--danger-dark); }
    .button-row { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem; }
    .meta { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.25rem; }
    .card { border: 1px solid var(--border); padding: 1.25rem; border-radius: 12px; background: var(--card); box-shadow: var(--shadow); }
    .card h3 { margin-top: 0; font-size: 1.1rem; }
    .status-active { color: #16a34a; font-weight: 600; }
    .status-inactive { color: #dc2626; font-weight: 600; }
    .section { margin-top: 2rem; }
    .cleanup-warning { margin-top: 0.75rem; padding: 0.75rem; border-radius: 10px; background: #fef3c7; color: #92400e; border: 1px solid #fde68a; }
  </style>
</head>
<body>
  <div class=\"page\">
    <header>
      <h1>TheraView <span id=\"hostname\">(--)</span></h1>
    </header>
    <div class=\"meta\">
      <div class=\"card\">
        <h3>System</h3>
        <p id=\"clock\">Clock: --</p>
        <p id=\"rtc\">RTC: --</p>
        <p id=\"cpu\">CPU Usage: --</p>
        <p id=\"wifi\">Wi-Fi: --</p>
        <p id=\"ip\">IP: --</p>
        <p>Live stream (VLC): <a id=\"stream-link\" href=\"#\" target=\"_blank\" rel=\"noopener\">tcp://--</a> (expect 5s+ delay)</p>
      </div>
      <div class=\"card\">
        <h3>Camera Recording</h3>
        <p id=\"recorder\" class=\"status-inactive\">Recording status: --</p>
        <div class=\"button-row\">
          <button id=\"recorder-start\">Start</button>
          <button id=\"recorder-stop\" class=\"secondary\">Stop</button>
        </div>
      </div>
      <div class=\"card\">
        <h3>Concat Job</h3>
        <div class=\"button-row\">
          <button id=\"run\">Run concat_and_convert</button>
          <button id=\"stop-concat\" class=\"secondary\">Stop concat_and_convert</button>
        </div>
        <p id=\"status\">Status: idle</p>
        <p id=\"timing\">Start: -- | End: -- | Elapsed: --</p>
      </div>
      <div class=\"card\">
        <h3>Cleanup Converted Files</h3>
        <p><strong>Warning:</strong> This deletes MKV chunks tagged as converted.</p>
        <div class=\"button-row\">
          <button id=\"review-cleanup\" class=\"secondary\">Review MKV cleanup</button>
          <button id=\"confirm-cleanup\" class=\"danger\" disabled>Delete MKV chunks</button>
        </div>
        <div id=\"cleanup-warning\" class=\"cleanup-warning\" style=\"display:none;\">
          <p>Files queued for deletion:</p>
          <ul id=\"cleanup-list\"></ul>
          <p id=\"cleanup-blocked\"></p>
        </div>
      </div>
      <div class=\"card\">
        <h3>Cleanup All Files</h3>
        <p><strong>Serious Warning:</strong> This permanently deletes <em>all</em> recordings, including MP4 files.</p>
        <div class=\"button-row\">
          <button id=\"confirm-cleanup-all\" class=\"danger\">Delete ALL files</button>
        </div>
      </div>
    </div>
    <section class=\"section\">
      <h2>Files</h2>
      <table>
        <thead>
          <tr><th>Name</th><th>Size (MB)</th><th>Modified</th><th>Download</th></tr>
        </thead>
        <tbody id=\"files\"></tbody>
      </table>
    </section>
    <section class=\"section\">
      <h2>Latest Log</h2>
      <pre id=\"log\"></pre>
    </section>
  </div>
<script>
async function fetchStatus() {
  const res = await fetch('/status');
  const data = await res.json();
  const statusEl = document.getElementById('status');
  const state = data.running ? (data.stop_requested ? 'stopping' : 'running') : 'idle';
  const exit = data.last_exit === null ? 'n/a' : data.last_exit;
  statusEl.textContent = `Status: ${state} (last exit: ${exit})`;
  const elapsed = data.elapsed_seconds === null ? 'n/a' : `${data.elapsed_seconds}s`;
  document.getElementById('timing').textContent = `Start: ${data.start_time || 'n/a'} | End: ${data.end_time || 'n/a'} | Elapsed: ${elapsed}`;
  const cpuUsage = data.cpu_usage;
  const cpuText = cpuUsage === null || cpuUsage === undefined ? 'n/a' : `${cpuUsage.toFixed(1)}%`;
  document.getElementById('cpu').textContent = `CPU Usage: ${cpuText}`;
  document.getElementById('hostname').textContent = data.hostname ? `(${data.hostname})` : '(n/a)';
  document.getElementById('clock').textContent = `Clock: ${data.clock_time || 'n/a'}`;
  const rtc = data.rtc || {};
  const rtcName = rtc.name ? ` (${rtc.name})` : '';
  document.getElementById('rtc').textContent = `RTC: ${rtc.detected ? 'detected' + rtcName : 'not detected'}`;
  const wifi = data.wifi || {};
  const wifiLabel = wifi.ssid ? `${wifi.ssid}${wifi.mode ? ` (${wifi.mode})` : ''}` : 'n/a';
  document.getElementById('wifi').textContent = `Wi-Fi: ${wifiLabel}`;
  const network = data.network || {};
  const ipLabel = network.ip ? `${network.ip}${network.interface ? ` (${network.interface})` : ''}` : 'n/a';
  document.getElementById('ip').textContent = `IP: ${ipLabel}`;
  const streamPort = data.stream_port || 5000;
  const streamHost = network.ip || data.hostname || '0.0.0.0';
  const streamLink = `tcp://${streamHost}:${streamPort}`;
  const streamLinkEl = document.getElementById('stream-link');
  streamLinkEl.textContent = streamLink;
  streamLinkEl.href = streamLink;
  const recorder = data.recorder_summary || {};
  const recorderEl = document.getElementById('recorder');
  recorderEl.textContent = recorder.message || 'Recording status: unknown';
  recorderEl.classList.remove('status-active', 'status-inactive');
  if (recorder.state === 'active') {
    recorderEl.classList.add('status-active');
  } else if (recorder.state === 'inactive') {
    recorderEl.classList.add('status-inactive');
  }
  document.getElementById('log').textContent = data.log_tail || '';
}

async function fetchFiles() {
  const res = await fetch('/files');
  const data = await res.json();
  const tbody = document.getElementById('files');
  tbody.innerHTML = '';
  data.files.forEach(file => {
    const row = document.createElement('tr');
    const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
    const downloadUrl = `/download?name=${encodeURIComponent(file.name)}`;
    row.innerHTML = `<td>${file.name}</td><td>${sizeMb}</td><td>${file.mtime}</td><td><a href="${downloadUrl}">Download</a></td>`;
    tbody.appendChild(row);
  });
}

async function runConcat() {
  const res = await fetch('/run-concat', { method: 'POST' });
  if (res.status === 409) {
    alert('Concat is already running.');
  }
  await fetchStatus();
}

document.getElementById('run').addEventListener('click', runConcat);
document.getElementById('stop-concat').addEventListener('click', async () => {
  const res = await fetch('/stop-concat', { method: 'POST' });
  const data = await res.json();
  if (!data.ok) {
    alert(data.message || 'Stop request failed.');
  }
  await fetchStatus();
});

let cleanupPrefixes = [];

document.getElementById('review-cleanup').addEventListener('click', async () => {
  const res = await fetch('/cleanup-plan');
  const data = await res.json();
  const list = document.getElementById('cleanup-list');
  const blocked = document.getElementById('cleanup-blocked');
  const warning = document.getElementById('cleanup-warning');
  list.innerHTML = '';
  cleanupPrefixes = [];
  if (data.candidates && data.candidates.length) {
    data.candidates.forEach(item => {
      cleanupPrefixes.push(item.prefix);
      item.chunks.forEach(chunk => {
        const li = document.createElement('li');
        li.textContent = chunk.split('/').pop();
        list.appendChild(li);
      });
    });
    blocked.textContent = '';
  } else {
    const li = document.createElement('li');
    li.textContent = 'No MKV chunks eligible for cleanup.';
    list.appendChild(li);
  }
  if (data.blocked && data.blocked.length) {
    blocked.textContent = `Blocked: ${data.blocked.map(item => `${item.prefix} (${item.reason})`).join('; ')}`;
  } else {
    blocked.textContent = '';
  }
  warning.style.display = 'block';
  document.getElementById('confirm-cleanup').disabled = cleanupPrefixes.length === 0;
});

document.getElementById('confirm-cleanup').addEventListener('click', async () => {
  if (!cleanupPrefixes.length) {
    return;
  }
  const confirmDelete = confirm(`Delete ${cleanupPrefixes.length} recording groups of MKV chunks? This cannot be undone.`);
  if (!confirmDelete) {
    return;
  }
  const res = await fetch('/cleanup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prefixes: cleanupPrefixes })
  });
  const data = await res.json();
  if (!data.ok) {
    alert(data.message || 'Cleanup failed.');
  } else {
    alert(`Deleted ${data.deleted.length} MKV files. Skipped ${data.skipped.length} groups.`);
  }
  cleanupPrefixes = [];
  document.getElementById('confirm-cleanup').disabled = true;
  await fetchFiles();
});

document.getElementById('confirm-cleanup-all').addEventListener('click', async () => {
  const confirmDelete = confirm('SERIOUS WARNING: This will permanently delete ALL recordings, including MP4 files. This cannot be undone.');
  if (!confirmDelete) {
    return;
  }
  const typed = prompt('Type DELETE ALL to confirm permanently deleting every recording file.');
  if (typed !== 'DELETE ALL') {
    alert('Cleanup all canceled. Confirmation phrase did not match.');
    return;
  }
  const res = await fetch('/cleanup-all', { method: 'POST' });
  const data = await res.json();
  if (!data.ok) {
    alert(data.message || 'Cleanup all failed.');
    return;
  }
  alert(`Deleted ${data.deleted.length} files. Skipped ${data.skipped.length} files.`);
  await fetchFiles();
});

async function controlService(target, action) {
  const res = await fetch('/service', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ service: target, action })
  });
  const data = await res.json();
  if (!data.ok) {
    alert(data.message || 'Service action failed.');
  }
  await fetchStatus();
}

document.getElementById('recorder-start').addEventListener('click', () => controlService('recorder', 'start'));
document.getElementById('recorder-stop').addEventListener('click', () => controlService('recorder', 'stop'));

fetchStatus();
fetchFiles();
setInterval(fetchStatus, 5000);
setInterval(fetchFiles, 15000);
</script>
</body>
</html>
"""


def render_index():
    return INDEX_HTML.replace("__HOSTNAME__", HOSTNAME)


def main():
    server = ThreadedHTTPServer((HOST, PORT), Handler)
    print(f"TheraView web viewer running on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
