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
STREAM_PORT = int(os.environ.get("RTSP_PORT", os.environ.get("STREAM_PORT", "8554")))
STREAM_PATH = os.environ.get("RTSP_PATH", "live")
LIVE_VIEW_PORT = int(os.environ.get("LIVE_VIEW_PORT", "8888"))
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


def validate_manual_time(value):
    if not isinstance(value, str):
        return None
    normalized = value.strip().replace("T", " ")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", normalized):
        return None
    return normalized


def set_system_time(manual_time):
    normalized = validate_manual_time(manual_time)
    if not normalized:
        return {
            "ok": False,
            "message": "Invalid time format. Use YYYY-MM-DD HH:MM:SS.",
        }
    try:
        date_result = subprocess.run(
            ["sudo", "date", "-s", normalized],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "message": str(exc)}
    if date_result.returncode != 0:
        message = date_result.stderr.strip() or date_result.stdout.strip() or "date command failed."
        return {"ok": False, "message": message}

    try:
        rtc_result = subprocess.run(
            ["sudo", "hwclock", "-w"],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "message": f"System time set, but RTC write failed: {exc}"}

    if rtc_result.returncode != 0:
        message = rtc_result.stderr.strip() or rtc_result.stdout.strip() or "hwclock command failed."
        return {"ok": False, "message": f"System time set, but RTC write failed: {message}"}

    return {"ok": True, "message": f"System time set to {normalized} and written to RTC.", "time": normalized}


def get_cpu_temp_c():
    temp_path = "/sys/class/thermal/thermal_zone0/temp"
    if not os.path.exists(temp_path):
        return None
    try:
        with open(temp_path, "r", encoding="utf-8") as handle:
            milli_c = int(handle.read().strip())
    except (OSError, ValueError):
        return None
    return milli_c / 1000.0


def parse_throttle_flags(hex_value):
    flags = []
    flag_map = {
        0: "under-voltage",
        1: "arm frequency capped",
        2: "currently throttled",
        3: "soft temperature limit active",
        16: "under-voltage has occurred",
        17: "arm frequency capping has occurred",
        18: "throttling has occurred",
        19: "soft temperature limit has occurred",
    }
    for bit, label in flag_map.items():
        if hex_value & (1 << bit):
            flags.append(label)
    return flags


def get_throttle_status():
    output = run_command(["vcgencmd", "get_throttled"])
    if not output:
        return {"available": False, "raw": None, "flags": []}
    raw = output.split("=", 1)[-1].strip()
    try:
        value = int(raw, 16)
    except ValueError:
        return {"available": True, "raw": raw, "flags": []}
    return {"available": True, "raw": raw, "flags": parse_throttle_flags(value)}


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
    converted_tag = "_converted.ts"
    prefixes = {}
    for name in os.listdir(OUTDIR):
        if not name.endswith(converted_tag):
            continue
        match = re.match(r"^(.*)_[0-9]{5}_converted\.ts$", name)
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


def delete_segment_chunks(prefixes):
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


def list_log_files():
    entries = []
    for name in sorted(os.listdir(LOGDIR)):
        path = os.path.join(LOGDIR, name)
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


def remove_recording_file(name):
    safe_name = os.path.basename(name)
    if safe_name != name:
        return {"ok": False, "message": "Invalid file name."}
    path = os.path.join(OUTDIR, safe_name)
    if not os.path.isfile(path):
        return {"ok": False, "message": "File not found."}
    try:
        os.remove(path)
    except OSError as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "deleted": safe_name}


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
            status["cpu_usage"] = get_cpu_usage_percent()
            status["cpu_temp_c"] = get_cpu_temp_c()
            status["throttle"] = get_throttle_status()
            status["clock_time"] = get_clock_time()
            status["rtc"] = get_rtc_status()
            recorder_service = get_service_status(RECORDER_SERVICE)
            status["recorder_service"] = recorder_service
            status["recorder_summary"] = get_recorder_summary(recorder_service)
            status["hostname"] = HOSTNAME
            status["wifi"] = get_wifi_info()
            status["network"] = get_primary_ip_info()
            status["stream_port"] = STREAM_PORT
            status["stream_path"] = STREAM_PATH
            status["live_view_port"] = LIVE_VIEW_PORT
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
        if parsed.path == "/log-files":
            self._send_json({"files": list_log_files()})
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
        if parsed.path == "/log-open":
            params = parse_qs(parsed.query)
            name = params.get("name", [None])[0]
            if not name:
                self.send_error(HTTPStatus.BAD_REQUEST, "Missing name")
                return
            safe_name = os.path.basename(name)
            if safe_name != name:
                self.send_error(HTTPStatus.BAD_REQUEST, "Invalid name")
                return
            path = os.path.join(LOGDIR, safe_name)
            if not os.path.isfile(path):
                self.send_error(HTTPStatus.NOT_FOUND, "Not found")
                return
            try:
                with open(path, "rb") as handle:
                    data = handle.read()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Disposition", f'inline; filename="{safe_name}"')
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
            result = delete_segment_chunks(prefixes)
            self._send_json({"ok": True, **result})
            return
        if parsed.path == "/delete-file":
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
            name = payload.get("name")
            if not isinstance(name, str) or not name:
                self._send_json(
                    {"ok": False, "message": "Missing file name."},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return
            result = remove_recording_file(name)
            status_code = HTTPStatus.OK if result.get("ok") else HTTPStatus.BAD_REQUEST
            self._send_json(result, status=status_code)
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
        if parsed.path == "/set-time":
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
            requested_time = payload.get("time")
            result = set_system_time(requested_time)
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
    .time-set { margin-bottom: 0.9rem; display: grid; gap: 0.45rem; }
    .time-set label { color: var(--text); font-weight: 600; }
    .time-set input { padding: 0.5rem; border-radius: 8px; border: 1px solid var(--border); }
    #set-time-status { font-size: 0.9rem; }
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
        <div class=\"time-set\">
          <label for=\"manual-time\">Set System Time</label>
          <input id=\"manual-time\" type=\"datetime-local\" step=\"1\" />
          <button id=\"set-time\" class=\"secondary\">Apply Time</button>
          <p id=\"set-time-status\">Manual time update not run yet.</p>
        </div>
        <p id=\"clock\">Clock: --</p>
        <p id=\"rtc\">RTC: --</p>
        <p id=\"cpu\">CPU Usage: --</p>
        <p id=\"cpu-temp\">CPU Temp: --</p>
        <p id=\"throttle\">Throttle: --</p>
        <p id=\"wifi\">Wi-Fi: --</p>
        <p id=\"ip\">IP: --</p>
        <p><strong>Main Live View:</strong> <a id=\"stream-link\" href=\"#\" target=\"_blank\" rel=\"noopener\">http://--:8888/live/</a></p>
        <p>VLC (RTSP): <a id=\"stream-link-rtsp\" href=\"#\" target=\"_blank\" rel=\"noopener\">rtsp://--:8554/live</a></p>
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
        <h3>MP4 Processing</h3>
        <div class=\"button-row\">
          <button id=\"run\">Create Checked MP4</button>
          <button id=\"stop-concat\" class=\"secondary\">Stop MP4 Processing</button>
        </div>
        <p id=\"status\">Status: idle</p>
        <p id=\"timing\">Start: -- | End: -- | Elapsed: --</p>
      </div>
    </div>
    <section class="section">
      <h2>Files</h2>
      <table>
        <thead>
          <tr><th>Name</th><th>Size (MB)</th><th>Modified</th><th>Download</th><th>Delete</th></tr>
        </thead>
        <tbody id=\"files\"></tbody>
      </table>
    </section>
    <section class=\"section\">
      <h2>Log Files</h2>
      <table>
        <thead>
          <tr><th>Name</th><th>Size (KB)</th><th>Modified</th><th>Open</th></tr>
        </thead>
        <tbody id=\"log-files\"></tbody>
      </table>
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
  const cpuTemp = data.cpu_temp_c;
  const tempText = cpuTemp === null || cpuTemp === undefined ? 'n/a' : `${cpuTemp.toFixed(1)}°C`;
  document.getElementById('cpu-temp').textContent = `CPU Temp: ${tempText}`;
  const throttle = data.throttle || {};
  let throttleText = 'unavailable';
  if (throttle.available) {
    if (throttle.flags && throttle.flags.length) {
      throttleText = `${throttle.raw || 'unknown'} (${throttle.flags.join(', ')})`;
    } else {
      throttleText = `${throttle.raw || '0x0'} (ok)`;
    }
  }
  document.getElementById('throttle').textContent = `Throttle: ${throttleText}`;
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
  const liveViewPort = data.live_view_port || 8888;
  const streamPath = data.stream_path || "live";
  const streamHost = network.ip || data.hostname || '0.0.0.0';
  const streamLink = `http://${streamHost}:${liveViewPort}/${streamPath}/`;
  const streamLinkEl = document.getElementById('stream-link');
  streamLinkEl.textContent = streamLink;
  streamLinkEl.href = streamLink;
  const rtspPort = data.stream_port || 8554;
  const rtspLink = `rtsp://${streamHost}:${rtspPort}/${streamPath}`;
  const rtspLinkEl = document.getElementById('stream-link-rtsp');
  rtspLinkEl.textContent = rtspLink;
  rtspLinkEl.href = rtspLink;
  const recorder = data.recorder_summary || {};
  const recorderEl = document.getElementById('recorder');
  recorderEl.textContent = recorder.message || 'Recording status: unknown';
  recorderEl.classList.remove('status-active', 'status-inactive');
  if (recorder.state === 'active') {
    recorderEl.classList.add('status-active');
  } else if (recorder.state === 'inactive') {
    recorderEl.classList.add('status-inactive');
  }
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
    row.innerHTML = `<td>${file.name}</td><td>${sizeMb}</td><td>${file.mtime}</td><td><a href="${downloadUrl}">Download</a></td><td><button class="danger" data-delete-file="${file.name}">Delete</button></td>`;
    tbody.appendChild(row);
  });

  document.querySelectorAll('[data-delete-file]').forEach((button) => {
    button.addEventListener('click', async () => {
      const fileName = button.getAttribute('data-delete-file');
      const confirmDelete = confirm(`Delete file ${fileName}? This cannot be undone.`);
      if (!confirmDelete) {
        return;
      }
      const res = await fetch('/delete-file', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: fileName })
      });
      const data = await res.json();
      if (!data.ok) {
        alert(data.message || 'Delete failed.');
        return;
      }
      await fetchFiles();
    });
  });
}

async function fetchLogFiles() {
  const res = await fetch('/log-files');
  const data = await res.json();
  const tbody = document.getElementById('log-files');
  tbody.innerHTML = '';
  data.files.forEach(file => {
    const row = document.createElement('tr');
    const sizeKb = (file.size / 1024).toFixed(1);
    const openUrl = `/log-open?name=${encodeURIComponent(file.name)}`;
    row.innerHTML = `<td>${file.name}</td><td>${sizeKb}</td><td>${file.mtime}</td><td><a href="${openUrl}" target="_blank" rel="noopener">Open</a></td>`;
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

document.getElementById('set-time').addEventListener('click', async () => {
  const input = document.getElementById('manual-time');
  const statusEl = document.getElementById('set-time-status');
  const value = (input.value || '').trim();
  if (!value) {
    statusEl.textContent = 'Please choose a date and time first.';
    return;
  }
  const normalized = value.replace('T', ' ');
  const formatted = normalized.length === 16 ? `${normalized}:00` : normalized;
  const res = await fetch('/set-time', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ time: formatted })
  });
  const data = await res.json();
  statusEl.textContent = data.message || 'Time update completed.';
  if (!data.ok) {
    alert(data.message || 'Failed to set time.');
  }
  await fetchStatus();
});

fetchStatus();
fetchFiles();
fetchLogFiles();
setInterval(fetchStatus, 5000);
setInterval(fetchFiles, 15000);
setInterval(fetchLogFiles, 15000);
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
