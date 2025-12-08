import subprocess
import threading
import datetime
import os
import signal

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

def start_preview_only():
    global preview_proc
    stop_pipelines()
    preview_proc = subprocess.Popen(
        preview_pipeline(),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=0,
    )

def start_record_plus_preview():
    global record_proc, current_filename
    stop_pipelines()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    current_filename = os.path.join(OUTPUT_DIR, f"{BASENAME_PREFIX}{ts}.mp4")
    record_proc = subprocess.Popen(
        record_pipeline(current_filename),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=0,
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
        record_proc = None


def set_recording_state(recording: bool):
    global active_record
    with proc_lock:
        if recording == active_record:
            if recording and record_proc is None:
                start_record_plus_preview()
            elif not recording and preview_proc is None:
                start_preview_only()
            _update_led()
            return active_record

        active_record = recording
        if active_record:
            start_record_plus_preview()
        else:
            start_preview_only()

        _update_led()
        return active_record


def toggle_recording():
    return set_recording_state(not active_record)

def current_pipe():
    if record_proc:
        return record_proc
    return preview_proc
