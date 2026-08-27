#!/usr/bin/env python3
"""
sync_startup_test.py  -  RUNS ON THE PI.  ONE startup per invocation.

Purpose: characterise the SUB-FRAME SYNC RESIDUAL across independent camera
startups. Each fresh process = one independent startup. Shell-loop this ~20x:

    for i in $(seq 1 20); do python3 sync_startup_test.py $i; done

Captures TIMESTAMPS ONLY (no ball, no image saving). For each run it computes:
  - raw_offset_ms   : mean signed delta after greedy nearest-timestamp pairing
                      (includes whole-frame startup slip; can exceed 16.67 ms)
  - whole_frames    : round(raw_offset / frame_period)  -> the bookkeeping part
  - residual_ms     : raw_offset - whole_frames*frame_period, folded to +-8.3 ms
                      *** THIS is the true sub-frame phase offset. The number
                          that matters. residual x ball_speed = position error. ***
  - jitter_ms       : std-dev of the signed delta (the irreducible floor)
  - drift_ms_total  : slope*N -> total offset change across the capture
                      (expected tiny; sanity check that drift stays negligible)
  - max_paired_ms   : after index-aligning by whole_frames, the worst |delta|.
                      Should be < 8.3 ms if alignment worked.

Appends ONE row to sync_startup_summary.csv. Analyse the 20 rows on the laptop
with sync_startup_analyse.py to see if the residual is STABLE (fixed correction)
or WANDERS (per-session measurement, or build the hardware trigger).
"""
import sys
import csv
import time
import statistics
from pathlib import Path
from picamera2 import Picamera2

# ---- settings ----
FRAMES_TO_CAPTURE = 180          # ~3 s at 60 fps; drift is dead so no need for 5 s
TARGET_FPS        = 60
FRAME_PERIOD_MS   = 1000.0 / TARGET_FPS      # 16.667 ms
OUTPUT_DIR = Path.home() / "captures"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
SUMMARY_CSV = OUTPUT_DIR / "sync_startup_summary.csv"

run_id = sys.argv[1] if len(sys.argv) > 1 else "NA"


def greedy_pair_deltas(t0_list, t1_list):
    """Nearest-timestamp greedy pairing. Returns signed deltas (ms), cam0 - cam1."""
    deltas = []
    used = set()
    for t0 in t0_list:
        best_j, best = -1, None
        for j in range(len(t1_list)):
            if j in used:
                continue
            d = t0 - t1_list[j]
            if best is None or abs(d) < abs(best):
                best, best_j = d, j
        if best_j != -1:
            used.add(best_j)
            deltas.append(best / 1e6)   # ns -> ms, SIGN KEPT
    return deltas


def fold_to_subframe(offset_ms, period_ms):
    """Strip whole frames; return (whole_frames, residual_ms in +-period/2)."""
    whole = round(offset_ms / period_ms)
    residual = offset_ms - whole * period_ms
    return whole, residual


# ---- capture timestamps from both cameras ----
print(f"[run {run_id}] initialising cameras...")
cam0 = Picamera2(camera_num=0)
cam1 = Picamera2(camera_num=1)
frame_us = int(1_000_000 / TARGET_FPS)
controls = {"FrameDurationLimits": (frame_us, frame_us)}
cfg0 = cam0.create_preview_configuration(main={"size": (1456, 1088)}, controls=controls)
cfg1 = cam1.create_preview_configuration(main={"size": (1456, 1088)}, controls=controls)
cam0.configure(cfg0)
cam1.configure(cfg1)

ts0, ts1 = [], []
def grab0(req):
    t = req.get_metadata().get("SensorTimestamp")
    if t is not None: ts0.append(t)
def grab1(req):
    t = req.get_metadata().get("SensorTimestamp")
    if t is not None: ts1.append(t)
cam0.post_callback = grab0
cam1.post_callback = grab1

# The gap between these two start() calls IS the startup offset we're characterising.
cam0.start(); cam1.start()
while len(ts0) < FRAMES_TO_CAPTURE or len(ts1) < FRAMES_TO_CAPTURE:
    time.sleep(0.05)
cam0.stop(); cam1.stop()

ts0 = ts0[:FRAMES_TO_CAPTURE]
ts1 = ts1[:FRAMES_TO_CAPTURE]
print(f"[run {run_id}] captured cam0={len(ts0)} cam1={len(ts1)}")

# ---- frame-rate sanity (junk run if a camera isn't at 60 fps) ----
def intra_mean(ts):
    d = [(ts[i+1]-ts[i])/1e6 for i in range(len(ts)-1)]
    return statistics.mean(d)
fps_ok = abs(intra_mean(ts0)-FRAME_PERIOD_MS) < 2 and abs(intra_mean(ts1)-FRAME_PERIOD_MS) < 2

# ---- greedy pair, get signed deltas ----
deltas = greedy_pair_deltas(ts0, ts1)
raw_offset = statistics.mean(deltas)
jitter     = statistics.pstdev(deltas)

# drift: slope of delta vs index, reported as total change across the capture
n = len(deltas)
xs = list(range(n))
xbar = statistics.mean(xs); ybar = raw_offset
num = sum((xs[i]-xbar)*(deltas[i]-ybar) for i in range(n))
den = sum((xs[i]-xbar)**2 for i in range(n))
slope = num/den if den else 0.0
drift_total = slope * n

# ---- fold to sub-frame residual (the number that matters) ----
whole_frames, residual = fold_to_subframe(raw_offset, FRAME_PERIOD_MS)

# ---- alignment check: after removing whole_frames, worst |delta| should be < period/2 ----
aligned = [d - whole_frames*FRAME_PERIOD_MS for d in deltas]
max_paired = max(abs(a) for a in aligned)

print(f"[run {run_id}] raw_offset={raw_offset:+.3f} ms | "
      f"whole_frames={whole_frames} | residual={residual:+.3f} ms | "
      f"jitter={jitter:.4f} ms | drift_total={drift_total:+.4f} ms | "
      f"max_paired={max_paired:.3f} ms | fps_ok={fps_ok}")

# ---- append one row to the summary ----
new_file = not SUMMARY_CSV.exists()
with open(SUMMARY_CSV, "a", newline="") as f:
    w = csv.writer(f)
    if new_file:
        w.writerow(["run_id","raw_offset_ms","whole_frames","residual_ms",
                    "jitter_ms","drift_total_ms","max_paired_ms","fps_ok","n_pairs"])
    w.writerow([run_id, f"{raw_offset:.4f}", whole_frames, f"{residual:.4f}",
                f"{jitter:.5f}", f"{drift_total:.4f}", f"{max_paired:.4f}",
                int(fps_ok), n])

print(f"[run {run_id}] appended to {SUMMARY_CSV}")
