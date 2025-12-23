from .core import (
    DEVICE, RECORD_WIDTH, RECORD_HEIGHT, STREAM_WIDTH, STREAM_HEIGHT,
    FRAMERATE, PREVIEW_FRAMERATE, RECORD_BITRATE, STREAM_TEXT
)

def preview_pipeline():
    return [
        "gst-launch-1.0", "-e", "-q",
        "v4l2src", f"device={DEVICE}", "io-mode=dmabuf",
        "!", f"image/jpeg,width={RECORD_WIDTH},height={RECORD_HEIGHT},framerate={PREVIEW_FRAMERATE}/1",
        "!", "jpegdec",
        "!", "videoconvert",
        "!", "tee", "name=t",

        "t.", "!", "queue", "leaky=2", "max-size-buffers=90", "max-size-bytes=0", "max-size-time=0",
        "!", "videoscale",
        "!", f"video/x-raw,width={STREAM_WIDTH},height={STREAM_HEIGHT},framerate={PREVIEW_FRAMERATE}/1",
        "!", "videoconvert",
        "!", "clockoverlay", "font-desc=Sans 16", "halignment=right", "valignment=bottom",
        "draw-outline=true", "color=0xFFFFFFFF", "outline-color=0xFF000000",
        "!", "textoverlay", f"text={STREAM_TEXT}", "valignment=top", "halignment=right",
        "font-desc=Sans, 16", "draw-outline=true", "color=0xFFFFFFFF", "outline-color=0xFF000000",
        "!", "queue", "leaky=2", "max-size-buffers=45", "max-size-bytes=0", "max-size-time=0",
        "!", "jpegenc",
        "!", "multipartmux", "boundary=frame",
        "!", "filesink", "location=/dev/stdout",

        "t.", "!", "queue", "leaky=2", "max-size-buffers=30", "max-size-bytes=0", "max-size-time=0",
        "!", "videorate", f"max-rate={PREVIEW_FRAMERATE}", "drop-only=true",
        "!", "fpsdisplaysink", "text-overlay=false", "video-sink=fakesink", "sync=false", "fps-update-interval=1000",
    ]


from .core import BASENAME_PREFIX

def record_pipeline(filename):
    return [
        "gst-launch-1.0", "-e", "-q",
        "v4l2src", f"device={DEVICE}", "io-mode=dmabuf",
        "!", f"image/jpeg,width={RECORD_WIDTH},height={RECORD_HEIGHT},framerate={FRAMERATE}/1",
        "!", "jpegdec",
        "!", "videoconvert",
        "!", "clockoverlay", "time-format=%Y-%m-%d %H:%M:%S", "font-desc=Sans 18",
        "halignment=right", "valignment=bottom", "draw-outline=true", "color=0xFFFFFFFF",
        "outline-color=0xFF000000",
        "!", "videoconvert",
        "!", "tee", "name=t",

        "t.", "!", "queue", "max-size-buffers=240", "max-size-bytes=0", "max-size-time=0",
        "!", "videoconvert",
        "!", "x264enc",
        f"bitrate={RECORD_BITRATE}",
        "speed-preset=ultrafast",
        "tune=zerolatency",
        f"key-int-max={FRAMERATE}",
        "threads=0",
        "!", "queue", "max-size-time=2000000000", "max-size-bytes=0", "max-size-buffers=0",
        "!", "h264parse",
        "!", "queue", "max-size-time=2000000000", "max-size-bytes=0", "max-size-buffers=0",
        "!", "mp4mux", "faststart=true",
        "!", "filesink", f"location={filename}",

        "t.", "!", "queue", "leaky=2", "max-size-buffers=60", "max-size-bytes=0", "max-size-time=0",
        "!", "videoscale",
        "!", f"video/x-raw,width={STREAM_WIDTH},height={STREAM_HEIGHT},framerate={PREVIEW_FRAMERATE}/1",
        "!", "videoconvert",
        "!", "timeoverlay", "font-desc=Sans 16", "halignment=left", "valignment=bottom", "color=0xFFFF0000",
        "!", "textoverlay", f"text={STREAM_TEXT}", "valignment=top", "halignment=right",
        "font-desc=Sans, 16", "draw-outline=true", "color=0xFFFFFFFF",
        "outline-color=0xFF000000",
        "!", "jpegenc",
        "!", "multipartmux", "boundary=frame",
        "!", "filesink", "location=/dev/stdout",

        "t.", "!", "queue", "leaky=2", "max-size-buffers=30", "max-size-bytes=0", "max-size-time=0",
        "!", "videorate", f"max-rate={PREVIEW_FRAMERATE}", "drop-only=true",
        "!", "fpsdisplaysink", "text-overlay=false", "video-sink=fakesink", "sync=false", "fps-update-interval=1000",
    ]
