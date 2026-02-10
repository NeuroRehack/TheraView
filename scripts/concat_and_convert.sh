#!/bin/bash
#
# Concatenate sequential MKV segments, convert to MP4, validate, and cleanup.
#

set -u
set -o pipefail

OUTDIR=${OUTDIR:-/home/pi/TheraView/recordings}
LOGDIR=${LOGDIR:-/home/pi/TheraView/logs}
FFPROBE=${FFPROBE:-ffprobe}
FFMPEG=${FFMPEG:-ffmpeg}

mkdir -p "$OUTDIR" "$LOGDIR"

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$LOGDIR/concat_and_convert.log"
}

is_healthy_mp4() {
  local file="$1"
  if [ ! -f "$file" ]; then
    return 1
  fi
  local duration
  duration=$($FFPROBE -v error -show_entries format=duration -of default=nw=1:nk=1 "$file" 2>/dev/null || true)
  if [ -z "$duration" ]; then
    return 1
  fi
  local duration_int=${duration%.*}
  if [ "$duration_int" -lt 1 ]; then
    return 1
  fi
  return 0
}

# Find base prefixes for mkv chunks like HOST_YYYY-mm-dd_HH-MM-SS_00001.mkv
mapfile -t prefixes < <(
  find "$OUTDIR" -maxdepth 1 -type f -name "*.mkv" \
    -printf "%f\n" \
    | sed -E 's/_[0-9]{5}\.mkv$//' \
    | sort -u
)

for prefix in "${prefixes[@]}"; do
  mapfile -t chunks < <(
    find "$OUTDIR" -maxdepth 1 -type f -name "${prefix}_[0-9][0-9][0-9][0-9][0-9].mkv" \
      -printf "%p\n" \
      | sort
  )

  if [ ${#chunks[@]} -eq 0 ]; then
    continue
  fi

  concat_list=$(mktemp)
  for chunk in "${chunks[@]}"; do
    printf "file '%s'\n" "$chunk" >> "$concat_list"
  done

  output_mp4="$OUTDIR/${prefix}.mp4"
  checked_mp4="$OUTDIR/${prefix}.checked.mp4"

  if is_healthy_mp4 "$checked_mp4"; then
    log "Healthy MP4 already exists for $prefix ($checked_mp4). Skipping."
    for chunk in "${chunks[@]}"; do
      tagged_chunk="${chunk%.mkv}_converted.mkv"
      if [ "$chunk" != "$tagged_chunk" ]; then
        mv -f "$chunk" "$tagged_chunk"
      fi
    done
    continue
  fi

  if is_healthy_mp4 "$output_mp4"; then
    log "Existing MP4 passed health check for $prefix. Renaming to $checked_mp4"
    mv -f "$output_mp4" "$checked_mp4"
    for chunk in "${chunks[@]}"; do
      tagged_chunk="${chunk%.mkv}_converted.mkv"
      if [ "$chunk" != "$tagged_chunk" ]; then
        mv -f "$chunk" "$tagged_chunk"
      fi
    done
    continue
  fi

  log "Concatenating ${#chunks[@]} chunks into $output_mp4"

  if ! "$FFMPEG" -hide_banner -loglevel error -f concat -safe 0 -i "$concat_list" \
    -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 192k "$output_mp4"; then
    log "ffmpeg concat/compress failed for $prefix"
    rm -f "$concat_list"
    continue
  fi

  rm -f "$concat_list"

  if ! is_healthy_mp4 "$output_mp4"; then
    log "Health check failed for $output_mp4"
    continue
  fi

  log "MP4 health check confirmed. Renaming to $checked_mp4"
  mv -f "$output_mp4" "$checked_mp4"
  for chunk in "${chunks[@]}"; do
    tagged_chunk="${chunk%.mkv}_converted.mkv"
    if [ "$chunk" != "$tagged_chunk" ]; then
      mv -f "$chunk" "$tagged_chunk"
    fi
  done

done
