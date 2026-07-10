#!/bin/bash
# Run on Pi: bash ~/captures/pi_preview_loop.sh [camera_index]
# Loops rpicam-still to ~/captures/preview.jpg for live preview.
# Also serves high-res capture requests (from capture_intrinsic.ps1) between
# preview frames, since only one process can hold the camera at a time -
# running rpicam-still separately over SSH while this loop is active fails
# with "Device or resource busy".
# Atomic tmp->rename prevents the laptop reading a half-written file.
# Ctrl+C to stop.

CAM=${1:-0}
PREVIEW=~/captures/preview.jpg
PREVIEW_TMP=~/captures/preview_tmp.jpg
REQUEST=~/captures/capture_request
RESULT=~/captures/capture_result.png
RESULT_TMP=~/captures/capture_result_tmp.png

mkdir -p ~/captures/distance_check

echo "Preview loop started on camera $CAM. Capturing to $PREVIEW"
echo "Ctrl+C to stop."

while true; do
    if [ -f "$REQUEST" ]; then
        rm -f "$REQUEST"
        if rpicam-still --camera "$CAM" --encoding png -o "$RESULT_TMP" --immediate --width 1456 --height 1088 -n 2>/dev/null; then
            mv "$RESULT_TMP" "$RESULT"
        fi
    elif rpicam-still --camera "$CAM" -o "$PREVIEW_TMP" --immediate --width 1456 --height 1088 -n 2>/dev/null; then
        mv "$PREVIEW_TMP" "$PREVIEW"
    fi
done
