#!/usr/bin/env python3
"""
check_flight_sync.py  -  RUNS ON THE LAPTOP.

Reads one flight's timestamps.csv (written by capture_flights_stereo.py) and
reports everything you need to trust that flight's stereo timing BEFORE you
triangulate it:

  - frame counts per camera (should be within a few frames)
  - per-camera frame spacing / fps (should be ~16.67 ms / 60 fps)
  - raw offset, whole-frame slip, and SUB-FRAME RESIDUAL (the number that
    feeds the centroid sync correction in triangulation)
  - jitter (irreducible floor)
  - position error at your ball speed, corrected vs uncorrected

The RESIDUAL this prints for a given flight is the number to apply as that
flight's sync correction (shift one camera's centroid by residual x pixel_velocity).

Usage:
    python3 check_flight_sync.py path/to/flight_01/timestamps.csv
    python3 check_flight_sync.py path/to/session/   # checks every flight in it
"""
import sys
import csv
import glob
import statistics
from pathlib import Path

TARGET_FPS      = 60
FRAME_PERIOD_MS = 1000.0 / TARGET_FPS
BALL_SPEED_MS   = 10.4          # fast-end toward-leg speed; edit if needed
WIDTH_BUDGET_MM = 100.0

FPS_TOL_MS   = 2.0              # per-camera spacing must be within this of 16.67
COUNT_TOL    = 3               # allowed frame-count mismatch between cameras


def load(ts_csv):
    ts0, ts1 = [], []
    with open(ts_csv) as f:
        for r in csv.DictReader(f):
            (ts0 if r["cam"] == "0" else ts1).append(int(r["sensor_timestamp_ns"]))
    return ts0, ts1


def spacing_ms(ts):
    if len(ts) < 2:
        return 0.0, 0.0, 0.0
    d = [(ts[i+1]-ts[i])/1e6 for i in range(len(ts)-1)]
    return statistics.mean(d), min(d), max(d)


def greedy_deltas(ts0, ts1):
    used, deltas = set(), []
    for t0 in ts0:
        bj, bd = -1, None
        for j, t1 in enumerate(ts1):
            if j in used:
                continue
            d = t0 - t1
            if bd is None or abs(d) < abs(bd):
                bd, bj = d, j
        if bj != -1:
            used.add(bj)
            deltas.append(bd/1e6)
    return deltas


def check(ts_csv):
    name = Path(ts_csv).parent.name
    ts0, ts1 = load(ts_csv)
    n0, n1 = len(ts0), len(ts1)
    ok = True

    print(f"\n=== {name} ===")
    print(f"frames: cam0={n0}  cam1={n1}", end="  ")
    if abs(n0-n1) > COUNT_TOL:
        print(f"[FAIL: mismatch > {COUNT_TOL}]"); ok = False
    else:
        print("[ok]")

    m0 = spacing_ms(ts0); m1 = spacing_ms(ts1)
    for cam, m in (("cam0", m0), ("cam1", m1)):
        fps = 1000.0/m[0] if m[0] else 0.0
        flag = "ok" if abs(m[0]-FRAME_PERIOD_MS) <= FPS_TOL_MS else "FAIL: not 60 fps"
        if "FAIL" in flag: ok = False
        print(f"{cam} spacing {m[0]:.3f} ms (min {m[1]:.3f} max {m[2]:.3f}) -> {fps:.2f} fps [{flag}]")

    deltas = greedy_deltas(ts0, ts1)
    raw   = statistics.mean(deltas)
    jit   = statistics.pstdev(deltas)
    whole = round(raw/FRAME_PERIOD_MS)
    resid = raw - whole*FRAME_PERIOD_MS
    aligned_max = max(abs(d - whole*FRAME_PERIOD_MS) for d in deltas)

    print(f"raw offset {raw:+.3f} ms  ->  whole frames {whole}, "
          f"RESIDUAL {resid:+.3f} ms  <-- apply this as the sync correction")
    print(f"jitter {jit*1000:.1f} us   max|delta| after align {aligned_max:.3f} ms", end="  ")
    if aligned_max < FRAME_PERIOD_MS/2:
        print("[ok]")
    else:
        print("[FAIL: alignment broke]"); ok = False

    unc = abs(resid)/1000.0 * BALL_SPEED_MS * 1000.0
    jfl = jit/1000.0 * BALL_SPEED_MS * 1000.0
    print(f"position error @ {BALL_SPEED_MS} m/s: uncorrected {unc:.0f} mm "
          f"({'OVER' if unc>WIDTH_BUDGET_MM else 'within'} +-{WIDTH_BUDGET_MM:.0f}),"
          f"  after correction ~{jfl:.2f} mm (jitter floor)")

    print(">>> FLIGHT OK" if ok else ">>> FLIGHT HAS ISSUES - inspect before triangulating")
    return ok, resid


def main():
    if len(sys.argv) < 2:
        print("usage: python3 check_flight_sync.py <timestamps.csv | session_dir>")
        sys.exit(1)
    p = Path(sys.argv[1])
    if p.is_dir():
        csvs = sorted(glob.glob(str(p / "**" / "timestamps.csv"), recursive=True))
        if not csvs:
            print(f"no timestamps.csv found under {p}"); sys.exit(1)
        results = [check(c) for c in csvs]
        good = sum(1 for ok, _ in results if ok)
        print(f"\n=== {good}/{len(results)} flights passed ===")
    else:
        check(str(p))


if __name__ == "__main__":
    main()
