#!/bin/bash
# Run on Pi: bash ~/captures/pi_preview_loop.sh
# Loops rpicam-still to ~/captures/preview.jpg for live preview.
# Atomic tmp->rename prevents laptop reading a half-written file.
# Ctrl+C to stop.

PREVIEW=~/captures/preview.jpg
PREVIEW_TMP=~/captures/preview_tmp.jpg

mkdir -p ~/captures/distance_check

echo "Preview loop started. Capturing to $PREVIEW"
echo "Ctrl+C to stop."

while true; do
    if rpicam-still --camera 0 -o "$PREVIEW_TMP" --immediate --width 1456 --height 1088 -n 2>/dev/null; then
        mv "$PREVIEW_TMP" "$PREVIEW"
    fi
done
