#!/bin/bash
# Run on Pi: bash ~/captures/pi_preview_loop_stereo.sh
# Stereo version of pi_preview_loop.sh - runs one independent preview/capture
# loop per camera (0 and 1), concurrently in the background, so both feeds
# stay live at once for capture_extrinsic.ps1.
#
# Each camera's loop is self-contained (own preview/request/result files) and
# never runs more than one rpicam-still process against its own camera at a
# time, exactly like the single-camera script - so there is no request-vs-
# preview race on a given sensor. Concurrent one-shot captures across the two
# *different* cameras were verified to succeed reliably; only sustained
# tight-loop preview cycling on both at once occasionally logged a transient
# "Device or resource busy" on one frame (harmless - that iteration's preview
# frame is just skipped and the file is left unchanged for the next pass).
# Because of that, capture_extrinsic.ps1 signals the two capture requests
# below SEQUENTIALLY (cam0 then cam1), not simultaneously, to keep the actual
# calibration PNGs contention-free.
#
# Atomic tmp->rename prevents the laptop reading a half-written file.
# Ctrl+C to stop (stops both loops).

mkdir -p ~/captures

run_loop() {
    local CAM=$1
    local PREVIEW=~/captures/preview_cam${CAM}.jpg
    local PREVIEW_TMP=~/captures/preview_cam${CAM}_tmp.jpg
    local REQUEST=~/captures/capture_request_cam${CAM}
    local RESULT=~/captures/capture_result_cam${CAM}.png
    local RESULT_TMP=~/captures/capture_result_cam${CAM}_tmp.png

    while true; do
        if [ -f "$REQUEST" ]; then
            rm -f "$REQUEST"
            if rpicam-still --camera "$CAM" --encoding png -o "$RESULT_TMP" --immediate --width 1456 --height 1088 --shutter 5000 --gain 4.0 -n 2>/dev/null; then
                mv "$RESULT_TMP" "$RESULT"
            fi
        elif rpicam-still --camera "$CAM" -o "$PREVIEW_TMP" --immediate --width 1456 --height 1088 --shutter 5000 --gain 4.0 -n 2>/dev/null; then
            mv "$PREVIEW_TMP" "$PREVIEW"
        fi
    done
}

echo "Stereo preview loop started on cameras 0 and 1."
echo "Preview: ~/captures/preview_cam0.jpg and ~/captures/preview_cam1.jpg"
echo "Ctrl+C to stop."

run_loop 0 &
PID0=$!
run_loop 1 &
PID1=$!

trap 'kill "$PID0" "$PID1" 2>/dev/null' EXIT
wait
