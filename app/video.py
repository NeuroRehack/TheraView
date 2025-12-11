import os
import shutil

from .core import (
    DEVICE,
    FRAMERATE,
    HLS_LIST_SIZE,
    HLS_SEGMENT_TIME,
    RECORD_BITRATE,
    RECORD_HEIGHT,
    RECORD_WIDTH,
    STREAM_BITRATE,
    STREAM_HEIGHT,
    STREAM_TEXT,
    STREAM_WIDTH,
)

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
HLS_DIR = "hls"
PREVIEW_PLAYLIST = os.path.join(HLS_DIR, "preview.m3u8")
RECORD_PLAYLIST = os.path.join(HLS_DIR, "stream.m3u8")
TIMESTAMP_EXPR = "%{localtime\\:%Y-%m-%d %H\\:%M\\:%S}"


def _clean_hls_dir():
    os.makedirs(HLS_DIR, exist_ok=True)
    for name in os.listdir(HLS_DIR):
        path = os.path.join(HLS_DIR, name)
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        except FileNotFoundError:
            continue


def _drawtext(text: str, x: str, y: str, size: int = 20):
    safe_text = text.replace("'", "\\'")
    return (
        "drawtext=fontfile=%(font)s:"
        "fontsize=%(size)d:"
        "fontcolor=white:"
        "text='%(text)s':"
        "x=%(x)s:"
        "y=%(y)s:"
        "borderw=2:"
        "bordercolor=black@0.6" % {"font": FONT_PATH, "size": size, "text": safe_text, "x": x, "y": y}
    )


def _overlay_chain(width: int, height: int, include_label: bool = True, include_clock: bool = True):
    filters = [f"scale={width}:{height}"]
    if include_label:
        filters.append(_drawtext(STREAM_TEXT, "w-tw-10", "10", 22))
    if include_clock:
        filters.append(_drawtext(TIMESTAMP_EXPR, "w-tw-10", "h-th-10", 24))
    return ",".join(filters)


def _common_input():
    return [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "v4l2",
        "-framerate",
        str(FRAMERATE),
        "-video_size",
        f"{RECORD_WIDTH}x{RECORD_HEIGHT}",
        "-i",
        DEVICE,
    ]


def preview_pipeline():
    _clean_hls_dir()
    return _common_input() + [
        "-vf",
        _overlay_chain(STREAM_WIDTH, STREAM_HEIGHT),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-tune",
        "zerolatency",
        "-g",
        str(FRAMERATE),
        "-keyint_min",
        str(FRAMERATE),
        "-pix_fmt",
        "yuv420p",
        "-f",
        "hls",
        "-hls_time",
        str(HLS_SEGMENT_TIME),
        "-hls_list_size",
        str(HLS_LIST_SIZE),
        "-hls_flags",
        "delete_segments+append_list",
        "-hls_segment_filename",
        os.path.join(HLS_DIR, "preview_%03d.ts"),
        PREVIEW_PLAYLIST,
    ]


def record_pipeline(filename):
    _clean_hls_dir()
    record_filters = _overlay_chain(RECORD_WIDTH, RECORD_HEIGHT, include_label=False)
    stream_filters = _overlay_chain(STREAM_WIDTH, STREAM_HEIGHT)
    filter_graph = f"[0:v]{record_filters}[record];[0:v]{stream_filters}[stream]"

    return _common_input() + [
        "-filter_complex",
        filter_graph,
        "-map",
        "[record]",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-tune",
        "zerolatency",
        "-b:v",
        f"{RECORD_BITRATE}k",
        "-g",
        str(FRAMERATE),
        "-keyint_min",
        str(FRAMERATE),
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        filename,
        "-map",
        "[stream]",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-tune",
        "zerolatency",
        "-b:v",
        f"{STREAM_BITRATE}k",
        "-g",
        str(FRAMERATE),
        "-keyint_min",
        str(FRAMERATE),
        "-pix_fmt",
        "yuv420p",
        "-f",
        "hls",
        "-hls_time",
        str(HLS_SEGMENT_TIME),
        "-hls_list_size",
        str(HLS_LIST_SIZE),
        "-hls_flags",
        "delete_segments+append_list",
        "-hls_segment_filename",
        os.path.join(HLS_DIR, "stream_%03d.ts"),
        RECORD_PLAYLIST,
    ]


def current_playlist(recording_active: bool):
    if recording_active and os.path.isfile(RECORD_PLAYLIST):
        return RECORD_PLAYLIST
    return PREVIEW_PLAYLIST if os.path.isfile(PREVIEW_PLAYLIST) else None
