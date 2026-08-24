# rect_vs_ellipse_prediction_comparison.py
#
# Does the rect-close-kernel detection-accuracy regression (decision 64:
# avg_combined_rate -2.15pp, labeled_recall -3.75pp, 51% of flights >2pp)
# actually matter for Model C prediction error against the held-out
# final-point targets -- the metric that's actually load-bearing -- or does
# the trajectory-consistency filter + RANSAC absorb it?
#
# Compares Model C (gravity+drag) final-point prediction error between
# ellipse-kernel and rect-kernel mask detections, at a FIXED 430ms fit
# window (not the usual N-sweep), across all 163 flights, twice per flight
# (once per detection source). Reuses the exact same held-out-target
# methodology already validated in trajectory_model_prediction_sweep_all_flights.py
# (target triangulation, frame-exclusion-for-leakage, RANSAC-with-fallback) --
# the only real methodological change is a fixed time window instead of an
# N-sweep, and running against TWO detection sources per flight instead of one.
#
# Does NOT modify detector_core.py or any existing production module.
# build_corrected_track_from_dir() below mirrors all_flights_common.
# build_corrected_track() exactly, parameterized on detections_dir (which
# that function hardcodes to the ellipse baseline) -- needed since this
# script must run against two different detections directories per flight.
#
# Usage:
#   python src/stereo/rect_vs_ellipse_prediction_comparison.py

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

from src.stereo.all_flights_common import (  # noqa: E402
    enumerate_eligible_flights, load_session_calib, g_fixed_for,
    load_final_point_targets, find_flight_dir,
)
from src.stereo.label_vs_detection import triangulate  # noqa: E402
from src.stereo.pixel_velocity_correction import build_corrected_pairs  # noqa: E402
from src.stereo.stereo_flight_sync_table import load_timestamps  # noqa: E402
from src.stereo.trajectory_fit import (  # noqa: E402
    build_model_fit_predict, ransac_fit,
    RANSAC_INLIER_THRESHOLD_MM, RANSAC_MIN_SAMPLES, RANSAC_N_ITERATIONS, RANSAC_SEED,
)

LOG_PATH = REPO_ROOT / "claude" / "claude_logs" / "2026-08-03_pi_realtime_benchmark_worklog.md"
OUT_DIR = REPO_ROOT / "results" / "trajectory_fit_comparison" / "rect_vs_ellipse_kernel"

ELLIPSE_DETECTIONS_ROOT = REPO_ROOT / "results" / "detector_tuning" / "detections" / "03_stride1_thresh16_openk3_area30_circ0.3"
RECT_DETECTIONS_ROOT = REPO_ROOT / "results" / "detector_tuning" / "detections" / "12_rect_close_kernel"
POOLED_K_TXT = REPO_ROOT / "results" / "trajectory_fit_comparison" / "all_flights" / "phase1" / "pooled_k.txt"

FIT_WINDOW_S = 0.430  # fixed 430ms fit window (== the full-population P5 flight
                       # duration found earlier this session -- not a coincidence,
                       # Chin Wei chose it deliberately)

FLAGGED_FLIGHTS_TO_CHECK = [  # worst DETECTION-rate regressions from decision 64,
    ("2026_07_15_gym", "flight_17"),  # session-qualified, for the explicit cross-check
    ("2026_07_15_gym", "flight_22"),
    ("2026_07_21_gym", "flight_50"),
    ("2026_07_21_gym", "flight_63"),
]


def log_append(message: str) -> None:
    with open(LOG_PATH, "a") as f:
        f.write(f"- [{datetime.now().strftime('%H:%M:%S')}] {message}\n")


def load_pooled_k() -> float:
    with open(POOLED_K_TXT) as f:
        return float(f.read().strip())


def build_corrected_track_from_dir(session, flight_id, detections_dir, K0, D0, K1, D1, P0, P1, min_pairs=8):
    """Mirrors all_flights_common.build_corrected_track exactly, except
    detections_dir is an explicit argument instead of pulled from
    SESSIONS[session]['detections_dir'] (hardcoded to the ellipse baseline
    in the original -- this script needs to run against two different
    detections directories per flight, so that hardcoding doesn't fit)."""
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
    """Same as trajectory_model_prediction_sweep_all_flights.py's version."""
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


def fit_and_predict_c(t_win, xyz_win, frame_win, g_fixed, pooled_k, t_target):
    """Model-C-only version of trajectory_model_prediction_sweep_all_flights.py's
    fit_and_predict_ransac -- same RANSAC-with-fallback-to-plain-fit pattern."""
    min_samples = RANSAC_MIN_SAMPLES["C"]
    fit_fn, predict_fn = build_model_fit_predict("C", g_fixed, k_fixed=pooled_k)
    if len(t_win) < min_samples:
        params = fit_fn(t_win, xyz_win)
        return predict_fn(params, np.array([t_target]))[0], None
    res = ransac_fit(t_win, xyz_win, fit_fn, predict_fn,
                      min_samples=min_samples, inlier_threshold_mm=RANSAC_INLIER_THRESHOLD_MM,
                      n_iterations=RANSAC_N_ITERATIONS["C"], random_seed=RANSAC_SEED,
                      frame_numbers=frame_win)
    pred = predict_fn(res["params"], np.array([t_target]))[0]
    return pred, res["rejected_frames"]


def run_variant(session, flight_id, detections_dir, pooled_k, targets, K0, D0, K1, D1, P0, P1, g_fixed):
    tgt = targets.get((session, flight_id))
    if tgt is None or "cam0" not in tgt or "cam1" not in tgt:
        return dict(status="skipped", reason="missing final-point label (one or both cams)")

    track = build_corrected_track_from_dir(session, flight_id, detections_dir, K0, D0, K1, D1, P0, P1)
    if track is None:
        return dict(status="skipped", reason="no corrected detector track")
    frames, t, xyz, t_anchor_ns = track

    u0, v0, f0 = tgt["cam0"]
    u1, v1, f1 = tgt["cam1"]
    target_xyz = triangulate(np.array([[u0, v0]]), np.array([[u1, v1]]), K0, D0, K1, D1, P0, P1)[0]
    t_target = target_time_sec(session, flight_id, f0, f1, t_anchor_ns)
    if t_target is None:
        return dict(status="skipped", reason="target frame not found in timestamps.csv")

    # exclude any fit point coinciding with the target's own frame (leakage guard)
    keep_idx = [i for i, fr in enumerate(frames) if fr != f0]
    if len(keep_idx) < 3:
        return dict(status="skipped", reason=f"only {len(keep_idx)} fit points after excluding target frame")
    frames = [frames[i] for i in keep_idx]
    t = t[np.array(keep_idx)]
    xyz = xyz[np.array(keep_idx)]

    if t_target <= t[0]:
        return dict(status="skipped", reason="target time is before the fit track starts")

    # fixed 430ms window: N = count of points with t <= FIT_WINDOW_S
    N = int(np.searchsorted(t, FIT_WINDOW_S, side="right"))
    if N < 3:
        return dict(status="skipped", reason=f"only {N} points within {FIT_WINDOW_S*1000:.0f}ms window")

    t_win = t[:N]
    xyz_win = xyz[:N]
    frame_win = frames[:N]
    lead_time_ms = (t_target - t_win[-1]) * 1000.0
    if lead_time_ms <= 0:
        return dict(status="skipped", reason="window already reached/passed target time")

    try:
        pred, rejected = fit_and_predict_c(t_win, xyz_win, frame_win, g_fixed, pooled_k, t_target)
    except RuntimeError as e:
        return dict(status="fit_failed", reason=str(e))

    err = float(np.linalg.norm(pred - target_xyz))
    rejected_frac = (len(rejected) / N) if rejected is not None else None
    return dict(status="ok", error_mm=err, rejected_frac=rejected_frac, n_fit_points=N, lead_time_ms=lead_time_ms)


def process_flight(session, flight_id, pooled_k, targets):
    try:
        K0, D0, K1, D1, P0, P1 = load_session_calib(session)
        g_fixed = g_fixed_for(session, flight_id)
    except Exception as e:
        return dict(session=session, flight=flight_id, status="error", reason=f"calib exception: {e!r}")

    ellipse = run_variant(session, flight_id, ELLIPSE_DETECTIONS_ROOT / session, pooled_k, targets,
                           K0, D0, K1, D1, P0, P1, g_fixed)
    rect = run_variant(session, flight_id, RECT_DETECTIONS_ROOT / session, pooled_k, targets,
                        K0, D0, K1, D1, P0, P1, g_fixed)

    return dict(session=session, flight=flight_id, ellipse=ellipse, rect=rect)


def _worker(task):
    session, flight_id, pooled_k, targets = task
    return process_flight(session, flight_id, pooled_k, targets)


def main():
    log_append("=== rect_vs_ellipse_prediction_comparison.py starting ===")
    pooled_k = load_pooled_k()
    print(f"Pooled K: {pooled_k:.6e} 1/mm; fixed fit window: {FIT_WINDOW_S*1000:.0f}ms")
    log_append(f"Pooled K: {pooled_k:.6e} 1/mm; fixed fit window: {FIT_WINDOW_S*1000:.0f}ms")

    targets = load_final_point_targets()
    flights = enumerate_eligible_flights()
    print(f"{len(flights)} eligible flights (ellipse-detections-based enumeration)")
    log_append(f"{len(flights)} eligible flights, {len(targets)} flights with final-point-label entries")

    # timing pilot, same pattern as trajectory_model_prediction_sweep_all_flights.py
    pilot_sample = flights[:5] + flights[len(flights) // 2:len(flights) // 2 + 5]
    t0 = time.time()
    pilot_results = [process_flight(s, f, pooled_k, targets) for s, f in pilot_sample]
    pilot_elapsed = time.time() - t0
    per_flight = pilot_elapsed / len(pilot_sample)
    projected_serial = per_flight * len(flights)
    print(f"Timing pilot: {len(pilot_sample)} flights in {pilot_elapsed:.1f}s "
          f"({per_flight:.2f}s/flight incl. BOTH variants) -> projected serial: {projected_serial:.1f}s")
    log_append(f"Timing pilot: {per_flight:.2f}s/flight -> projected serial {projected_serial:.1f}s")

    use_parallel = projected_serial > 180
    all_results = {(r["session"], r["flight"]): r for r in pilot_results}
    remaining = [t for t in flights if t not in all_results]

    t_batch0 = time.time()
    if use_parallel:
        print("Parallelizing via ProcessPoolExecutor...")
        tasks = [(s, f, pooled_k, targets) for s, f in remaining]
        with ProcessPoolExecutor() as ex:
            futures = {ex.submit(_worker, t): t for t in tasks}
            done = 0
            for fut in as_completed(futures):
                r = fut.result()
                all_results[(r["session"], r["flight"])] = r
                done += 1
                if done % 20 == 0 or done == len(remaining):
                    print(f"  {done}/{len(remaining)} flights processed")
    else:
        for i, (s, f) in enumerate(remaining, 1):
            all_results[(s, f)] = process_flight(s, f, pooled_k, targets)
            if i % 20 == 0 or i == len(remaining):
                print(f"  {i}/{len(remaining)} flights processed")
    t_batch_elapsed = time.time() - t_batch0
    print(f"Batch done in {t_batch_elapsed:.1f}s")
    log_append(f"Batch complete: {len(remaining)} flights in {t_batch_elapsed:.1f}s (parallel={use_parallel})")

    # ---- write per-flight comparison CSV ----
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    both_ok = []
    for (session, flight_id), r in sorted(all_results.items()):
        e, c = r["ellipse"], r["rect"]
        row = dict(session=session, flight=flight_id,
                   ellipse_status=e["status"], rect_status=c["status"],
                   ellipse_error_mm="", rect_error_mm="", delta_mm="",
                   ellipse_rejected_frac="", rect_rejected_frac="",
                   ellipse_n_fit_points=e.get("n_fit_points", ""), rect_n_fit_points=c.get("n_fit_points", ""),
                   ellipse_reason=e.get("reason", ""), rect_reason=c.get("reason", ""))
        if e["status"] == "ok" and c["status"] == "ok":
            delta = c["error_mm"] - e["error_mm"]
            row.update(ellipse_error_mm=f"{e['error_mm']:.2f}", rect_error_mm=f"{c['error_mm']:.2f}",
                       delta_mm=f"{delta:.2f}",
                       ellipse_rejected_frac=f"{e['rejected_frac']:.4f}" if e["rejected_frac"] is not None else "",
                       rect_rejected_frac=f"{c['rejected_frac']:.4f}" if c["rejected_frac"] is not None else "")
            both_ok.append((session, flight_id, e["error_mm"], c["error_mm"], delta,
                            e["rejected_frac"], c["rejected_frac"]))
        rows.append(row)

    csv_path = OUT_DIR / "rect_vs_ellipse_prediction_comparison.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"-> {csv_path}")
    log_append(f"wrote {csv_path}: {len(rows)} flights, {len(both_ok)} with valid comparisons on both variants")

    # ---- pooled stats ----
    ellipse_errs = np.array([x[2] for x in both_ok])
    rect_errs = np.array([x[3] for x in both_ok])
    deltas = np.array([x[4] for x in both_ok])

    def med_iqr(a):
        return float(np.median(a)), float(np.percentile(a, 75) - np.percentile(a, 25))

    e_med, e_iqr = med_iqr(ellipse_errs)
    r_med, r_iqr = med_iqr(rect_errs)
    print(f"\n=== POOLED (n={len(both_ok)} flights with valid comparisons on both variants) ===")
    print(f"ellipse: median={e_med:.1f}mm  IQR={e_iqr:.1f}mm")
    print(f"rect:    median={r_med:.1f}mm  IQR={r_iqr:.1f}mm")
    print(f"delta (rect-ellipse): median={float(np.median(deltas)):.1f}mm  mean={float(np.mean(deltas)):.1f}mm")

    log_append(f"POOLED (n={len(both_ok)}): ellipse median={e_med:.1f}mm IQR={e_iqr:.1f}mm; "
               f"rect median={r_med:.1f}mm IQR={r_iqr:.1f}mm; "
               f"delta median={float(np.median(deltas)):.1f}mm mean={float(np.mean(deltas)):.1f}mm")

    with open(OUT_DIR / "pooled_summary.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["variant", "n", "median_error_mm", "iqr_error_mm"])
        w.writerow(["ellipse", len(both_ok), f"{e_med:.2f}", f"{e_iqr:.2f}"])
        w.writerow(["rect", len(both_ok), f"{r_med:.2f}", f"{r_iqr:.2f}"])
        w.writerow(["delta(rect-ellipse)", len(both_ok), f"{float(np.median(deltas)):.2f}", ""])
    print(f"-> {OUT_DIR / 'pooled_summary.csv'}")

    # ---- explicit check: the 4 worst DETECTION-rate-regression flights ----
    print(f"\n=== FLAGGED-FLIGHT CHECK (worst detection-rate regressions) ===")
    log_append("Flagged-flight check (worst detection-rate regressions from decision 64):")
    for session, flight_id in FLAGGED_FLIGHTS_TO_CHECK:
        match = [x for x in both_ok if x[0] == session and x[1] == flight_id]
        if not match:
            r = all_results.get((session, flight_id))
            reason = "not found"
            if r:
                reason = f"ellipse={r['ellipse']['status']}({r['ellipse'].get('reason','')}) rect={r['rect']['status']}({r['rect'].get('reason','')})"
            print(f"  {session}/{flight_id}: NO VALID COMPARISON ({reason})")
            log_append(f"  {session}/{flight_id}: NO VALID COMPARISON ({reason})")
            continue
        _, _, e_err, r_err, d, e_rej, r_rej = match[0]
        print(f"  {session}/{flight_id}: ellipse_err={e_err:.1f}mm  rect_err={r_err:.1f}mm  "
              f"delta={d:+.1f}mm  ellipse_rejected_frac={e_rej}  rect_rejected_frac={r_rej}")
        log_append(f"  {session}/{flight_id}: ellipse_err={e_err:.1f}mm rect_err={r_err:.1f}mm "
                   f"delta={d:+.1f}mm ellipse_rejected_frac={e_rej} rect_rejected_frac={r_rej}")

    log_append("=== rect_vs_ellipse_prediction_comparison.py complete ===")
    print(f"\nDone. Output dir: {OUT_DIR}")


if __name__ == "__main__":
    main()
