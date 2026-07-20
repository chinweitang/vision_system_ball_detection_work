#!/usr/bin/env python3
"""
stereo_flight_sync_table.py  -  RUNS ON THE LAPTOP.

Audits stereo timing across every flight in a session and emits one summary
CSV plus one plot. See per-flight docstrings below for the algorithm; the
short version:

  - split each flight's timestamps.csv by camera, sort by timestamp
  - per-camera median inter-frame period -> dropped-frame diagnostics
  - nearest-timestamp pairing (bisect) between cam0 and cam1
  - median/MAD orphan rejection on the pairing deltas (real jitter is ~9 us,
    a genuine orphan sits ~1800 sigma out -> 5x MAD is a clean cut)
  - raw offset / whole-frame slip / sub-frame residual from surviving pairs
  - longest contiguous run of surviving pairs, in cam0 time order

Usage:
    python3 stereo_flight_sync_table.py path/to/flight_01            # single flight, prints report only
    python3 stereo_flight_sync_table.py path/to/flight_01/timestamps.csv
    python3 stereo_flight_sync_table.py path/to/session_dir           # full session -> sync_audit.csv + plot
                                                                       # (looks under <session_dir>/ball_flights)
"""
import sys
import csv
import glob
import re
import bisect
import statistics
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BALL_SPEED = 10.4  # m/s, fast-end toward-leg speed; edit if needed

DROP_GAP_FACTOR = 1.5   # consecutive diff > this x median period => dropped frame(s)
ORPHAN_MAD_FACTOR = 5.0  # reject pairs whose delta is more than this x MAD from the median


def natural_flight_key(flight_id):
    m = re.search(r"(\d+)", flight_id)
    return (int(m.group(1)) if m else 0, flight_id)


def load_timestamps(csv_path):
    """Return (cam0, cam1), each a list of (frame_index, sensor_timestamp_ns)
    sorted by timestamp (not by frame_index)."""
    cam0, cam1 = [], []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            entry = (int(row["frame_index"]), int(row["sensor_timestamp_ns"]))
            (cam0 if row["cam"] == "0" else cam1).append(entry)
    cam0.sort(key=lambda e: e[1])
    cam1.sort(key=lambda e: e[1])
    return cam0, cam1


def camera_period_and_drops(entries):
    """Median inter-frame period (ns) and dropped-frame diagnostics for one
    camera's (frame_index, ts_ns) entries, sorted by timestamp."""
    times = [e[1] for e in entries]
    frame_indices = [e[0] for e in entries]
    n = len(times)
    if n < 2:
        return float("nan"), 0, []

    diffs = [times[i + 1] - times[i] for i in range(n - 1)]
    period = statistics.median(diffs)

    drop_count = 0
    drop_frames = []
    for i, d in enumerate(diffs):
        if d > DROP_GAP_FACTOR * period:
            lost = round(d / period) - 1
            if lost > 0:
                drop_count += lost
                drop_frames.append(frame_indices[i])
    return period, drop_count, drop_frames


def nearest_index(times_sorted, t):
    """Index into times_sorted of the value closest to t. Sorted-array bisect
    search, not a nested loop."""
    idx = bisect.bisect_left(times_sorted, t)
    if idx == 0:
        return 0
    if idx == len(times_sorted):
        return len(times_sorted) - 1
    before, after = times_sorted[idx - 1], times_sorted[idx]
    return idx - 1 if (t - before) <= (after - t) else idx


def longest_true_run(valid):
    best = cur = 0
    for v in valid:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best


def analyze_flight(csv_path):
    flight_id = Path(csv_path).parent.name
    cam0, cam1 = load_timestamps(csv_path)
    n0, n1 = len(cam0), len(cam1)

    times0 = [e[1] for e in cam0]
    times1 = [e[1] for e in cam1]

    period0_ns, drops0, drop_frames0 = camera_period_and_drops(cam0)
    period1_ns, drops1, drop_frames1 = camera_period_and_drops(cam1)
    period0_ms = period0_ns / 1e6 if period0_ns == period0_ns else float("nan")
    period1_ms = period1_ns / 1e6 if period1_ns == period1_ns else float("nan")

    # nearest-timestamp pairing: for every cam0 timestamp, closest cam1 timestamp
    deltas_ns = [t0 - times1[nearest_index(times1, t0)] for t0 in times0] if times1 else []

    if deltas_ns:
        median_delta = statistics.median(deltas_ns)
        abs_dev = [abs(d - median_delta) for d in deltas_ns]
        mad = statistics.median(abs_dev)
        threshold = ORPHAN_MAD_FACTOR * mad
        valid = [ad <= threshold for ad in abs_dev]
    else:
        valid = []

    n_valid_pairs = sum(valid)
    run_len = longest_true_run(valid)

    surviving_ns = [d for d, v in zip(deltas_ns, valid) if v]
    if surviving_ns:
        raw_offset_ms = statistics.mean(surviving_ns) / 1e6
        jitter_us = statistics.pstdev(surviving_ns) / 1e3
    else:
        raw_offset_ms = float("nan")
        jitter_us = float("nan")

    if period0_ms == period0_ms and period0_ms > 0 and raw_offset_ms == raw_offset_ms:
        whole_frames = round(raw_offset_ms / period0_ms)
        residual_ms = raw_offset_ms - whole_frames * period0_ms
    else:
        whole_frames = 0
        residual_ms = float("nan")

    pos_err_uncorrected_mm = abs(residual_ms) / 1000.0 * BALL_SPEED * 1000.0
    pos_err_jitter_mm = (jitter_us / 1e6) * BALL_SPEED * 1000.0

    return {
        "flight_id": flight_id,
        "n0": n0,
        "n1": n1,
        "period0_ms": period0_ms,
        "period1_ms": period1_ms,
        "drops0": drops0,
        "drops1": drops1,
        "drop_frames0": drop_frames0,
        "drop_frames1": drop_frames1,
        "n_valid_pairs": n_valid_pairs,
        "longest_run": run_len,
        "raw_offset_ms": raw_offset_ms,
        "whole_frames": whole_frames,
        "residual_ms": residual_ms,
        "jitter_us": jitter_us,
        "pos_err_uncorrected_mm": pos_err_uncorrected_mm,
        "pos_err_jitter_mm": pos_err_jitter_mm,
    }


CSV_FIELDS = [
    "flight_id", "n0", "n1", "period0_ms", "period1_ms", "drops0", "drops1",
    "n_valid_pairs", "longest_run", "raw_offset_ms", "whole_frames",
    "residual_ms", "jitter_us", "pos_err_uncorrected_mm", "pos_err_jitter_mm",
]


def print_single_flight_report(r):
    print(f"\n=== {r['flight_id']} ===")
    print(f"frames: cam0={r['n0']}  cam1={r['n1']}")
    print(f"period: cam0={r['period0_ms']:.4f} ms  cam1={r['period1_ms']:.4f} ms")
    print(f"drops:  cam0={r['drops0']} at frames {r['drop_frames0']}   "
          f"cam1={r['drops1']} at frames {r['drop_frames1']}")
    print(f"pairing: n_valid_pairs={r['n_valid_pairs']}  longest_run={r['longest_run']}")
    print(f"raw_offset={r['raw_offset_ms']:+.4f} ms  whole_frames={r['whole_frames']}  "
          f"residual={r['residual_ms']:+.4f} ms  jitter={r['jitter_us']:.2f} us")
    print(f"position error: uncorrected={r['pos_err_uncorrected_mm']:.2f} mm  "
          f"jitter floor={r['pos_err_jitter_mm']:.3f} mm")


def print_summary_table(rows):
    header = (f"{'flight_id':<14}{'n0':>5}{'n1':>5}{'drops0':>7}{'drops1':>7}"
              f"{'valid':>7}{'run':>6}{'raw_ms':>10}{'whole':>7}{'resid_ms':>10}{'jit_us':>8}")
    print(header)
    print("-" * len(header))
    for r in rows:
        print(f"{r['flight_id']:<14}{r['n0']:>5}{r['n1']:>5}{r['drops0']:>7}{r['drops1']:>7}"
              f"{r['n_valid_pairs']:>7}{r['longest_run']:>6}{r['raw_offset_ms']:>10.3f}"
              f"{r['whole_frames']:>7}{r['residual_ms']:>10.3f}{r['jitter_us']:>8.2f}")

    n = len(rows)
    total_drops = sum(r["drops0"] + r["drops1"] for r in rows)
    runs = [r["longest_run"] for r in rows]
    residuals = [r["residual_ms"] for r in rows]
    print("-" * len(header))
    print(f"total flights={n}  total drops={total_drops}  "
          f"longest_run min/median/max = {min(runs)}/{statistics.median(runs):.0f}/{max(runs)}  "
          f"residual mean={statistics.mean(residuals):+.4f} ms  "
          f"spread(sd)={statistics.pstdev(residuals):.4f} ms")


def write_csv(rows, out_path):
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in CSV_FIELDS})


def write_plot(rows, out_path):
    x = list(range(1, len(rows) + 1))
    y = [r["residual_ms"] for r in rows]

    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    ax.scatter(x, y, s=28, color="#2a78d6", edgecolors="none", zorder=3)

    ax.set_xlabel("flight index")
    ax.set_ylabel("residual (ms)")
    ax.set_title("Stereo sync residual vs. flight")
    ax.axhline(0, color="#c3c2b7", linewidth=1, zorder=1)
    ax.grid(True, color="#e1e0d9", linewidth=0.8, zorder=0)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#c3c2b7")
    ax.tick_params(colors="#52514e")

    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def find_session_flights(session_dir):
    candidates = [session_dir / "ball_flights", session_dir]
    for base in candidates:
        if base.is_dir():
            found = sorted(glob.glob(str(base / "**" / "timestamps.csv"), recursive=True))
            if found:
                return found
    return []


def run_session(session_dir):
    csvs = find_session_flights(session_dir)
    if not csvs:
        print(f"no timestamps.csv found under {session_dir}")
        sys.exit(1)

    rows = [analyze_flight(c) for c in csvs]
    rows.sort(key=lambda r: natural_flight_key(r["flight_id"]))

    print_summary_table(rows)

    out_csv = session_dir / "sync_audit.csv"
    out_png = session_dir / "sync_residual_vs_flight.png"
    write_csv(rows, out_csv)
    write_plot(rows, out_png)
    print(f"\nwrote {out_csv}")
    print(f"wrote {out_png}")


def main():
    if len(sys.argv) < 2:
        print("usage: python3 stereo_flight_sync_table.py <timestamps.csv | flight_dir | session_dir>")
        sys.exit(1)

    p = Path(sys.argv[1])
    if p.is_file():
        print_single_flight_report(analyze_flight(p))
        return

    if not p.is_dir():
        print(f"path not found: {p}")
        sys.exit(1)

    direct_csv = p / "timestamps.csv"
    if direct_csv.is_file():
        print_single_flight_report(analyze_flight(direct_csv))
        return

    run_session(p)


if __name__ == "__main__":
    main()
