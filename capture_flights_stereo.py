#!/usr/bin/env python3
"""capture_flights_stereo.py  -  RUNS ON THE PI.

Stereo version of capture_flights.py. Captures a burst from BOTH cameras into
RAM, logs EVERY frame's SensorTimestamp per camera (UNPAIRED), and on keep
writes per-camera PNGs plus a per-flight timestamp CSV.

DESIGN (agreed):
  - Capture is DUMB: no pairing, no sync correction here. It only records raw
    frames + raw SensorTimestamps for each camera independently.
  - Pairing (nearest timestamp) and the ~7 ms residual centroid correction are
    done downstream in triangulate.py, using the per-flight timestamp CSV.
  - Frames are collected via post_callback (NOT capture_array in a loop), so
    every frame each sensor produces is logged with its true exposure timestamp.
    Sequential capture_array calls would inject uncontrolled software latency and
    break timestamp-based pairing.

Per flight:
  Enter -> 3s countdown -> BURST_SECONDS burst into RAM (both cams)
  -> frame-rate sanity check per camera
  -> y keep (write PNGs + timestamps.csv) / n discard / q quit

Locked settings from exposure test: ExposureTime=5000us, AnalogueGain=4.0.
Lossless PNG (required for adjacent-frame differencing).

Output layout (per kept flight):
  ~/captures/<SESSION>/flight_NN/
      cam0/frame_000.png ...
      cam1/frame_000.png ...
      timestamps.csv        # cam, frame_index, sensor_timestamp_ns
"""
import time
import re
import csv
from pathlib import Path
import cv2
import numpy as np
from picamera2 import Picamera2

# --- Locked settings ---
EXPOSURE = 5000          # microseconds
GAIN     = 4.0
WIDTH, HEIGHT = 1456, 1088
TARGET_FPS    = 60
FRAME_PERIOD_MS = 1000.0 / TARGET_FPS
BURST_SECONDS = 5.0
COUNTDOWN_S   = 3
SESSION_NAME  = "2026-07-14_gym_stereo_arc"     # <-- EDIT per session
# ------------------------

session_dir = Path.home() / "captures" / SESSION_NAME
session_dir.mkdir(parents=True, exist_ok=True)


def next_flight_number(d: Path) -> int:
    nums = []
    for p in d.iterdir():
        if p.is_dir():
            m = re.fullmatch(r"flight_(\d+)", p.name)
            if m:
                nums.append(int(m.group(1)))
    return (max(nums) + 1) if nums else 1


def list_session(d: Path):
    print(f"\n--- contents of {d.name} ---")
    entries = sorted(p.name for p in d.iterdir())
    for e in entries:
        print(f"   {e}")
    if not entries:
        print("   (empty)")
    print("---------------------------")


def intra_mean_ms(ts_ns):
    if len(ts_ns) < 2:
        return 0.0
    d = [(ts_ns[i+1] - ts_ns[i]) / 1e6 for i in range(len(ts_ns) - 1)]
    return sum(d) / len(d)


# --- Camera setup (both cams, hard-locked 60 fps) ---
frame_us = int(1_000_000 / TARGET_FPS)
controls = {
    "FrameDurationLimits": (frame_us, frame_us),   # forces 60 fps
    "ExposureTime": EXPOSURE,
    "AnalogueGain": GAIN,
}

print("Initialising cameras...")
cam0 = Picamera2(camera_num=0)   # bus 6 (right, per context)
cam1 = Picamera2(camera_num=1)   # bus 4 (left)
cfg0 = cam0.create_video_configuration(
    main={"size": (WIDTH, HEIGHT), "format": "YUV420"}, controls=controls)
cfg1 = cam1.create_video_configuration(
    main={"size": (WIDTH, HEIGHT), "format": "YUV420"}, controls=controls)
cam0.configure(cfg0)
cam1.configure(cfg1)

# Buffers filled by callbacks. Each entry: (sensor_timestamp_ns, mono_frame).
# We copy the Y plane out of the buffer immediately so it isn't recycled.
buf0, buf1 = [], []
capturing = False   # gate so callbacks only store during the burst window


def make_cb(buf):
    def cb(request):
        if not capturing:
            return
        md = request.get_metadata()
        t = md.get("SensorTimestamp")
        if t is None:
            return
        arr = request.make_array("main")        # YUV420
        y = arr[:HEIGHT, :WIDTH].copy()          # Y plane = mono
        buf.append((t, y))
    return cb

cam0.post_callback = make_cb(buf0)
cam1.post_callback = make_cb(buf1)

cam0.start(); cam1.start()
time.sleep(0.5)   # let sensors settle

print("=" * 55)
print(f"Session: {SESSION_NAME}")
print(f"Settings: ExposureTime={EXPOSURE}us  Gain={GAIN}")
print(f"Burst: {BURST_SECONDS}s (~{int(BURST_SECONDS*TARGET_FPS)} frames/cam target)")
print("Stereo: cam0 (bus6/right) + cam1 (bus4/left), UNPAIRED logging")
print("=" * 55)

try:
    while True:
        cmd = input("\nEnter to capture a flight ('q' to quit): ").strip().lower()
        if cmd == "q":
            print("Quitting session.")
            break

        for c in range(COUNTDOWN_S, 0, -1):
            print(f"  {c}...")
            time.sleep(1.0)

        # --- burst ---
        buf0.clear(); buf1.clear()
        print("  RECORDING")
        capturing = True
        start_t = time.monotonic()
        while time.monotonic() - start_t < BURST_SECONDS:
            time.sleep(0.005)     # callbacks do the work; just wait out the window
        capturing = False
        time.sleep(0.1)           # let any in-flight callbacks land
        n0, n1 = len(buf0), len(buf1)

        ts0 = [t for (t, _) in buf0]
        ts1 = [t for (t, _) in buf1]
        fps0 = 1000.0 / intra_mean_ms(ts0) if n0 > 1 else 0.0
        fps1 = 1000.0 / intra_mean_ms(ts1) if n1 > 1 else 0.0
        print(f"  cam0: {n0} frames ({fps0:.1f} fps) | cam1: {n1} frames ({fps1:.1f} fps)")

        bad = []
        if abs(1000.0/fps0 - FRAME_PERIOD_MS) > 2 if fps0 else True:
            bad.append("cam0")
        if abs(1000.0/fps1 - FRAME_PERIOD_MS) > 2 if fps1 else True:
            bad.append("cam1")
        if bad:
            print(f"  WARNING: {', '.join(bad)} not at 60 fps - flight may be junk.")
        if abs(n0 - n1) > 2:
            print(f"  NOTE: frame-count mismatch ({n0} vs {n1}) - normal for free-run,"
                  f" pairing handles it downstream.")

        # --- review ---
        list_session(session_dir)
        choice = input("Keep? [y save / n discard / q quit]: ").strip().lower()
        if choice == "q":
            print("Quitting (flight discarded).")
            break
        if choice != "y":
            print("Discarded.")
            continue

        # --- save ---
        num = next_flight_number(session_dir)
        flight_dir = session_dir / f"flight_{num:02d}"
        cam0_dir = flight_dir / "cam0"
        cam1_dir = flight_dir / "cam1"
        cam0_dir.mkdir(parents=True, exist_ok=False)
        cam1_dir.mkdir(parents=True, exist_ok=False)

        print(f"  Writing {n0}+{n1} PNGs to {flight_dir.name} ...")
        for i, (_, f) in enumerate(buf0):
            cv2.imwrite(str(cam0_dir / f"frame_{i:03d}.png"), f)
        for i, (_, f) in enumerate(buf1):
            cv2.imwrite(str(cam1_dir / f"frame_{i:03d}.png"), f)

        # per-flight UNPAIRED timestamp log - the input to downstream pairing + sync correction
        ts_csv = flight_dir / "timestamps.csv"
        with open(ts_csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["cam", "frame_index", "sensor_timestamp_ns"])
            for i, (t, _) in enumerate(buf0):
                w.writerow([0, i, t])
            for i, (t, _) in enumerate(buf1):
                w.writerow([1, i, t])

        saved0 = len(list(cam0_dir.glob("*.png")))
        saved1 = len(list(cam1_dir.glob("*.png")))
        print(f"  Saved {flight_dir.name}: cam0={saved0}, cam1={saved1}, timestamps.csv written.")

finally:
    cam0.stop(); cam1.stop()
    print("\nCameras stopped. Final session contents:")
    list_session(session_dir)
