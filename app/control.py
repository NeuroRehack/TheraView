import os
import re
import signal
import subprocess
import threading
import datetime
import time

from .video import preview_pipeline, record_pipeline
from .core import OUTPUT_DIR, BASENAME_PREFIX


led_controller = None

proc_lock = threading.Lock()
preview_proc = None
record_proc = None
pipelines_enabled = True
active_record = False
record_restart_at = 0.0
current_filename = ""
preview_fps = None
record_fps = None


def set_led_controller(controller):
    global led_controller
    led_controller = controller
    _update_led()


def _update_led():
    if led_controller:
        led_controller.set(active_record and pipelines_enabled and _proc_alive(record_proc))


def _proc_alive(proc):
    return proc is not None and proc.poll() is None


def _flush_record_file():
    """Attempt to flush the current recording file to avoid corruption."""

    if not current_filename or not os.path.exists(current_filename):
        return

    try:
        with open(current_filename, "rb") as f:
            os.fsync(f.fileno())
    except Exception as exc:  # pragma: no cover - best effort
        print(f"Failed to fsync {current_filename}: {exc}")


def _monitor_fps(proc, key):
    global preview_fps, record_fps

    while True:
        line = proc.stderr.readline()
        if not line:
            break

        try:
            text = line.decode("utf-8", errors="ignore")
        except AttributeError:
            text = str(line)

        match = re.search(r"fps:\s*([0-9.]+)", text)
        if not match:
            match = re.search(r"current:\s*([0-9.]+)", text)

        if match:
            try:
                value = float(match.group(1))
            except ValueError:
                continue
            with proc_lock:
                if key == "preview":
                    preview_fps = value
                else:
                    record_fps = value

    with proc_lock:
        if key == "preview":
            preview_fps = None
        else:
            record_fps = None


def _start_monitor_thread(proc, key):
    thread = threading.Thread(target=_monitor_fps, args=(proc, key), daemon=True)
    thread.start()

def start_preview_only():
    global preview_proc
    stop_pipelines()
    preview_proc = subprocess.Popen(
        preview_pipeline(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    _start_monitor_thread(preview_proc, "preview")

def start_record_plus_preview():
    global record_proc, current_filename
    stop_pipelines()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    current_filename = os.path.join(OUTPUT_DIR, f"{BASENAME_PREFIX}{ts}.mp4")
    record_proc = subprocess.Popen(
        record_pipeline(current_filename),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    _start_monitor_thread(record_proc, "record")

def stop_pipelines():
    global preview_proc, record_proc

    if preview_proc is not None:
        try:
            preview_proc.send_signal(signal.SIGINT)
            preview_proc.wait(timeout=5)
        except:
            try:
                preview_proc.terminate()
                preview_proc.wait(timeout=3)
            except:
                preview_proc.kill()
        preview_proc = None

    if record_proc is not None:
        try:
            record_proc.send_signal(signal.SIGINT)
            record_proc.wait(timeout=8)
        except:
            try:
                record_proc.terminate()
                record_proc.wait(timeout=4)
            except:
                record_proc.kill()
        _flush_record_file()
        record_proc = None


def set_recording_state(recording: bool):
    global active_record, record_restart_at
    with proc_lock:
        active_record = recording
        record_restart_at = 0.0

        if not pipelines_enabled:
            _update_led()
            return False

        if recording and _proc_alive(record_proc):
            _update_led()
            return True

        if recording:
            start_record_plus_preview()
            record_alive = _proc_alive(record_proc)
            if not record_alive:
                print("Recording failed to start; staying in preview mode.")
                start_preview_only()
            _update_led()
            return record_alive
        else:
            start_preview_only()
            _update_led()
            return False


def toggle_recording():
    return set_recording_state(not active_record)


def set_pipelines_enabled(enabled: bool):
    global pipelines_enabled, record_restart_at
    with proc_lock:
        if pipelines_enabled == enabled:
            return pipelines_enabled

        pipelines_enabled = enabled
        record_restart_at = 0.0

        if not enabled:
            stop_pipelines()
            _update_led()
            return False

        if active_record:
            start_record_plus_preview()
            if not _proc_alive(record_proc):
                print("Recording failed to start; staying in preview mode.")
                start_preview_only()
        else:
            start_preview_only()

        _update_led()
        return True


def toggle_pipelines():
    return set_pipelines_enabled(not pipelines_enabled)

def current_pipe():
    if _proc_alive(record_proc):
        return record_proc
    if _proc_alive(preview_proc):
        return preview_proc
    return None


def status_snapshot():
    """Return a thread-safe view of the pipeline state and heal obvious drifts."""

    global active_record, record_proc, preview_proc, record_restart_at

    with proc_lock:
        record_alive = _proc_alive(record_proc)
        preview_alive = _proc_alive(preview_proc)

        if not pipelines_enabled:
            if record_alive or preview_alive:
                stop_pipelines()
            record_alive = False
            preview_alive = False
            _update_led()
            return {
                "record_active": active_record,
                "record_running": record_alive,
                "preview_running": preview_alive,
                "filename": current_filename,
                "preview_fps": preview_fps,
                "record_fps": record_fps,
                "pipelines_enabled": pipelines_enabled,
            }

        if active_record:
            if not record_alive:
                now = time.time()
                if now - record_restart_at >= 2.0:
                    print("Recording pipeline stopped unexpectedly; attempting restart.")
                    record_restart_at = now
                    start_record_plus_preview()
                    record_alive = _proc_alive(record_proc)

                if not record_alive and not preview_alive:
                    start_preview_only()
                    preview_alive = _proc_alive(preview_proc)
        else:
            if record_alive:
                stop_pipelines()
                record_alive = False
            if not preview_alive:
                start_preview_only()
                preview_alive = _proc_alive(preview_proc)

        _update_led()

        return {
            "record_active": active_record,
            "record_running": record_alive,
            "preview_running": preview_alive,
            "filename": current_filename,
            "preview_fps": preview_fps,
            "record_fps": record_fps,
            "pipelines_enabled": pipelines_enabled,
        }
