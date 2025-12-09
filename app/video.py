from .core import (
    DEVICE, RECORD_WIDTH, RECORD_HEIGHT, STREAM_WIDTH, STREAM_HEIGHT,
    FRAMERATE, RECORD_BITRATE, STREAM_TEXT
)

def preview_pipeline():
    return [
        "gst-launch-1.0", "-e", "-q",
        "v4l2src", f"device={DEVICE}", "io-mode=dmabuf",
        "!", f"image/jpeg,width={RECORD_WIDTH},height={RECORD_HEIGHT},framerate={FRAMERATE}/1",
        "!", "jpegdec",
        "!", "videoscale",
        "!", f"video/x-raw,width={STREAM_WIDTH},height={STREAM_HEIGHT},framerate={FRAMERATE}/1",
        "!", "videoconvert",
        "!", "clockoverlay", "font-desc=Sans 16", "halignment=right", "valignment=bottom",
        "draw-outline=true", "color=0xFFFFFFFF", "outline-color=0xFF000000",
        "!", "textoverlay", f"text={STREAM_TEXT}", "valignment=top", "halignment=right",
        "font-desc=Sans, 16", "draw-outline=true", "color=0xFFFFFFFF", "outline-color=0xFF000000",
        "!", "jpegenc",
        "!", "multipartmux", "boundary=frame",
        "!", "filesink", "location=/dev/stdout",
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

        "t.", "!", "queue",
        "!", "videoconvert",
        "!", "x264enc",
        f"bitrate={RECORD_BITRATE}",
        "speed-preset=ultrafast",
        "tune=zerolatency",
        f"key-int-max={FRAMERATE}",
        "!", "h264parse",
        "!", "mp4mux", "faststart=true",
        "!", "filesink", f"location={filename}",

        "t.", "!", "queue",
        "!", "videoscale",
        "!", f"video/x-raw,width={STREAM_WIDTH},height={STREAM_HEIGHT},framerate={FRAMERATE}/1",
        "!", "videoconvert",
        "!", "timeoverlay", "font-desc=Sans 16", "halignment=left", "valignment=bottom", "color=0xFFFF0000",
        "!", "textoverlay", f"text={STREAM_TEXT}", "valignment=top", "halignment=right",
        "font-desc=Sans, 16", "draw-outline=true", "color=0xFFFFFFFF",
        "outline-color=0xFF000000",
        "!", "jpegenc",
        "!", "multipartmux", "boundary=frame",
        "!", "filesink", "location=/dev/stdout",
    ]
