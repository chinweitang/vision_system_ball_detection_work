#!/usr/bin/env python3
"""exposure_sweep.py  -  RUNS ON THE PI.

Fast exposure/gain sweep for ball detection. For each (exposure, gain) setting it
captures a short burst from BOTH cameras and prints brightness stats immediately,
so you can spot "too dark" / "clipped" on the Pi without pulling anything.

WHY THE PROTOCOL MATTERS:
  Exposure is capped by MOTION BLUR, not chosen for brightness.
  smear_mm = ball_speed_m_s * exposure_s * 1000
  At 10.4 m/s:  2000us -> 21mm,  5000us -> 52mm,  10000us -> 104mm.
  A 210mm ball smeared 100mm has a meaningless centroid.
  => THROW THE BALL AT REALISTIC FLIGHT SPEED during each burst.
     A slow bouncing ball will make every setting look fine and you'll pick wrong.

  Logical order: pick the SHORTEST exposure that still detects, then raise gain to
  compensate for brightness. Do not lengthen exposure to fix darkness.

USAGE:
    python3 exposure_sweep.py            # runs the STAGE_1 coarse sweep below
    # edit SETTINGS for stage 2 refinement once you've seen stage 1

Each setting saves to:  ~/captures/<SESSION>/exp<E>_gain<G>/cam0|cam1/frame_NNN.png
Pull the whole session folder and run your detector over each subfolder.
"""
import time
import statistics
from pathlib import Path
import cv2
import numpy as np
from picamera2 import Picamera2

# ---------------- settings to sweep ----------------
# STAGE 1 (coarse): fix gain, sweep exposure DOWNWARD from the library-locked 5000us.
# Gym is likely brighter -> shorter exposure may work -> less blur -> better centroid.
SETTINGS = [
    (1000, 4.0),
    (1500, 4.0),   # the current locked baseline - the one to beat
    (3000, 4.0),
    (5000, 4.0),
]

# STAGE 2 (refine) - uncomment / edit after seeing stage 1.
# If the short exposures are too dark, hold the exposure and raise gain instead:
# SETTINGS = [
#     (1500, 8.0),
#     (1500, 12.0),
#     (2000, 8.0),
# ]

BURST_SECONDS = 3.0
COUNTDOWN_S   = 3
WIDTH, HEIGHT = 1456, 1088
TARGET_FPS    = 60
BALL_SPEED_MS = 10.4          # fast-end flight speed, for the blur readout
SESSION_NAME  = "2026-07-15_gym_exposure_sweep3"    # <-- EDIT per session
# ---------------------------------------------------

session_dir = Path.home() / "captures" / SESSION_NAME
session_dir.mkdir(parents=True, exist_ok=True)

frame_us = int(1_000_000 / TARGET_FPS)

print("Initialising cameras...")
cam0 = Picamera2(camera_num=0)
cam1 = Picamera2(camera_num=1)
base_controls = {"FrameDurationLimits": (frame_us, frame_us)}
cfg0 = cam0.create_video_configuration(
    main={"size": (WIDTH, HEIGHT), "format": "YUV420"}, controls=base_controls)
cfg1 = cam1.create_video_configuration(
    main={"size": (WIDTH, HEIGHT), "format": "YUV420"}, controls=base_controls)
cam0.configure(cfg0)
cam1.configure(cfg1)

# Buffers filled by callbacks during a burst.
buf0, buf1 = [], []
capturing = False

def make_cb(buf):
    def cb(request):
        if not capturing:
            return
        arr = request.make_array("main")
        buf.append(arr[:HEIGHT, :WIDTH].copy())   # Y plane = mono
    return cb

cam0.post_callback = make_cb(buf0)
cam1.post_callback = make_cb(buf1)

cam0.start(); cam1.start()
time.sleep(0.5)


def brightness_stats(frames):
    """Cheap on-Pi gate: is this setting too dark, or clipping?"""
    if not frames:
        return None
    # sample a few frames rather than all - this only needs to be indicative
    sample = frames[::max(1, len(frames)//10)][:10]
    means, p99s, sats = [], [], []
    for f in sample:
        means.append(float(f.mean()))
        p99s.append(float(np.percentile(f, 99)))
        sats.append(float((f > 250).mean() * 100.0))
    return (statistics.mean(means), statistics.mean(p99s), statistics.mean(sats))


def report(cam_name, frames):
    s = brightness_stats(frames)
    if s is None:
        print(f"  {cam_name}: NO FRAMES")
        return
    mean, p99, sat = s
    flags = []
    if mean < 15:   flags.append("VERY DARK")
    if p99 < 120:   flags.append("no bright pixels - ball may not stand out")
    if sat > 1.0:   flags.append("CLIPPING (>1% saturated)")
    tag = ("  [" + ", ".join(flags) + "]") if flags else "  [looks usable]"
    print(f"  {cam_name}: {len(frames):3d} frames | mean {mean:5.1f} | "
          f"p99 {p99:5.1f} | sat {sat:4.2f}%{tag}")


try:
    for (exposure, gain) in SETTINGS:
        smear = BALL_SPEED_MS * (exposure / 1e6) * 1000.0
        print("\n" + "=" * 58)
        print(f"SETTING: exposure={exposure}us  gain={gain}")
        print(f"  predicted smear at {BALL_SPEED_MS} m/s: {smear:.0f} mm "
              f"({smear/210*100:.0f}% of a 210mm ball)")
        print("=" * 58)

        cam0.set_controls({"ExposureTime": exposure, "AnalogueGain": gain})
        cam1.set_controls({"ExposureTime": exposure, "AnalogueGain": gain})
        time.sleep(0.6)     # let the new exposure settle through the pipeline

        input("Press Enter, then THROW AT FULL FLIGHT SPEED during the burst: ")
        for c in range(COUNTDOWN_S, 0, -1):
            print(f"  {c}...")
            time.sleep(1.0)

        buf0.clear(); buf1.clear()
        print("  RECORDING")
        capturing = True
        t0 = time.monotonic()
        while time.monotonic() - t0 < BURST_SECONDS:
            time.sleep(0.005)
        capturing = False
        time.sleep(0.1)

        frames0 = list(buf0)
        frames1 = list(buf1)
        report("cam0", frames0)
        report("cam1", frames1)

        out = session_dir / f"exp{exposure}_gain{gain}"
        (out / "cam0").mkdir(parents=True, exist_ok=True)
        (out / "cam1").mkdir(parents=True, exist_ok=True)
        print(f"  writing {len(frames0)}+{len(frames1)} PNGs to {out.name} ...")
        for i, f in enumerate(frames0):
            cv2.imwrite(str(out / "cam0" / f"frame_{i:03d}.png"), f)
        for i, f in enumerate(frames1):
            cv2.imwrite(str(out / "cam1" / f"frame_{i:03d}.png"), f)
        print(f"  saved {out.name}")

finally:
    cam0.stop(); cam1.stop()
    print("\nCameras stopped.")
    print(f"\nPull the session:\n  scp -i <key> -r "
          f"chinnywei@192.168.50.1:~/captures/{SESSION_NAME} data/")
    print("Then run your detector over each exp*_gain* subfolder and compare "
          "detection rate + centroid quality.")
