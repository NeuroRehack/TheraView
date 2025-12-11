import os
import signal
import subprocess
import threading
import datetime

from .video import preview_pipeline, record_pipeline
from .core import OUTPUT_DIR, BASENAME_PREFIX


led_controller = None

proc_lock = threading.Lock()
preview_proc = None
record_proc = None
active_record = False
current_filename = ""


def set_led_controller(controller):
    global led_controller
    led_controller = controller
    _update_led()


def _update_led():
    if led_controller:
        led_controller.set(active_record)


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

def start_preview_only():
    global preview_proc
    stop_pipelines()
    preview_proc = subprocess.Popen(
        preview_pipeline(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

def start_record_plus_preview():
    global record_proc, current_filename
    stop_pipelines()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    current_filename = os.path.join(OUTPUT_DIR, f"{BASENAME_PREFIX}{ts}.mp4")
    record_proc = subprocess.Popen(
        record_pipeline(current_filename),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

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
    global active_record
    with proc_lock:
        if recording == active_record:
            if recording and not _proc_alive(record_proc):
                start_record_plus_preview()
            elif not recording and not _proc_alive(preview_proc):
                start_preview_only()
            active_record = recording and _proc_alive(record_proc)
            _update_led()
            return active_record

        if recording:
            start_record_plus_preview()
            active_record = _proc_alive(record_proc)
            if not active_record:
                print("Recording failed to start; staying in preview mode.")
                start_preview_only()
        else:
            start_preview_only()
            active_record = False

        _update_led()
        return active_record


def toggle_recording():
    return set_recording_state(not active_record)

def status_snapshot():
    """Return a thread-safe view of the pipeline state and heal obvious drifts."""

    global active_record, record_proc, preview_proc

    with proc_lock:
        record_alive = _proc_alive(record_proc)
        preview_alive = _proc_alive(preview_proc)

        # If the record pipeline died unexpectedly, drop back to preview to keep serving.
        if active_record and not record_alive:
            print("Recording pipeline stopped unexpectedly; switching to preview.")
            active_record = False
            record_proc = None
            if not preview_alive:
                start_preview_only()
                preview_alive = _proc_alive(preview_proc)

        # If neither pipeline is alive (e.g., after a crash), bring preview back up.
        if not active_record and not preview_alive:
            start_preview_only()
            preview_alive = _proc_alive(preview_proc)

        _update_led()

        return {
            "record_active": active_record,
            "record_running": record_alive,
            "preview_running": preview_alive,
            "filename": current_filename,
        }
