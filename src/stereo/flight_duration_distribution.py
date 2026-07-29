# flight_duration_distribution.py
# Small follow-up to the all-flights gravity-vs-drag generalization: look at
# the real distribution of each flight's total observable duration (first
# usable fit frame -> held-out target), read/derived from the already-
# produced prediction_sweep_all_flights.csv, to inform a future duration-
# strata decision. See
# claude/claude_logs/2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md.
#
# Does NOT rerun the prediction sweep -- only rebuilds each flight's
# corrected-pairing TIME ARRAY (no RANSAC, no model fitting) to derive
# fit_window_duration_ms(N), since that isn't itself a column in the CSV.
#
# Usage:
#   python src/stereo/flight_duration_distribution.py

import csv
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.stereo.all_flights_common import load_session_calib, build_corrected_track  # noqa: E402

LOG_PATH = REPO_ROOT / "claude" / "claude_logs" / "2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md"
PHASE2_CSV = REPO_ROOT / "data" / "trajectory_fit_comparison" / "all_flights" / "phase2" / "prediction_sweep_all_flights.csv"
OUT_DIR = REPO_ROOT / "data" / "trajectory_fit_comparison" / "all_flights" / "duration_distribution"

TOLERANCE_MS = 1.0  # float round-trip through the CSV's 2-decimal lead_time_ms
                     # formatting can introduce up to ~5ms of rounding noise per
                     # value; 1ms is tight relative to durations in the
                     # hundreds-to-thousands of ms, chosen to catch a real bug
                     # (which would show up as a large, systematic drift, not
                     # sub-ms rounding) without false-flagging on formatting noise


def log_append(message: str) -> None:
    with open(LOG_PATH, "a") as f:
        f.write(f"- [{datetime.now().strftime('%H:%M:%S')}] {message}\n")


def main():
    log_append("=== flight_duration_distribution.py starting ===")

    rows_by_flight = defaultdict(list)
    with open(PHASE2_CSV, newline="") as f:
        for row in csv.DictReader(f):
            key = (row["session"], row["flight"])
            rows_by_flight[key].append((int(row["N"]), float(row["lead_time_ms"])))

    print(f"{len(rows_by_flight)} flights present in prediction_sweep_all_flights.csv")
    log_append(f"{len(rows_by_flight)} flights present in prediction_sweep_all_flights.csv "
               f"(each contributes multiple N x model rows)")

    calib_cache = {}
    durations = []
    failed_invariant = []
    n_track_build_failed = 0

    for i, (key, rows) in enumerate(sorted(rows_by_flight.items()), 1):
        session, flight = key
        if session not in calib_cache:
            calib_cache[session] = load_session_calib(session)
        K0, D0, K1, D1, P0, P1 = calib_cache[session]

        track = build_corrected_track(session, flight, K0, D0, K1, D1, P0, P1)
        if track is None:
            n_track_build_failed += 1
            log_append(f"{session}/{flight}: build_corrected_track returned None -- "
                       f"cannot derive fit_window_duration_ms, skipping")
            continue
        frames, t, xyz, _t_anchor_ns = track

        # unique N values actually present for this flight (model doesn't
        # affect fit_window_duration, so dedupe on N)
        n_to_leadtimes = defaultdict(list)
        for N, lead_ms in rows:
            n_to_leadtimes[N].append(lead_ms)

        totals = []
        for N, lead_list in n_to_leadtimes.items():
            if N - 1 >= len(t):
                continue  # shouldn't happen, but guard against stale/mismatched track
            fit_window_duration_ms = t[N - 1] * 1000.0
            for lead_ms in lead_list:
                totals.append(fit_window_duration_ms + lead_ms)

        if not totals:
            n_track_build_failed += 1
            continue

        totals_arr = np.array(totals)
        spread = totals_arr.max() - totals_arr.min()
        if spread > TOLERANCE_MS:
            failed_invariant.append((session, flight, spread, totals_arr.min(), totals_arr.max()))
            log_append(f"{session}/{flight}: INVARIANT FAILED -- total_duration spread="
                       f"{spread:.3f}ms across N (min={totals_arr.min():.2f}, max={totals_arr.max():.2f}) "
                       f"> tolerance {TOLERANCE_MS}ms")
            continue

        durations.append(dict(session=session, flight=flight, total_duration_ms=float(np.mean(totals_arr))))

        if i % 40 == 0 or i == len(rows_by_flight):
            print(f"  {i}/{len(rows_by_flight)} flights checked")

    log_append(f"invariant check complete: {len(durations)} flights passed, "
               f"{len(failed_invariant)} FAILED, {n_track_build_failed} track-build failures")
    print(f"\n{len(durations)} flights passed the invariant check "
          f"({len(failed_invariant)} failed, {n_track_build_failed} track-build failures)")

    if failed_invariant:
        print("\n*** INVARIANT FAILURES ***")
        for session, flight, spread, lo, hi in failed_invariant:
            print(f"  {session}/{flight}: spread={spread:.2f}ms (min={lo:.2f}, max={hi:.2f})")
    else:
        print("Invariant holds for every flight checked (within "
              f"{TOLERANCE_MS}ms tolerance) -- no bug indicated in the CSV's timing columns.")
        log_append(f"Invariant holds for ALL {len(durations)} flights within {TOLERANCE_MS}ms -- "
                   f"no timing-column bug indicated")

    # ---- summary stats ----
    vals = np.array([d["total_duration_ms"] for d in durations])
    print(f"\n=== Summary statistics (n={len(vals)}) ===")
    print(f"min={vals.min():.1f}ms  p25={np.percentile(vals,25):.1f}ms  "
          f"median={np.median(vals):.1f}ms  p75={np.percentile(vals,75):.1f}ms  max={vals.max():.1f}ms")
    iqr = np.percentile(vals, 75) - np.percentile(vals, 25)
    lo_fence = np.percentile(vals, 25) - 1.5 * iqr
    hi_fence = np.percentile(vals, 75) + 1.5 * iqr
    outliers = [d for d in durations if d["total_duration_ms"] < lo_fence or d["total_duration_ms"] > hi_fence]
    print(f"Boxplot-rule outliers (outside [{lo_fence:.1f}, {hi_fence:.1f}]ms): {len(outliers)}")
    for d in sorted(outliers, key=lambda d: d["total_duration_ms"]):
        print(f"  {d['session']}/{d['flight']}: {d['total_duration_ms']:.1f}ms")

    outliers_str = ", ".join(f"{d['flight']}={d['total_duration_ms']:.0f}ms" for d in outliers) if outliers else "none"
    log_append(f"Summary stats (n={len(vals)}): min={vals.min():.1f}ms, p25={np.percentile(vals,25):.1f}ms, "
               f"median={np.median(vals):.1f}ms, p75={np.percentile(vals,75):.1f}ms, max={vals.max():.1f}ms, "
               f"IQR={iqr:.1f}ms, boxplot outliers={len(outliers)} ({outliers_str})")

    # ---- write flight_durations.csv ----
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / "flight_durations.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["session", "flight", "total_duration_ms"])
        for d in sorted(durations, key=lambda d: (d["session"], d["flight"])):
            w.writerow([d["session"], d["flight"], f"{d['total_duration_ms']:.2f}"])
    print(f"-> {csv_path}")
    log_append(f"wrote {csv_path} ({len(durations)} rows)")

    # ---- histogram ----
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.hist(vals, bins=25, color="tab:blue", alpha=0.8, edgecolor="white")
    for q, label in [(np.percentile(vals, 25), "p25"), (np.median(vals), "median"), (np.percentile(vals, 75), "p75")]:
        ax.axvline(q, color="tab:red", linestyle="--", alpha=0.7)
        ax.text(q, ax.get_ylim()[1] * 0.95, label, rotation=90, fontsize=8, color="tab:red", va="top")
    ax.set_xlabel("total observable duration (ms): first usable fit frame -> held-out target")
    ax.set_ylabel("count (flights)")
    ax.set_title(f"Flight duration distribution (n={len(vals)} flights)")
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    plot_path = OUT_DIR / "flight_duration_histogram.png"
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)
    print(f"-> {plot_path}")
    log_append(f"wrote {plot_path}")

    log_append("=== flight_duration_distribution.py complete ===")


if __name__ == "__main__":
    main()
