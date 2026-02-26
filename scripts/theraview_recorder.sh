#!/bin/bash
#
# TheraView USB Camera Recorder Supervisor
# Crash-safe version using FFmpeg + MediaMTX with segmented MPEG-TS recording
#

set -u
set -o pipefail

CAMERA=${CAMERA:-/dev/video0}
OUTDIR=${OUTDIR:-/home/pi/TheraView/recordings}
LOGDIR=${LOGDIR:-/home/pi/TheraView/logs}

RECORD_WIDTH=${RECORD_WIDTH:-1920}
RECORD_HEIGHT=${RECORD_HEIGHT:-1080}
FRAMERATE=${FRAMERATE:-30}
RECORD_BITRATE=${RECORD_BITRATE:-6000000}   # bps

ROTATE_SECONDS=${ROTATE_SECONDS:-300}   # 5 minutes

STREAM_BITRATE=${STREAM_BITRATE:-6000000}   # bps
RTSP_HOST=${RTSP_HOST:-127.0.0.1}
RTSP_PORT=${RTSP_PORT:-8554}
RTSP_PATH=${RTSP_PATH:-live}

HOSTNAME=$(hostname)

mkdir -p "$OUTDIR" "$LOGDIR"

cpu_temp_c() {
  if [ -r /sys/class/thermal/thermal_zone0/temp ]; then
    awk '{printf "%.1f", $1/1000}' /sys/class/thermal/thermal_zone0/temp
    return
  fi
  echo "n/a"
}

throttle_status() {
  if command -v vcgencmd >/dev/null 2>&1; then
    vcgencmd get_throttled 2>/dev/null | sed 's/^throttled=//'
    return
  fi
  echo "n/a"
}

loadavg_1m() {
  awk '{print $1}' /proc/loadavg 2>/dev/null || echo "n/a"
}

log() {
  local cpu_temp throttle loadavg
  cpu_temp=$(cpu_temp_c)
  throttle=$(throttle_status)
  loadavg=$(loadavg_1m)
  echo "$(date '+%Y-%m-%d %H:%M:%S') $1 | cpu_temp_c=${cpu_temp} load1=${loadavg} throttled=${throttle}" | tee -a "$LOGDIR/theraview_recorder.log"
}

run_pipeline() {
  local start_time output_pattern free_space rtsp_url
  start_time=$(date +"%Y-%m-%d_%H-%M-%S")
  output_pattern="$OUTDIR/${HOSTNAME}_${start_time}_%05d.ts"
  free_space=$(df -BG "$OUTDIR" | awk 'NR==2{print $4}')
  rtsp_url="rtsp://${RTSP_HOST}:${RTSP_PORT}/${RTSP_PATH}"

  log "Camera detected, starting recording: $output_pattern"
  log "Publishing RTSP stream to: $rtsp_url (free space ${free_space})"

  ffmpeg -hide_banner -loglevel info -stats \
    -use_wallclock_as_timestamps 1 \
    -f v4l2 -framerate "$FRAMERATE" -video_size "${RECORD_WIDTH}x${RECORD_HEIGHT}" -input_format mjpeg -i "$CAMERA" \
    -vf "scale=in_range=pc:out_range=tv,format=yuv420p" \
    -c:v h264_v4l2m2m -b:v "$RECORD_BITRATE" -maxrate "$STREAM_BITRATE" -bufsize "$((STREAM_BITRATE * 2))" \
    -g "$((FRAMERATE * 2))" -bf 0 \
    -map 0:v:0 \
    -f tee \
    "[f=segment:segment_time=${ROTATE_SECONDS}:segment_format=mpegts:reset_timestamps=1:strftime=0]${output_pattern}|[f=rtsp:rtsp_transport=tcp]${rtsp_url}"
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
