#!/bin/bash
#
# TheraView USB Camera Recorder Supervisor
# Crash-safe version using Matroska container with live stream
#

set -u
set -o pipefail

CAMERA=${CAMERA:-/dev/video0}
OUTDIR=${OUTDIR:-/home/pi/TheraView/recordings}
LOGDIR=${LOGDIR:-/home/pi/TheraView/logs}

RECORD_WIDTH=${RECORD_WIDTH:-1920}
RECORD_HEIGHT=${RECORD_HEIGHT:-1080}
FRAMERATE=${FRAMERATE:-30}
RECORD_BITRATE=${RECORD_BITRATE:-4000}   # kbps

ROTATE_SECONDS=${ROTATE_SECONDS:-300}   # 5 minutes

STREAM_WIDTH=${STREAM_WIDTH:-1280}
STREAM_HEIGHT=${STREAM_HEIGHT:-720}
STREAM_BITRATE=${STREAM_BITRATE:-1000}   # kbps
STREAM_PORT=${STREAM_PORT:-5000}

HOSTNAME=$(hostname)

mkdir -p "$OUTDIR" "$LOGDIR"

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$LOGDIR/theraview_recorder.log"
}

run_pipeline() {
  local start_time file free_space
  start_time=$(date +"%Y-%m-%d_%H-%M-%S")
  file="$OUTDIR/${HOSTNAME}_${start_time}.mkv"
  free_space=$(df -BG "$OUTDIR" | awk 'NR==2{print $4}')

  log "Camera detected, starting recording: $file"

  gst-launch-1.0 -e \
    v4l2src device="$CAMERA" do-timestamp=true ! \
    image/jpeg,width=$RECORD_WIDTH,height=$RECORD_HEIGHT,framerate=$FRAMERATE/1 ! \
    tee name=t \
      t. ! queue ! \
        jpegdec ! \
        videoconvert ! \
        clockoverlay time-format="%Y-%m-%d %H:%M:%S" ! \
        jpegenc ! \
        splitmuxsink \
          muxer=matroskamux \
          max-size-time=$((ROTATE_SECONDS * 1000000000)) \
          location="$OUTDIR/${HOSTNAME}_${start_time}_%05d.mkv" \
      t. ! queue ! \
        jpegdec ! \
        videoscale ! \
        videoconvert ! \
        clockoverlay time-format="%Y-%m-%d %H:%M:%S" ! \
        textoverlay text="Free: ${free_space}" valignment=top halignment=right font-desc="Sans, 16" shaded-background=true ! \
        video/x-raw,width=$STREAM_WIDTH,height=$STREAM_HEIGHT,framerate=$FRAMERATE/1 ! \
        x264enc \
          tune=zerolatency \
          speed-preset=veryfast \
          bitrate=$STREAM_BITRATE \
          key-int-max=$FRAMERATE \
        ! h264parse ! \
        mpegtsmux ! \
        tcpserversink host=0.0.0.0 port=$STREAM_PORT sync=false
}

while true; do
  while [ ! -e "$CAMERA" ]; do
    log "Camera not present, waiting"
    sleep 2
  done

  run_pipeline

  exit_code=$?
  log "Recording stopped (exit code $exit_code)"

  sleep 2
done
