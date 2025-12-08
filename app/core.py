import os
import socket

CONFIG_FILE = "config.conf"

def load_config(path):
    cfg = {}
    if not os.path.isfile(path):
        print("Config file not found. Using defaults.")
        return cfg
    with open(path, "r") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if "=" in s:
                k, v = s.split("=", 1)
                cfg[k.strip()] = v.strip()
    return cfg

CFG = load_config(CONFIG_FILE)

def cfg_str(key, default):
    return CFG.get(key, default)

def cfg_int(key, default):
    try:
        return int(CFG.get(key, default))
    except:
        return default

def cfg_bool(key, default):
    v = CFG.get(key, None)
    if v is None:
        return default
    return v.lower() in ["true", "1", "yes"]


DEVICE = cfg_str("DEVICE", "/dev/video0")
OUTPUT_DIR = cfg_str("OUTPUT_DIR", "recordings")

RECORD_WIDTH = cfg_int("RECORD_WIDTH", 1920)
RECORD_HEIGHT = cfg_int("RECORD_HEIGHT", 1080)

STREAM_WIDTH = cfg_int("STREAM_WIDTH", 640)
STREAM_HEIGHT = cfg_int("STREAM_HEIGHT", 480)

FRAMERATE = cfg_int("FRAMERATE", 30)
RECORD_BITRATE = cfg_int("RECORD_BITRATE", 8000)

ENABLE_SYSTEMD = cfg_bool("ENABLE_SYSTEMD", True)
ENABLE_HOTSPOT = cfg_bool("ENABLE_HOTSPOT", True)
LED_PIN = cfg_int("LED_PIN", 21)

hostname = socket.gethostname().lower()

def is_TVA():
    return hostname.startswith("tva")

def is_TVB():
    return hostname.startswith("tvb")


BASENAME_PREFIX = "TVX"
STREAM_TEXT = "TheraView X"
PORT = 5003

if is_TVA():
    BASENAME_PREFIX = cfg_str("BASENAME_PREFIX_A", "TVA")
    STREAM_TEXT = cfg_str("STREAM_TEXT_A", "TheraView A")
    PORT = cfg_int("PORT_A", 5001)
elif is_TVB():
    BASENAME_PREFIX = cfg_str("BASENAME_PREFIX_B", "TVB")
    STREAM_TEXT = cfg_str("STREAM_TEXT_B", "TheraView B")
    PORT = cfg_int("PORT_B", 5002)


def get_network_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except:
        return None
    finally:
        s.close()


def get_free_space_gb():
    st = os.statvfs("/")
    free_bytes = st.f_bavail * st.f_frsize
    return free_bytes / (1024 * 1024 * 1024)
