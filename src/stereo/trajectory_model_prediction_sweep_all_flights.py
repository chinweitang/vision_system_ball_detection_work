# trajectory_model_prediction_sweep_all_flights.py
# Generalized Phase 2: prediction-window sweep across all 163 eligible
# flights, aggregated by LEAD TIME (not raw N -- different flights have
# different frame densities/lengths, so N isn't comparable across flights).
# See claude/claude_logs/2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md.
#
# Per flight: held-out target = that flight's final-point label (triangulated
# cam0/cam1 pair, already correctly timestamp-paired at labelling time).
# Fit window = corrected-paired DETECTOR points only (only flight_01/22 have
# a manual label track -- that label-vs-detector comparison stays a 2-flight
# thing, already in the pilot's own outputs). Models A/B/C fit via RANSAC
# (K FIXED at Phase 1's Checkpoint-1-approved pooled result).
#
# Usage:
#   python src/stereo/trajectory_model_prediction_sweep_all_flights.py

import csv
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
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

from src.stereo.all_flights_common import (  # noqa: E402
    enumerate_eligible_flights, load_session_calib, g_fixed_for, build_corrected_track,
    load_final_point_targets, SESSIONS,
)
from src.stereo.label_vs_detection import triangulate  # noqa: E402
from src.stereo.stereo_flight_sync_table import load_timestamps  # noqa: E402
from src.stereo.trajectory_fit import (  # noqa: E402
    fit_constant_accel, predict_at, ransac_fit, build_model_fit_predict,
    RANSAC_INLIER_THRESHOLD_MM, RANSAC_MIN_SAMPLES, RANSAC_N_ITERATIONS, RANSAC_SEED,
)
from src.stereo.all_flights_common import find_flight_dir  # noqa: E402

LOG_PATH = REPO_ROOT / "claude" / "claude_logs" / "2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md"
ALL_FLIGHTS_DIR = REPO_ROOT / "data" / "trajectory_fit_comparison" / "all_flights"
PHASE1_DIR = ALL_FLIGHTS_DIR / "phase1"
PHASE2_DIR = ALL_FLIGHTS_DIR / "phase2"

POOLED_K_TXT = PHASE1_DIR / "pooled_k.txt"
REPRESENTATIVE_LEAD_TIMES_MS = [100, 300, 500, 1000]
LEAD_TIME_BIN_WIDTH_MS = 100.0  # for RANSAC health-check bucketing (decision #6)


def log_append(message: str) -> None:
    with open(LOG_PATH, "a") as f:
        f.write(f"- [{datetime.now().strftime('%H:%M:%S')}] {message}\n")


def load_pooled_k() -> float:
    with open(POOLED_K_TXT) as f:
        return float(f.read().strip())


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


def fit_and_predict_ransac(model, t_win, xyz_win, frame_win, g_fixed, k_fixed, t_target):
    """Same convention as the pilot's fit_and_predict_ransac -- falls back
    to the plain fit when the window is smaller than RANSAC's min_samples
    (RANSAC isn't meaningfully applicable to an already-underdetermined
    window; Model A's low-N instability is expected to be untouched)."""
    min_samples = RANSAC_MIN_SAMPLES[model]
    fit_fn, predict_fn = build_model_fit_predict(model, g_fixed, k_fixed=k_fixed if model == "C" else None)
    if len(t_win) < min_samples:
        if model == "A":
            p0, v0, a = fit_constant_accel(t_win, xyz_win)
            return predict_at(p0, v0, a, t_target), None
        params = fit_fn(t_win, xyz_win)
        return predict_fn(params, np.array([t_target]))[0], None
    res = ransac_fit(t_win, xyz_win, fit_fn, predict_fn,
                      min_samples=min_samples, inlier_threshold_mm=RANSAC_INLIER_THRESHOLD_MM,
                      n_iterations=RANSAC_N_ITERATIONS[model], random_seed=RANSAC_SEED,
                      frame_numbers=frame_win)
    pred = predict_fn(res["params"], np.array([t_target]))[0]
    return pred, res["rejected_frames"]


def process_flight_phase2(session: str, flight_id: str, pooled_k: float, targets: dict) -> dict:
    key = (session, flight_id)
    tgt = targets.get(key)
    if tgt is None or "cam0" not in tgt or "cam1" not in tgt:
        return dict(session=session, flight=flight_id, status="skipped",
                    reason="missing final-point label (one or both cams)")

    try:
        K0, D0, K1, D1, P0, P1 = load_session_calib(session)
        g_fixed = g_fixed_for(session, flight_id)
        track = build_corrected_track(session, flight_id, K0, D0, K1, D1, P0, P1)
    except Exception as e:
        return dict(session=session, flight=flight_id, status="error", reason=f"exception: {e!r}")

    if track is None:
        return dict(session=session, flight=flight_id, status="skipped",
                    reason="no corrected detector track")

    frames, t, xyz, t_anchor_ns = track

    u0, v0, f0 = tgt["cam0"]
    u1, v1, f1 = tgt["cam1"]
    target_xyz = triangulate(np.array([[u0, v0]]), np.array([[u1, v1]]), K0, D0, K1, D1, P0, P1)[0]
    t_target = target_time_sec(session, flight_id, f0, f1, t_anchor_ns)
    if t_target is None:
        return dict(session=session, flight=flight_id, status="skipped",
                    reason="target frame not found in timestamps.csv")

    # exclude any fit pair that coincides with the target's own frames (avoid leakage)
    keep_idx = [i for i, fr in enumerate(frames) if fr != f0]
    if len(keep_idx) < 3:
        return dict(session=session, flight=flight_id, status="skipped",
                    reason=f"only {len(keep_idx)} fit points after excluding target frame")
    frames = [frames[i] for i in keep_idx]
    t = t[np.array(keep_idx)]
    xyz = xyz[np.array(keep_idx)]

    if t_target <= t[0]:
        return dict(session=session, flight=flight_id, status="skipped",
                    reason="target time is before the fit track starts -- not a forward prediction")

    N_max = len(frames)
    rows = []
    n_converge_fail = 0
    for N in range(3, N_max + 1):
        t_win = t[:N]
        xyz_win = xyz[:N]
        frame_win = frames[:N]
        lead_time_ms = (t_target - t_win[-1]) * 1000.0
        if lead_time_ms <= 0:
            continue  # window has already reached/passed the target time
        for model in ("A", "B", "C"):
            try:
                pred, rejected = fit_and_predict_ransac(model, t_win, xyz_win, frame_win, g_fixed, pooled_k, t_target)
                err = float(np.linalg.norm(pred - target_xyz))
                rejected_frac = (len(rejected) / N) if rejected is not None else None
            except RuntimeError as e:
                err = np.nan
                rejected_frac = None
                n_converge_fail += 1
            rows.append(dict(session=session, flight=flight_id, N=N, model=model,
                              lead_time_ms=lead_time_ms, error_mm=err, rejected_frac=rejected_frac))

    return dict(session=session, flight=flight_id, status="ok", rows=rows,
                n_converge_fail=n_converge_fail, n_fit_points=N_max)


def _worker(task):
    session, flight_id, pooled_k, targets = task
    return process_flight_phase2(session, flight_id, pooled_k, targets)


def main():
    log_append("=== trajectory_model_prediction_sweep_all_flights.py: generalized Phase 2 starting ===")
    pooled_k = load_pooled_k()
    log_append(f"loaded pooled K from Phase 1: {pooled_k:.6e} 1/mm")
    print(f"Pooled K (fixed, held constant across all windows/flights): {pooled_k:.6e} 1/mm")

    targets = load_final_point_targets()
    flights = enumerate_eligible_flights()
    log_append(f"{len(flights)} eligible flights, {len(targets)} flights with >=1 final-point-label cam entry")

    # ---- timing pilot ----
    pilot_sample = flights[:5] + flights[len(flights) // 2:len(flights) // 2 + 5]
    t0 = time.time()
    pilot_results = [process_flight_phase2(s, f, pooled_k, targets) for s, f in pilot_sample]
    pilot_elapsed = time.time() - t0
    per_flight = pilot_elapsed / len(pilot_sample)
    projected_serial = per_flight * len(flights)
    print(f"Timing pilot: {len(pilot_sample)} flights in {pilot_elapsed:.1f}s "
          f"({per_flight:.2f}s/flight) -> projected serial total: {projected_serial:.1f}s "
          f"({projected_serial/60:.1f} min)")
    log_append(f"Phase 2 timing pilot: {pilot_elapsed:.1f}s for {len(pilot_sample)} flights "
               f"({per_flight:.2f}s/flight) -> projected serial: {projected_serial:.1f}s "
               f"({projected_serial/60:.1f} min)")

    use_parallel = projected_serial > 180
    if use_parallel:
        log_append("Phase 2: projected serial time exceeds 3 min -- using ProcessPoolExecutor")
        print("Parallelizing via ProcessPoolExecutor...")
    else:
        log_append("Phase 2: projected serial time small -- running serially")

    all_results = {}
    for r in pilot_results:
        all_results[(r["session"], r["flight"])] = r
    remaining = [t for t in flights if t not in all_results]

    t_batch0 = time.time()
    if use_parallel:
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
                    log_append(f"Phase 2 progress: {done}/{len(remaining)} remaining flights processed")
    else:
        for i, (s, f) in enumerate(remaining, 1):
            all_results[(s, f)] = process_flight_phase2(s, f, pooled_k, targets)
            if i % 20 == 0 or i == len(remaining):
                print(f"  {i}/{len(remaining)} flights processed")
    t_batch_elapsed = time.time() - t_batch0
    print(f"Batch done in {t_batch_elapsed:.1f}s")
    log_append(f"Phase 2 batch complete: {len(remaining)} flights in {t_batch_elapsed:.1f}s "
               f"(parallel={use_parallel})")

    n_ok = sum(1 for r in all_results.values() if r["status"] == "ok")
    n_skipped = sum(1 for r in all_results.values() if r["status"] != "ok")
    log_append(f"Phase 2: {n_ok} flights ok, {n_skipped} skipped "
               f"({', '.join(sorted(set(r.get('reason','?') for r in all_results.values() if r['status']!='ok')))})")

    all_rows = []
    for r in all_results.values():
        if r["status"] == "ok":
            all_rows.extend(r["rows"])
    log_append(f"Phase 2: {len(all_rows)} total (flight,N,model) rows across {n_ok} flights")

    # ---- write prediction_sweep_all_flights.csv ----
    PHASE2_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = PHASE2_DIR / "prediction_sweep_all_flights.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["session", "flight", "N", "model", "lead_time_ms", "error_mm", "rejected_frac"])
        for r in all_rows:
            w.writerow([r["session"], r["flight"], r["N"], r["model"],
                        f"{r['lead_time_ms']:.2f}",
                        f"{r['error_mm']:.4f}" if not np.isnan(r["error_mm"]) else "",
                        f"{r['rejected_frac']:.4f}" if r["rejected_frac"] is not None else ""])
    print(f"-> {csv_path}")
    log_append(f"wrote {csv_path} ({len(all_rows)} rows)")

    # ---- RANSAC health-check flags (decision #6): outlier relative to
    # OTHER flights in the SAME lead-time bucket, not a fixed ceiling ----
    def bucket_of(lead_ms):
        return int(lead_ms // LEAD_TIME_BIN_WIDTH_MS)

    by_model_bucket = {}
    for r in all_rows:
        if r["rejected_frac"] is None:
            continue
        key = (r["model"], bucket_of(r["lead_time_ms"]))
        by_model_bucket.setdefault(key, []).append(r["rejected_frac"])

    bucket_stats = {}
    for key, vals in by_model_bucket.items():
        arr = np.array(vals)
        med = float(np.median(arr))
        q1, q3 = float(np.percentile(arr, 25)), float(np.percentile(arr, 75))
        iqr = q3 - q1
        bucket_stats[key] = (med, iqr)

    flagged = []
    for r in all_rows:
        if r["rejected_frac"] is None:
            continue
        key = (r["model"], bucket_of(r["lead_time_ms"]))
        med, iqr = bucket_stats[key]
        threshold = med + 1.5 * iqr
        if iqr > 0 and r["rejected_frac"] > threshold:
            flagged.append(dict(session=r["session"], flight=r["flight"], model=r["model"], N=r["N"],
                                 lead_time_ms=r["lead_time_ms"], rejected_frac=r["rejected_frac"],
                                 bucket_median=med, bucket_iqr=iqr, bucket_threshold=threshold))

    csv_path_flags = PHASE2_DIR / "ransac_health_flags.csv"
    with open(csv_path_flags, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["session", "flight", "model", "N", "lead_time_ms", "rejected_frac",
                    "bucket_median", "bucket_iqr", "bucket_threshold"])
        for fl in flagged:
            w.writerow([fl["session"], fl["flight"], fl["model"], fl["N"], f"{fl['lead_time_ms']:.1f}",
                        f"{fl['rejected_frac']:.4f}", f"{fl['bucket_median']:.4f}",
                        f"{fl['bucket_iqr']:.4f}", f"{fl['bucket_threshold']:.4f}"])
    print(f"-> {csv_path_flags} ({len(flagged)} flagged rows)")
    log_append(f"wrote {csv_path_flags}: {len(flagged)} (flight,model,N) rows flagged as "
               f"rejection-fraction outliers relative to their own lead-time-bucket peers "
               f"(median+1.5*IQR rule)")

    convergence_fails = {(r["session"], r["flight"]): r.get("n_converge_fail", 0)
                          for r in all_results.values() if r["status"] == "ok"}
    n_flights_with_fails = sum(1 for v in convergence_fails.values() if v > 0)
    total_fails = sum(convergence_fails.values())
    log_append(f"RANSAC convergence failures: {total_fails} total across {n_flights_with_fails} flights "
               f"(separate QA signal from the rejection-fraction health check)")

    flagged_keys = {(fl["flight"], fl["model"], fl["N"]) for fl in flagged}

    # ---- prediction_error_vs_leadtime.png ----
    fig, ax = plt.subplots(figsize=(11, 7))
    model_colors = {"A": "tab:blue", "B": "tab:orange", "C": "tab:green"}
    for model in ("A", "B", "C"):
        rows_m = [r for r in all_rows if r["model"] == model and not np.isnan(r["error_mm"])]
        xs = np.array([r["lead_time_ms"] for r in rows_m])
        ys = np.array([r["error_mm"] for r in rows_m])
        is_flagged = np.array([(r["flight"], r["model"], r["N"]) in flagged_keys for r in rows_m])

        ax.scatter(xs[~is_flagged], ys[~is_flagged], s=6, alpha=0.15, color=model_colors[model], label=f"{model} (points)")
        if is_flagged.any():
            ax.scatter(xs[is_flagged], ys[is_flagged], s=18, alpha=0.8, color=model_colors[model],
                       marker="x", label=f"{model} (RANSAC-health-flagged)")

        # binned median/IQR trend
        bin_edges = np.arange(0, xs.max() + 100, 100) if len(xs) else np.array([0, 100])
        bin_idx = np.digitize(xs, bin_edges)
        bin_centers, medians, q1s, q3s = [], [], [], []
        for b in range(1, len(bin_edges)):
            sel = ys[bin_idx == b]
            if len(sel) >= 3:
                bin_centers.append((bin_edges[b - 1] + bin_edges[b]) / 2)
                medians.append(np.median(sel))
                q1s.append(np.percentile(sel, 25))
                q3s.append(np.percentile(sel, 75))
        if bin_centers:
            ax.plot(bin_centers, medians, color=model_colors[model], linewidth=2.5, label=f"{model} median trend")
            ax.fill_between(bin_centers, q1s, q3s, color=model_colors[model], alpha=0.15)

    ax.set_yscale("log")
    ax.set_xlabel("lead time (ms)")
    ax.set_ylabel("prediction error at target (mm, log scale)")
    ax.set_title(f"All-flights DETECTOR-track population result (n={n_ok} flights) -- "
                 f"NOT a label-vs-detector comparison (that stays 2-flight, see pilot outputs)")
    handles, labels_ = ax.get_legend_handles_labels()
    seen = set()
    uniq = [(h, l) for h, l in zip(handles, labels_) if not (l in seen or seen.add(l))]
    ax.legend([h for h, l in uniq], [l for h, l in uniq], fontsize=7, loc="upper right")
    ax.grid(alpha=0.3, which="both")
    fig.tight_layout()
    plot_path = PHASE2_DIR / "prediction_error_vs_leadtime.png"
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)
    print(f"-> {plot_path}")
    log_append(f"wrote {plot_path}")

    # ---- prediction_error_summary_table.csv ----
    csv_path_summary = PHASE2_DIR / "prediction_error_summary_table.csv"
    TOL_MS = 50.0
    with open(csv_path_summary, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "lead_time_ms_target", "n_points", "median_error_mm", "p90_error_mm"])
        for model in ("A", "B", "C"):
            rows_m = [r for r in all_rows if r["model"] == model and not np.isnan(r["error_mm"])]
            for lt in REPRESENTATIVE_LEAD_TIMES_MS:
                sel = [r["error_mm"] for r in rows_m if abs(r["lead_time_ms"] - lt) <= TOL_MS]
                if sel:
                    w.writerow([model, lt, len(sel), f"{np.median(sel):.2f}", f"{np.percentile(sel, 90):.2f}"])
                else:
                    w.writerow([model, lt, 0, "", ""])
    print(f"-> {csv_path_summary}")
    log_append(f"wrote {csv_path_summary} (lead times {REPRESENTATIVE_LEAD_TIMES_MS}ms, tolerance +-{TOL_MS}ms)")

    log_append("=== trajectory_model_prediction_sweep_all_flights.py: Phase 2 complete ===")


if __name__ == "__main__":
    main()
