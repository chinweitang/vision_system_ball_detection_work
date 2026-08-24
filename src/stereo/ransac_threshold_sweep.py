# ransac_threshold_sweep.py
#
# Sweeps RANSAC's inlier distance threshold (RANSAC_INLIER_THRESHOLD_MM,
# production value 75.0mm, single source of truth in trajectory_fit.py:241 --
# verified, not duplicated anywhere else) across [50,75,100,125,150]mm, with
# n_iterations FIXED at 3 (the value the n_iterations sweep, decision 68,
# found gives near-zero accuracy cost vs the production 15) and
# fit_window_duration_ms FIXED at 430ms (same as every other sweep this
# session). Tests whether the 7-flight structurally-unstable subset
# (decision 66/69) is threshold-limited (loosening the threshold grows the
# inlier pool and stabilizes which points get selected) or whether its
# instability is independent of threshold too, same candidate-pool mechanism
# regardless of how loose/tight the cutoff is.
#
# Same per-flight precompute-once pattern as ransac_iterations_sweep.py --
# the expensive part (triangulation, pairing, target lookup) doesn't depend
# on threshold or seed, only the RANSAC call itself does.
#
# Stores accepted_frames (not just n_inliers) per run, needed downstream to
# compute pairwise Jaccard overlap across the 25 seeds per (flight,threshold)
# -- the decisive diagnostic for whether threshold is the bottleneck.
#
# Does NOT modify detector_core.py, trajectory_fit.py, or the production
# RANSAC config (RANSAC_INLIER_THRESHOLD_MM itself is untouched -- this
# script passes different threshold VALUES into ransac_fit's own
# inlier_threshold_mm parameter, already designed to be swept per-call).
#
# Usage:
#   python src/stereo/ransac_threshold_sweep.py [--pilot N]

import argparse
import csv
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

from src.stereo.all_flights_common import load_session_calib, g_fixed_for, load_final_point_targets  # noqa: E402
from src.stereo.label_vs_detection import triangulate  # noqa: E402
from src.stereo.pixel_velocity_correction import build_corrected_pairs  # noqa: E402
from src.stereo.stereo_flight_sync_table import load_timestamps  # noqa: E402
from src.stereo.trajectory_fit import build_model_fit_predict, ransac_fit, RANSAC_MIN_SAMPLES  # noqa: E402
from src.stereo.trajectory_fit import RANSAC_INLIER_THRESHOLD_MM as PRODUCTION_INLIER_THRESHOLD_MM  # noqa: E402

LOG_PATH = REPO_ROOT / "claude" / "claude_logs" / "2026-08-03_pi_realtime_benchmark_worklog.md"
OUT_DIR = REPO_ROOT / "results" / "trajectory_fit_comparison" / "ransac_distance_threshold_sweep"
ELLIPSE_DETECTIONS_ROOT = REPO_ROOT / "results" / "detector_tuning" / "detections" / "03_stride1_thresh16_openk3_area30_circ0.3"
POOLED_K_TXT = REPO_ROOT / "results" / "trajectory_fit_comparison" / "all_flights" / "phase1" / "pooled_k.txt"
DURATIONS_CSV = REPO_ROOT / "results" / "trajectory_fit_comparison" / "all_flights" / "duration_distribution" / "flight_durations.csv"

FIT_WINDOW_S = 0.430
DURATION_THRESHOLD_MS = 430.0
N_ITERATIONS_FIXED = 3   # per decision 68 (n_iterations sweep: near-zero accuracy cost vs production 15)
THRESHOLD_VALUES_MM = [50.0, 75.0, 100.0, 125.0, 150.0]
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
    """Same as rect_vs_ellipse_prediction_comparison.py / ransac_iterations_sweep.py."""
    from src.stereo.all_flights_common import find_flight_dir
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
    from src.stereo.all_flights_common import find_flight_dir
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
        return None, f"only {len(keep_idx)} fit points after excluding target frame"
    frames = [frames[i] for i in keep_idx]
    t = t[np.array(keep_idx)]
    xyz = xyz[np.array(keep_idx)]

    if t_target <= t[0]:
        return None, "target time is before the fit track starts"

    N = int(np.searchsorted(t, FIT_WINDOW_S, side="right"))
    if N < MIN_SAMPLES_C:
        return None, f"only {N} points within {FIT_WINDOW_S*1000:.0f}ms window"

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
    for thresh in THRESHOLD_VALUES_MM:
        for seed in range(N_SEEDS):
            t0 = time.perf_counter()
            try:
                res = ransac_fit(win["t_win"], win["xyz_win"], fit_fn, predict_fn,
                                  min_samples=MIN_SAMPLES_C, inlier_threshold_mm=thresh,
                                  n_iterations=N_ITERATIONS_FIXED, random_seed=seed, frame_numbers=win["frame_win"])
                wall_ms = (time.perf_counter() - t0) * 1000.0
                pred = predict_fn(res["params"], np.array([win["t_target"]]))[0]
                err = float(np.linalg.norm(pred - win["target_xyz"]))
                accepted_str = ";".join(str(int(x)) for x in sorted(res["accepted_frames"]))
                rows.append(dict(session=session, flight=flight_id, threshold_mm=thresh, seed=seed,
                                  status="ok", wall_ms=wall_ms, error_mm=err,
                                  n_inliers=res["n_inliers"], n_fit_points=win["N"],
                                  accepted_frames=accepted_str,
                                  fit_window_duration_ms=win["fit_window_duration_ms"]))
            except RuntimeError as e:
                wall_ms = (time.perf_counter() - t0) * 1000.0
                rows.append(dict(session=session, flight=flight_id, threshold_mm=thresh, seed=seed,
                                  status="fit_failed", wall_ms=wall_ms, error_mm="", n_inliers="",
                                  n_fit_points=win["N"], accepted_frames="",
                                  fit_window_duration_ms=win["fit_window_duration_ms"]))
    return session, flight_id, rows, None


def _worker(task):
    session, flight_id, pooled_k, targets = task
    return process_flight(session, flight_id, pooled_k, targets)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", type=int, default=0)
    args = ap.parse_args()

    log_append("=== ransac_threshold_sweep.py starting ===")
    print(f"Production RANSAC_INLIER_THRESHOLD_MM (verified single source of truth, "
          f"trajectory_fit.py:241): {PRODUCTION_INLIER_THRESHOLD_MM}")
    log_append(f"Confirmed production RANSAC_INLIER_THRESHOLD_MM={PRODUCTION_INLIER_THRESHOLD_MM} "
               f"(single definition site, trajectory_fit.py -- no duplicate hardcode found elsewhere)")

    pooled_k = load_pooled_k()
    durations = load_durations()
    targets = load_final_point_targets()

    eligible = sorted([k for k, d in durations.items() if d >= DURATION_THRESHOLD_MS])
    excluded = sorted([k for k, d in durations.items() if d < DURATION_THRESHOLD_MS])
    print(f"{len(eligible)} eligible flights (duration>={DURATION_THRESHOLD_MS:.0f}ms), "
          f"{len(excluded)} excluded -- same sample as the n_iterations sweep")
    log_append(f"{len(eligible)} eligible flights (same set as ransac_iterations_sweep.py), "
               f"n_iterations FIXED={N_ITERATIONS_FIXED}, thresholds={THRESHOLD_VALUES_MM}")

    if args.pilot:
        eligible = eligible[:args.pilot]
        print(f"PILOT MODE: {len(eligible)} flights")

    n_expected_rows_per_flight = len(THRESHOLD_VALUES_MM) * N_SEEDS
    print(f"Grid: {len(eligible)} flights x {len(THRESHOLD_VALUES_MM)} thresholds x {N_SEEDS} seeds "
          f"= up to {len(eligible)*n_expected_rows_per_flight} rows")

    t0 = time.time()
    pilot_n = min(5, len(eligible))
    pilot_results = [process_flight(s, f, pooled_k, targets) for s, f in eligible[:pilot_n]]
    pilot_elapsed = time.time() - t0
    per_flight = pilot_elapsed / pilot_n if pilot_n else 0
    projected_serial = per_flight * len(eligible)
    print(f"Timing pilot: {pilot_n} flights in {pilot_elapsed:.1f}s ({per_flight:.2f}s/flight, "
          f"{n_expected_rows_per_flight} RANSAC calls/flight) -> projected serial: "
          f"{projected_serial:.1f}s ({projected_serial/60:.1f} min)")
    log_append(f"Timing pilot: {per_flight:.2f}s/flight -> projected serial {projected_serial:.1f}s")

    if args.pilot:
        print("Pilot mode -- stopping here.")
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
    raw_csv = OUT_DIR / "ransac_threshold_sweep_raw.csv"
    fieldnames = ["session", "flight", "threshold_mm", "seed", "status", "wall_ms", "error_mm",
                  "n_inliers", "n_fit_points", "accepted_frames", "fit_window_duration_ms"]
    with open(raw_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in all_rows:
            row = dict(r)
            for k in ("wall_ms", "error_mm", "fit_window_duration_ms"):
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
    print(f"-> {excluded_csv}")

    log_append("=== ransac_threshold_sweep.py raw run complete ===")
    print(f"\nDone (raw sweep only -- run ransac_threshold_sweep_aggregate.py next for tables/figures). "
          f"Output dir: {OUT_DIR}")


if __name__ == "__main__":
    main()
