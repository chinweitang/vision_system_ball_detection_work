# ransac_iterations_sweep.py
#
# Characterizes RANSAC's n_iterations vs (compute time, prediction accuracy)
# tradeoff for Model C, to inform what iteration count is actually defensible
# for a real-time deployment -- follow-on from the Pi real-time benchmark
# (claude/decision_log.md #62: RANSAC's 15-iteration production cost was
# ~335-1176ms on the Pi, exceeding the ~480ms actuation budget for longer
# flights) and the theory discussion of ransac_n_iterations()'s success-
# probability formula.
#
# Uses the ELLIPSE (production, validated) detections -- this is a RANSAC
# parameter-tuning question, independent of the rect-kernel investigation
# (decisions 63-65). Fixed 430ms fit window, same held-out-target
# methodology as rect_vs_ellipse_prediction_comparison.py (reused directly,
# not re-derived).
#
# Runs on the LAPTOP, not the Pi -- these are relative-shape/tradeoff
# numbers (time vs n_iterations, error vs n_iterations), not the Pi's
# absolute timing (already measured separately, Pi benchmark Stage 1). The
# per-flight track/target is built ONCE per flight (expensive part), then
# the n_iterations x seed grid only re-runs the RANSAC call itself (cheap
# part) against that same precomputed window -- avoids 22,500x redundant
# triangulation/pairing work.
#
# Does NOT modify detector_core.py or any existing production module.
#
# Usage:
#   python src/stereo/ransac_iterations_sweep.py [--pilot N]

import argparse
import csv
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.stereo.all_flights_common import (  # noqa: E402
    load_session_calib, g_fixed_for, load_final_point_targets, find_flight_dir,
)
from src.stereo.label_vs_detection import triangulate  # noqa: E402
from src.stereo.pixel_velocity_correction import build_corrected_pairs  # noqa: E402
from src.stereo.stereo_flight_sync_table import load_timestamps  # noqa: E402
from src.stereo.trajectory_fit import (  # noqa: E402
    build_model_fit_predict, ransac_fit, RANSAC_INLIER_THRESHOLD_MM, RANSAC_MIN_SAMPLES,
)

LOG_PATH = REPO_ROOT / "claude" / "claude_logs" / "2026-08-03_pi_realtime_benchmark_worklog.md"
OUT_DIR = REPO_ROOT / "results" / "trajectory_fit_comparison" / "ransac_iterations_sweep"
ELLIPSE_DETECTIONS_ROOT = REPO_ROOT / "results" / "detector_tuning" / "detections" / "03_stride1_thresh16_openk3_area30_circ0.3"
POOLED_K_TXT = REPO_ROOT / "results" / "trajectory_fit_comparison" / "all_flights" / "phase1" / "pooled_k.txt"
DURATIONS_CSV = REPO_ROOT / "results" / "trajectory_fit_comparison" / "all_flights" / "duration_distribution" / "flight_durations.csv"

FIT_WINDOW_S = 0.430
DURATION_THRESHOLD_MS = 430.0
N_ITERATIONS_VALUES = [3, 5, 7, 10, 15, 25]
N_SEEDS = 25
MIN_SAMPLES_C = RANSAC_MIN_SAMPLES["C"]


def log_append(message: str) -> None:
    with open(LOG_PATH, "a") as f:
        f.write(f"- [{datetime.now().strftime('%H:%M:%S')}] {message}\n")


def load_pooled_k() -> float:
    with open(POOLED_K_TXT) as f:
        return float(f.read().strip())


def load_durations():
    out = {}
    with open(DURATIONS_CSV, newline="") as f:
        for row in csv.DictReader(f):
            out[(row["session"], row["flight"])] = float(row["total_duration_ms"])
    return out


def build_corrected_track_from_dir(session, flight_id, detections_dir, K0, D0, K1, D1, P0, P1, min_pairs=8):
    """Same as rect_vs_ellipse_prediction_comparison.py's version -- mirrors
    all_flights_common.build_corrected_track, parameterized on detections_dir."""
    flight_dir = find_flight_dir(session, flight_id)
    if flight_dir is None:
        return None
    ts_csv = flight_dir / "timestamps.csv"
    cam0_csv = detections_dir / f"{flight_id}_cam0_detections.csv"
    cam1_csv = detections_dir / f"{flight_id}_cam1_detections.csv"
    if not (cam0_csv.is_file() and cam1_csv.is_file()):
        return None
    pairs = build_corrected_pairs(cam0_csv, cam1_csv, ts_csv)
    if len(pairs) < min_pairs:
        return None
    pairs = sorted(pairs, key=lambda p: (p["t0_ns"] + p["t1_ns"]) / 2.0)
    uv0 = np.array([(p["u0_corr"], p["v0_corr"]) for p in pairs])
    uv1 = np.array([(p["u1_corr"], p["v1_corr"]) for p in pairs])
    xyz = triangulate(uv0, uv1, K0, D0, K1, D1, P0, P1)
    t_avg = np.array([(p["t0_ns"] + p["t1_ns"]) / 2.0 for p in pairs])
    t_sec = (t_avg - t_avg[0]) / 1e9
    frame_labels = [p["cam0_frame"] for p in pairs]
    t_anchor_ns = float(t_avg[0])
    return frame_labels, t_sec, xyz, t_anchor_ns


def target_time_sec(session, flight_id, target_frame0, target_frame1, t_anchor_ns):
    flight_dir = find_flight_dir(session, flight_id)
    if flight_dir is None:
        return None
    ts_csv = flight_dir / "timestamps.csv"
    cam0_entries, cam1_entries = load_timestamps(ts_csv)
    ts0 = dict(cam0_entries)
    ts1 = dict(cam1_entries)
    if target_frame0 not in ts0 or target_frame1 not in ts1:
        return None
    avg_ns = (ts0[target_frame0] + ts1[target_frame1]) / 2.0
    return (avg_ns - t_anchor_ns) / 1e9


def precompute_flight_window(session, flight_id, targets, K0, D0, K1, D1, P0, P1):
    """Everything that's IDENTICAL across all (n_iterations, seed) combos for
    this flight -- built once, not 150x per flight."""
    tgt = targets.get((session, flight_id))
    if tgt is None or "cam0" not in tgt or "cam1" not in tgt:
        return None, "missing final-point label"

    track = build_corrected_track_from_dir(session, flight_id, ELLIPSE_DETECTIONS_ROOT / session,
                                            K0, D0, K1, D1, P0, P1)
    if track is None:
        return None, "no corrected detector track"
    frames, t, xyz, t_anchor_ns = track

    u0, v0, f0 = tgt["cam0"]
    u1, v1, f1 = tgt["cam1"]
    target_xyz = triangulate(np.array([[u0, v0]]), np.array([[u1, v1]]), K0, D0, K1, D1, P0, P1)[0]
    t_target = target_time_sec(session, flight_id, f0, f1, t_anchor_ns)
    if t_target is None:
        return None, "target frame not found in timestamps.csv"

    keep_idx = [i for i, fr in enumerate(frames) if fr != f0]
    if len(keep_idx) < MIN_SAMPLES_C:
        return None, f"only {len(keep_idx)} fit points after excluding target frame (< min_samples={MIN_SAMPLES_C})"
    frames = [frames[i] for i in keep_idx]
    t = t[np.array(keep_idx)]
    xyz = xyz[np.array(keep_idx)]

    if t_target <= t[0]:
        return None, "target time is before the fit track starts"

    N = int(np.searchsorted(t, FIT_WINDOW_S, side="right"))
    if N < MIN_SAMPLES_C:
        return None, f"only {N} points within {FIT_WINDOW_S*1000:.0f}ms window (< min_samples={MIN_SAMPLES_C})"

    t_win = t[:N]
    xyz_win = xyz[:N]
    frame_win = frames[:N]
    lead_time_ms = (t_target - t_win[-1]) * 1000.0
    if lead_time_ms <= 0:
        return None, "window already reached/passed target time"

    g_fixed = g_fixed_for(session, flight_id)
    return dict(t_win=t_win, xyz_win=xyz_win, frame_win=frame_win, target_xyz=target_xyz,
                t_target=t_target, g_fixed=g_fixed, N=N, fit_window_duration_ms=float(t_win[-1] * 1000.0)), None


def process_flight(session, flight_id, pooled_k, targets):
    try:
        K0, D0, K1, D1, P0, P1 = load_session_calib(session)
    except Exception as e:
        return session, flight_id, None, f"calib exception: {e!r}"

    win, reason = precompute_flight_window(session, flight_id, targets, K0, D0, K1, D1, P0, P1)
    if win is None:
        return session, flight_id, None, reason

    fit_fn, predict_fn = build_model_fit_predict("C", win["g_fixed"], k_fixed=pooled_k)

    rows = []
    for n_iter in N_ITERATIONS_VALUES:
        for seed in range(N_SEEDS):
            t0 = time.perf_counter()
            try:
                res = ransac_fit(win["t_win"], win["xyz_win"], fit_fn, predict_fn,
                                  min_samples=MIN_SAMPLES_C, inlier_threshold_mm=RANSAC_INLIER_THRESHOLD_MM,
                                  n_iterations=n_iter, random_seed=seed, frame_numbers=win["frame_win"])
                wall_ms = (time.perf_counter() - t0) * 1000.0
                pred = predict_fn(res["params"], np.array([win["t_target"]]))[0]
                err = float(np.linalg.norm(pred - win["target_xyz"]))
                rows.append(dict(session=session, flight=flight_id, n_iterations=n_iter, seed=seed,
                                  status="ok", wall_ms=wall_ms, error_mm=err,
                                  n_inliers=res["n_inliers"], n_fit_points=win["N"],
                                  rejected_frac=len(res["rejected_frames"]) / win["N"],
                                  fit_window_duration_ms=win["fit_window_duration_ms"]))
            except RuntimeError as e:
                wall_ms = (time.perf_counter() - t0) * 1000.0
                rows.append(dict(session=session, flight=flight_id, n_iterations=n_iter, seed=seed,
                                  status="fit_failed", wall_ms=wall_ms, error_mm="", n_inliers="",
                                  n_fit_points=win["N"], rejected_frac="",
                                  fit_window_duration_ms=win["fit_window_duration_ms"]))
    return session, flight_id, rows, None


def _worker(task):
    session, flight_id, pooled_k, targets = task
    return process_flight(session, flight_id, pooled_k, targets)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", type=int, default=0, help="if >0, only run this many flights (timing pilot, no full output)")
    args = ap.parse_args()

    log_append("=== ransac_iterations_sweep.py starting ===")
    pooled_k = load_pooled_k()
    durations = load_durations()
    targets = load_final_point_targets()

    eligible = sorted([k for k, d in durations.items() if d >= DURATION_THRESHOLD_MS])
    excluded = sorted([k for k, d in durations.items() if d < DURATION_THRESHOLD_MS])
    print(f"{len(durations)} flights in flight_durations.csv; "
          f"{len(eligible)} eligible (duration >= {DURATION_THRESHOLD_MS:.0f}ms), "
          f"{len(excluded)} excluded (< {DURATION_THRESHOLD_MS:.0f}ms)")
    log_append(f"{len(eligible)} eligible flights (duration>={DURATION_THRESHOLD_MS:.0f}ms), "
               f"{len(excluded)} excluded: {excluded}")

    if args.pilot:
        eligible = eligible[:args.pilot]
        print(f"PILOT MODE: only running {len(eligible)} flights")

    n_expected_rows_per_flight = len(N_ITERATIONS_VALUES) * N_SEEDS
    print(f"Grid: {len(eligible)} flights x {len(N_ITERATIONS_VALUES)} n_iterations x {N_SEEDS} seeds "
          f"= up to {len(eligible)*n_expected_rows_per_flight} rows")

    t0 = time.time()
    pilot_n = min(5, len(eligible))
    pilot_results = [process_flight(s, f, pooled_k, targets) for s, f in eligible[:pilot_n]]
    pilot_elapsed = time.time() - t0
    per_flight = pilot_elapsed / pilot_n if pilot_n else 0
    projected_serial = per_flight * len(eligible)
    print(f"Timing pilot: {pilot_n} flights in {pilot_elapsed:.1f}s ({per_flight:.2f}s/flight, "
          f"{n_expected_rows_per_flight} RANSAC calls/flight) -> projected serial total: "
          f"{projected_serial:.1f}s ({projected_serial/60:.1f} min)")
    log_append(f"Timing pilot: {per_flight:.2f}s/flight -> projected serial {projected_serial:.1f}s "
               f"({projected_serial/60:.1f} min)")

    if args.pilot:
        print("Pilot mode -- stopping here, no full run.")
        return

    all_rows = []
    skipped = []
    for s, f, rows, reason in pilot_results:
        if rows is None:
            skipped.append((s, f, reason))
        else:
            all_rows.extend(rows)
    remaining = [(s, f) for s, f in eligible[pilot_n:]]

    t_batch0 = time.time()
    tasks = [(s, f, pooled_k, targets) for s, f in remaining]
    with ProcessPoolExecutor() as ex:
        futures = {ex.submit(_worker, t): t for t in tasks}
        done = 0
        for fut in as_completed(futures):
            s, f, rows, reason = fut.result()
            if rows is None:
                skipped.append((s, f, reason))
            else:
                all_rows.extend(rows)
            done += 1
            if done % 20 == 0 or done == len(remaining):
                print(f"  {done}/{len(remaining)} flights processed")
    t_batch_elapsed = time.time() - t_batch0
    print(f"Batch done in {t_batch_elapsed:.1f}s. {len(skipped)} flights skipped.")
    log_append(f"Batch complete: {len(remaining)} flights in {t_batch_elapsed:.1f}s, "
               f"{len(skipped)} skipped, {len(all_rows)} total rows")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---- raw per-run CSV ----
    raw_csv = OUT_DIR / "ransac_sweep_raw.csv"
    fieldnames = ["session", "flight", "n_iterations", "seed", "status", "wall_ms", "error_mm",
                  "n_inliers", "n_fit_points", "rejected_frac", "fit_window_duration_ms"]
    with open(raw_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in all_rows:
            row = dict(r)
            for k in ("wall_ms", "error_mm", "rejected_frac", "fit_window_duration_ms"):
                if isinstance(row.get(k), float):
                    row[k] = f"{row[k]:.4f}"
            w.writerow(row)
    print(f"-> {raw_csv} ({len(all_rows)} rows)")
    log_append(f"wrote {raw_csv}: {len(all_rows)} rows")

    excluded_csv = OUT_DIR / "excluded_flights.csv"
    with open(excluded_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["session", "flight", "total_duration_ms", "reason"])
        for s, f_ in excluded:
            w.writerow([s, f_, f"{durations[(s,f_)]:.2f}", f"duration < {DURATION_THRESHOLD_MS:.0f}ms"])
        for s, f_, reason in skipped:
            w.writerow([s, f_, f"{durations.get((s,f_), ''):.2f}" if (s, f_) in durations else "", reason])
    print(f"-> {excluded_csv} ({len(excluded)} duration-excluded + {len(skipped)} skipped-in-pipeline)")

    # ---- Table 1: wall-clock time per n_iterations ----
    ok_rows = [r for r in all_rows if r["status"] == "ok"]
    print(f"\n=== TABLE 1: wall-clock time per n_iterations ({len(ok_rows)} successful runs) ===")
    table1 = []
    for n_iter in N_ITERATIONS_VALUES:
        vals = sorted(r["wall_ms"] for r in ok_rows if r["n_iterations"] == n_iter)
        if not vals:
            continue
        med = statistics.median(vals)
        p95 = vals[min(len(vals) - 1, int(round(0.95 * (len(vals) - 1))))]
        table1.append((n_iter, len(vals), med, p95))
        print(f"  n_iterations={n_iter:3d}  n_runs={len(vals):5d}  median={med:8.2f}ms  p95={p95:8.2f}ms")

    with open(OUT_DIR / "table1_wallclock_by_niterations.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["n_iterations", "n_runs", "median_wall_ms", "p95_wall_ms"])
        for n_iter, n, med, p95 in table1:
            w.writerow([n_iter, n, f"{med:.2f}", f"{p95:.2f}"])
    print(f"-> {OUT_DIR / 'table1_wallclock_by_niterations.csv'}")

    # ---- Table 2: error per n_iterations, + seed-spread outlier flights ----
    print(f"\n=== TABLE 2: prediction error per n_iterations ===")
    table2 = []
    for n_iter in N_ITERATIONS_VALUES:
        vals = np.array([r["error_mm"] for r in ok_rows if r["n_iterations"] == n_iter])
        if len(vals) == 0:
            continue
        med = float(np.median(vals))
        iqr = float(np.percentile(vals, 75) - np.percentile(vals, 25))
        table2.append((n_iter, len(vals), med, iqr))
        print(f"  n_iterations={n_iter:3d}  n_runs={len(vals):5d}  median_error={med:8.2f}mm  IQR={iqr:8.2f}mm")

    with open(OUT_DIR / "table2_error_by_niterations.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["n_iterations", "n_runs", "median_error_mm", "iqr_error_mm"])
        for n_iter, n, med, iqr in table2:
            w.writerow([n_iter, n, f"{med:.2f}", f"{iqr:.2f}"])
    print(f"-> {OUT_DIR / 'table2_error_by_niterations.csv'}")

    # ---- seed-to-seed spread outlier flights (per n_iterations, boxplot rule) ----
    print(f"\n=== Seed-to-seed spread outlier flights (boxplot rule: > median+1.5*IQR of per-flight std) ===")
    flagged_spread = []
    for n_iter in N_ITERATIONS_VALUES:
        by_flight = {}
        for r in ok_rows:
            if r["n_iterations"] != n_iter:
                continue
            by_flight.setdefault((r["session"], r["flight"]), []).append(r["error_mm"])
        stds = {k: float(np.std(v)) for k, v in by_flight.items() if len(v) >= 2}
        if not stds:
            continue
        std_vals = np.array(list(stds.values()))
        med_std = float(np.median(std_vals))
        iqr_std = float(np.percentile(std_vals, 75) - np.percentile(std_vals, 25))
        threshold = med_std + 1.5 * iqr_std
        for (s, fl), std in stds.items():
            if iqr_std > 0 and std > threshold:
                flagged_spread.append(dict(n_iterations=n_iter, session=s, flight=fl, seed_std_mm=std,
                                            population_median_std_mm=med_std, threshold_mm=threshold))
                print(f"  n_iterations={n_iter}: {s}/{fl} seed_std={std:.1f}mm "
                      f"(population median={med_std:.1f}mm, threshold={threshold:.1f}mm)")

    with open(OUT_DIR / "seed_spread_outlier_flights.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["n_iterations", "session", "flight", "seed_std_mm", "population_median_std_mm", "threshold_mm"])
        for r in flagged_spread:
            w.writerow([r["n_iterations"], r["session"], r["flight"], f"{r['seed_std_mm']:.2f}",
                        f"{r['population_median_std_mm']:.2f}", f"{r['threshold_mm']:.2f}"])
    print(f"-> {OUT_DIR / 'seed_spread_outlier_flights.csv'} ({len(flagged_spread)} flagged (n_iterations,flight) rows)")

    log_append(f"TABLE1/TABLE2 written; {len(flagged_spread)} seed-spread-outlier (n_iterations,flight) rows flagged")
    log_append("=== ransac_iterations_sweep.py complete ===")
    print(f"\nDone. Output dir: {OUT_DIR}")


if __name__ == "__main__":
    main()
