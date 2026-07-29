# drag_k_discovery_all_flights.py
# Generalized Phase 1: K-discovery across all 163 eligible flights (both
# sessions), building on the flight_01/flight_22 pilot (drag_k_discovery.py)
# now that RANSAC is validated. See
# claude/claude_logs/2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md.
#
# Per flight: build corrected-paired (timestamp + sub-frame corrected)
# detector points (decision #3), run RANSAC per model A/B/C (Model C uses
# the 2-flight pilot's validated pooled K as its reference model for inlier
# identification -- decision #2), then a per-flight free-K refit ONLY if
# enough inliers survive. Final population K = a profiled 1-D search over
# k (NOT a monolithic 163-flight joint nonlinear fit -- see worklog for why
# that would be computationally infeasible and why the profiled search is
# the exact same optimum, not an approximation).
#
# Usage:
#   python src/stereo/drag_k_discovery_all_flights.py

import csv
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.stereo.all_flights_common import (  # noqa: E402
    enumerate_eligible_flights, load_session_calib, g_fixed_for, build_corrected_track,
)
from src.stereo.trajectory_fit import (  # noqa: E402
    fit_constant_accel, fit_drag_given_k, fit_drag_free_k,
    ransac_fit, build_model_fit_predict,
    RANSAC_INLIER_THRESHOLD_MM, RANSAC_MIN_SAMPLES, RANSAC_N_ITERATIONS, RANSAC_SEED,
)

LOG_PATH = REPO_ROOT / "claude" / "claude_logs" / "2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md"
ALL_FLIGHTS_DIR = REPO_ROOT / "data" / "trajectory_fit_comparison" / "all_flights"
PHASE1_DIR = ALL_FLIGHTS_DIR / "phase1"

# 2-flight pilot's validated pooled K -- used as Model C's RANSAC reference
# for inlier identification (decision #2: no per-flight K exists yet at
# that point, so the best available prior is the pilot's own result).
PILOT_K = 6.053818e-05  # 1/mm

MIN_POINTS_FOR_FIT = 8       # below this, skip the flight entirely (too little to fit anything)
MIN_INLIERS_FOR_REFIT = 20   # decision #2: per-flight free-K refit only with >= this many inliers


def log_append(message: str) -> None:
    with open(LOG_PATH, "a") as f:
        f.write(f"- [{datetime.now().strftime('%H:%M:%S')}] {message}\n")


def process_flight_phase1(session: str, flight_id: str) -> dict:
    """Runs (in a worker process for the full batch). Returns a fully
    picklable dict -- no numpy arrays with object dtype, no exceptions
    escaping (all caught and logged into the returned dict instead)."""
    try:
        K0, D0, K1, D1, P0, P1 = load_session_calib(session)
        g_fixed = g_fixed_for(session, flight_id)
        track = build_corrected_track(session, flight_id, K0, D0, K1, D1, P0, P1)
    except Exception as e:
        return dict(session=session, flight=flight_id, status="error",
                    reason=f"exception building track: {e!r}")

    if track is None:
        return dict(session=session, flight=flight_id, status="skipped",
                    reason="no flight dir / missing tuned detections / too few corrected pairs")

    frames, t, xyz, _t_anchor_ns = track
    if len(t) < MIN_POINTS_FOR_FIT:
        return dict(session=session, flight=flight_id, status="skipped",
                    reason=f"only {len(t)} corrected-paired points (< {MIN_POINTS_FOR_FIT})")

    result = dict(session=session, flight=flight_id, status="ok", n_points=len(t),
                  t_span_s=float(t[-1] - t[0]))

    ransac_by_model = {}
    for model in ("A", "B", "C"):
        min_samples = RANSAC_MIN_SAMPLES[model]
        if len(t) < min_samples:
            result[f"rejected_frac_{model}"] = None
            result[f"converge_fail_{model}"] = True
            ransac_by_model[model] = None
            continue
        fit_fn, predict_fn = build_model_fit_predict(model, g_fixed, k_fixed=PILOT_K if model == "C" else None)
        try:
            res = ransac_fit(t, xyz, fit_fn, predict_fn, min_samples, RANSAC_INLIER_THRESHOLD_MM,
                              RANSAC_N_ITERATIONS[model], RANSAC_SEED, frame_numbers=frames)
        except RuntimeError as e:
            result[f"rejected_frac_{model}"] = None
            result[f"converge_fail_{model}"] = True
            result[f"converge_fail_reason_{model}"] = str(e)
            ransac_by_model[model] = None
            continue
        ransac_by_model[model] = res
        result[f"rms_{model}"] = res["residual_rms_mm"]
        result[f"n_inliers_{model}"] = res["n_inliers"]
        result[f"rejected_frac_{model}"] = 1.0 - res["n_inliers"] / len(t)
        result[f"converge_fail_{model}"] = False

    c_res = ransac_by_model.get("C")
    if c_res is None:
        result["insufficient_data"] = True
        result["k_refined"] = None
        result["v0_mag"] = None
        result["inlier_t"] = None
        result["inlier_xyz"] = None
        return result

    accepted = set(c_res["accepted_frames"])
    idx = [i for i, f in enumerate(frames) if f in accepted]
    t_in, xyz_in = t[np.array(idx)], xyz[np.array(idx)]
    result["n_inliers_for_k"] = len(idx)
    result["inlier_t"] = t_in.tolist()
    result["inlier_xyz"] = xyz_in.tolist()

    if len(idx) >= MIN_INLIERS_FOR_REFIT:
        p0_a, v0_a, _ = fit_constant_accel(t_in, xyz_in)
        try:
            p0_r, v0_r, k_r, rms_r = fit_drag_free_k(t_in, xyz_in, g_fixed, p0_a, v0_a, PILOT_K)
            result["k_refined"] = k_r
            result["v0_mag"] = float(np.linalg.norm(v0_r))
            result["rms_refined"] = rms_r
            result["insufficient_data"] = False
        except RuntimeError as e:
            result["k_refined"] = None
            result["v0_mag"] = None
            result["insufficient_data"] = True
            result["refit_fail_reason"] = str(e)
    else:
        result["k_refined"] = None
        result["v0_mag"] = None
        result["insufficient_data"] = True
        result["reason"] = f"only {len(idx)} inliers (< {MIN_INLIERS_FOR_REFIT})"

    return result


def _worker(task):
    session, flight_id = task
    return process_flight_phase1(session, flight_id)


def main():
    log_append("=== drag_k_discovery_all_flights.py: generalized Phase 1 starting ===")

    flights = enumerate_eligible_flights()
    log_append(f"enumerate_eligible_flights(): {len(flights)} flights "
               f"({sum(1 for s,_ in flights if s=='2026_07_21_gym')} in 2026_07_21_gym + "
               f"{sum(1 for s,_ in flights if s=='2026_07_15_gym')} in 2026_07_15_gym)")
    if len(flights) != 163:
        print(f"*** ELIGIBLE COUNT MISMATCH: {len(flights)} != 163 -- STOPPING per error-handling ***")
        log_append(f"*** STOP: eligible flight count {len(flights)} != 163 -- investigate before continuing ***")
        sys.exit(1)
    print(f"{len(flights)} eligible flights confirmed.")

    # ---- timing pilot: ~10 flights, serial, full per-flight cost ----
    pilot_sample = flights[:5] + flights[len(flights) // 2:len(flights) // 2 + 5]
    log_append(f"timing pilot: {len(pilot_sample)} flights -- {pilot_sample}")
    t0 = time.time()
    pilot_results = [process_flight_phase1(s, f) for s, f in pilot_sample]
    pilot_elapsed = time.time() - t0
    per_flight = pilot_elapsed / len(pilot_sample)
    projected_serial = per_flight * len(flights)
    print(f"Timing pilot: {len(pilot_sample)} flights in {pilot_elapsed:.1f}s "
          f"({per_flight:.2f}s/flight) -> projected serial total: {projected_serial:.1f}s "
          f"({projected_serial/60:.1f} min)")
    log_append(f"timing pilot: {pilot_elapsed:.1f}s for {len(pilot_sample)} flights "
               f"({per_flight:.2f}s/flight avg) -> projected serial 163-flight total: "
               f"{projected_serial:.1f}s ({projected_serial/60:.1f} min)")

    use_parallel = projected_serial > 180  # >3 min projected -> parallelize
    if use_parallel:
        log_append(f"projected serial time exceeds 3 min -- using ProcessPoolExecutor "
                   f"(convention matches 10_run_full_dataset.py)")
        print("Parallelizing via ProcessPoolExecutor...")
    else:
        log_append("projected serial time is small -- running serially, no parallelization needed")

    all_results = {}
    # reuse the pilot_sample results already computed (avoid redoing work)
    for r in pilot_results:
        all_results[(r["session"], r["flight"])] = r
    remaining = [t for t in flights if t not in all_results]

    t_batch0 = time.time()
    if use_parallel:
        with ProcessPoolExecutor() as ex:
            futures = {ex.submit(_worker, t): t for t in remaining}
            done = 0
            for fut in as_completed(futures):
                r = fut.result()
                all_results[(r["session"], r["flight"])] = r
                done += 1
                if done % 20 == 0 or done == len(remaining):
                    print(f"  {done}/{len(remaining)} flights processed")
                    log_append(f"progress: {done}/{len(remaining)} remaining flights processed "
                               f"(+{len(pilot_sample)} from timing pilot)")
    else:
        for i, (s, f) in enumerate(remaining, 1):
            all_results[(s, f)] = process_flight_phase1(s, f)
            if i % 20 == 0 or i == len(remaining):
                print(f"  {i}/{len(remaining)} flights processed")
    t_batch_elapsed = time.time() - t_batch0
    print(f"Batch (remaining {len(remaining)} flights) done in {t_batch_elapsed:.1f}s")
    log_append(f"batch complete: {len(remaining)} remaining flights in {t_batch_elapsed:.1f}s "
               f"(parallel={use_parallel}); total flights processed = {len(all_results)}")

    # ---- write per_flight_k.csv ----
    PHASE1_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = PHASE1_DIR / "per_flight_k.csv"
    rows_ok = [r for r in all_results.values() if r["status"] == "ok"]
    n_skipped = sum(1 for r in all_results.values() if r["status"] != "ok")
    n_insufficient = sum(1 for r in rows_ok if r.get("insufficient_data"))
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["session", "flight", "n_points", "n_inliers_C", "k_refined", "v0_mag_mm_s"])
        for r in rows_ok:
            k_val = r.get("k_refined")
            v0_val = r.get("v0_mag")
            w.writerow([r["session"], r["flight"], r["n_points"], r.get("n_inliers_for_k", ""),
                        f"{k_val:.6e}" if k_val is not None else "insufficient_data",
                        f"{v0_val:.2f}" if v0_val is not None else ""])
    print(f"-> {csv_path}")
    log_append(f"wrote {csv_path} ({len(rows_ok)} ok rows, {n_skipped} skipped, "
               f"{n_insufficient} insufficient_data of {len(rows_ok)} ok)")

    # ---- ransac_rejection_summary.csv ----
    csv_path2 = PHASE1_DIR / "ransac_rejection_summary.csv"
    with open(csv_path2, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["session", "flight", "model", "rejected_fraction", "converge_fail"])
        for r in rows_ok:
            for model in ("A", "B", "C"):
                frac = r.get(f"rejected_frac_{model}")
                fail = r.get(f"converge_fail_{model}", False)
                w.writerow([r["session"], r["flight"], model,
                            f"{frac:.4f}" if frac is not None else "", fail])
    print(f"-> {csv_path2}")
    log_append(f"wrote {csv_path2}")

    # ---- models_full_arc_residual_all_flights.csv ----
    csv_path3 = PHASE1_DIR / "models_full_arc_residual_all_flights.csv"
    with open(csv_path3, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["session", "flight", "model", "residual_rms_mm"])
        for r in rows_ok:
            for model in ("A", "B", "C"):
                rms = r.get(f"rms_{model}")
                if rms is not None:
                    w.writerow([r["session"], r["flight"], model, f"{rms:.4f}"])
    print(f"-> {csv_path3}")
    log_append(f"wrote {csv_path3}")

    # ---- models_full_arc_residual_distribution.png (box plot) ----
    fig, ax = plt.subplots(figsize=(8, 6))
    data_by_model = {m: [r[f"rms_{m}"] for r in rows_ok if r.get(f"rms_{m}") is not None] for m in ("A", "B", "C")}
    ax.boxplot([data_by_model[m] for m in ("A", "B", "C")], labels=["A (free gravity)", "B (fixed gravity)", "C (fixed gravity + drag)"])
    ax.set_ylabel("full-arc RANSAC residual RMS (mm)")
    ax.set_yscale("log")
    ax.set_title(f"Model A/B/C full-arc residual distribution across {len(rows_ok)} flights")
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    plot_path = PHASE1_DIR / "models_full_arc_residual_distribution.png"
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)
    print(f"-> {plot_path}")
    log_append(f"wrote {plot_path}")

    # ---- per_flight_k_distribution.png ----
    k_vals = [r["k_refined"] for r in rows_ok if r.get("k_refined") is not None]
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.hist(k_vals, bins=20, color="tab:blue", alpha=0.75)
    ax.axvline(PILOT_K, color="tab:red", linestyle="--", label=f"pilot K={PILOT_K:.3e}")
    ax.set_xlabel("per-flight refined K (1/mm)")
    ax.set_ylabel("count")
    ax.set_title(f"Per-flight K distribution (n={len(k_vals)} flights with sufficient data)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    plot_path2 = PHASE1_DIR / "per_flight_k_distribution.png"
    fig.savefig(plot_path2, dpi=150)
    plt.close(fig)
    print(f"-> {plot_path2}")
    log_append(f"wrote {plot_path2} ({len(k_vals)} flights)")

    # ---- k_vs_velocity.png ----
    v0_vals = [r["v0_mag"] for r in rows_ok if r.get("k_refined") is not None]
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(v0_vals, k_vals, s=25, alpha=0.7)
    if len(k_vals) >= 3:
        corr = float(np.corrcoef(v0_vals, k_vals)[0, 1])
    else:
        corr = float("nan")
    ax.set_xlabel("fitted |v0| (mm/s)")
    ax.set_ylabel("per-flight refined K (1/mm)")
    ax.set_title(f"K vs launch speed (n={len(k_vals)}, Pearson r={corr:.3f})")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    plot_path3 = PHASE1_DIR / "k_vs_velocity.png"
    fig.savefig(plot_path3, dpi=150)
    plt.close(fig)
    print(f"-> {plot_path3}")
    log_append(f"wrote {plot_path3}, Pearson r(|v0|, K) = {corr:.4f}")

    # ---- pooled K via coarse sweep + profiled refinement ----
    inlier_tracks = []
    g_fixed_by_flight = []
    for r in rows_ok:
        if r.get("inlier_t") is not None:
            t_in = np.array(r["inlier_t"])
            xyz_in = np.array(r["inlier_xyz"])
            g = g_fixed_for(r["session"], r["flight"])
            inlier_tracks.append((t_in, xyz_in, g))
    log_append(f"pooled K search: {len(inlier_tracks)} flights contribute RANSAC-inlier points "
               f"(regardless of individual-refit eligibility, per decision #4)")

    def pooled_rms_multi_g(k):
        total_sse, total_n = 0.0, 0
        for t, xyz, g in inlier_tracks:
            p0_a, v0_a, _ = fit_constant_accel(t, xyz)
            try:
                _p0, _v0, rms = fit_drag_given_k(t, xyz, k, g, p0_a, v0_a)
            except RuntimeError:
                continue
            total_sse += len(t) * rms ** 2
            total_n += len(t)
        return float(np.sqrt(total_sse / total_n)) if total_n else None

    K_LO, K_HI = 3e-6, 3e-4
    k_grid = np.geomspace(K_LO, K_HI, 18)
    print(f"\nSweeping pooled K over {len(k_grid)} points [{K_LO:.1e}, {K_HI:.1e}]...")
    log_append(f"pooled K coarse sweep: {len(k_grid)} points, range [{K_LO:.2e},{K_HI:.2e}]")
    sweep_rows = []
    t_sweep0 = time.time()
    for k in k_grid:
        rms = pooled_rms_multi_g(k)
        sweep_rows.append((k, rms))
        print(f"  K={k:.4e}  pooled_rms={rms}")
    print(f"Sweep done in {time.time()-t_sweep0:.1f}s")
    log_append(f"pooled K coarse sweep complete in {time.time()-t_sweep0:.1f}s")

    valid_sweep = [(k, r) for k, r in sweep_rows if r is not None]
    best_k_grid, best_rms_grid = min(valid_sweep, key=lambda x: x[1])
    log_append(f"pooled K sweep best (grid): K={best_k_grid:.6e}, pooled_rms={best_rms_grid:.2f}mm")

    idx_best = k_grid.tolist().index(best_k_grid)
    lo_bound = k_grid[max(0, idx_best - 1)]
    hi_bound = k_grid[min(len(k_grid) - 1, idx_best + 1)]
    opt = minimize_scalar(lambda k: pooled_rms_multi_g(k) or 1e18, bounds=(lo_bound, hi_bound), method="bounded")
    pooled_k_final = float(opt.x)
    pooled_rms_final = float(opt.fun)
    print(f"\nPooled K (profiled joint fit): K={pooled_k_final:.6e}  pooled_rms={pooled_rms_final:.2f}mm")
    log_append(f"pooled K refined (bounded 1-D minimize_scalar around grid best): "
               f"K={pooled_k_final:.6e} 1/mm, pooled_rms={pooled_rms_final:.2f}mm")

    # ---- k_sweep_pooled.csv + residual_vs_K_pooled.png ----
    csv_path4 = PHASE1_DIR / "k_sweep_pooled.csv"
    with open(csv_path4, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["k", "pooled_residual_rms_mm"])
        for k, r in sweep_rows:
            w.writerow([f"{k:.8e}", f"{r:.4f}" if r is not None else ""])
        w.writerow([f"{pooled_k_final:.8e}", f"{pooled_rms_final:.4f}"])  # refined point, appended
    print(f"-> {csv_path4}")
    log_append(f"wrote {csv_path4}")

    fig, ax = plt.subplots(figsize=(9, 6))
    ks = [k for k, r in valid_sweep]
    rs = [r for k, r in valid_sweep]
    ax.plot(ks, rs, marker="o", color="tab:blue", label="coarse sweep (all flights, count-weighted)")
    ax.axvline(pooled_k_final, color="tab:red", linestyle="--", label=f"refined pooled K={pooled_k_final:.3e}")
    ax.axvline(PILOT_K, color="tab:green", linestyle=":", label=f"2-flight pilot K={PILOT_K:.3e}")
    ax.set_xscale("log")
    ax.set_xlabel("K (1/mm)")
    ax.set_ylabel("pooled residual RMS (mm, count-weighted across flights)")
    ax.set_title(f"Population K sweep ({len(inlier_tracks)} flights)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, which="both")
    fig.tight_layout()
    plot_path4 = PHASE1_DIR / "residual_vs_K_pooled.png"
    fig.savefig(plot_path4, dpi=150)
    plt.close(fig)
    print(f"-> {plot_path4}")
    log_append(f"wrote {plot_path4}")

    # ---- Checkpoint 1 conditions (decision #8) ----
    ratio = max(pooled_k_final, PILOT_K) / min(pooled_k_final, PILOT_K)
    frac_insufficient = n_insufficient / len(rows_ok) if rows_ok else 1.0
    # RANSAC health: fraction of (flight,model) with rejected_frac > 0.5 (a coarse
    # "own fitting went badly" signal at this stage; decision #6's proper
    # lead-time-relative flagging is a Phase 2 concept -- this is Phase 1's own
    # coarse version, on full-arc fits, just for the checkpoint gate)
    n_flagged_phase1 = sum(
        1 for r in rows_ok for m in ("A", "B", "C")
        if (r.get(f"rejected_frac_{m}") or 0) > 0.5
    )
    frac_flagged_phase1 = n_flagged_phase1 / (len(rows_ok) * 3) if rows_ok else 1.0

    print(f"\n=== Checkpoint 1 conditions ===")
    print(f"1. Pooled K vs pilot K ratio: {ratio:.2f}x (threshold: <=2x)")
    print(f"2. Fraction insufficient_data: {frac_insufficient:.1%} (threshold: <30%)")
    print(f"3. Fraction (flight,model) with >50% rejection: {frac_flagged_phase1:.1%}")
    log_append(f"Checkpoint 1 conditions: K ratio={ratio:.2f}x (pooled={pooled_k_final:.4e} vs "
               f"pilot={PILOT_K:.4e}), insufficient_data_frac={frac_insufficient:.1%} "
               f"({n_insufficient}/{len(rows_ok)}), phase1_high_rejection_frac={frac_flagged_phase1:.1%} "
               f"({n_flagged_phase1}/{len(rows_ok)*3})")

    conditions_ok = (ratio <= 2.0) and (frac_insufficient < 0.30) and (frac_flagged_phase1 < 0.30)
    if not conditions_ok:
        print("\n*** CHECKPOINT 1 CONDITION FAILED -- STOPPING per decision #8 ***")
        log_append("*** CHECKPOINT 1: one or more conditions failed -- STOPPING, waiting for direction ***")
    else:
        print("\nAll Checkpoint 1 conditions pass -- proceeding straight to Phase 2 (per decision #8).")
        log_append("Checkpoint 1: all conditions PASS -- proceeding straight to Phase 2, no stop.")

    log_append(f"=== drag_k_discovery_all_flights.py: Phase 1 complete. pooled_k={pooled_k_final:.6e}, "
               f"conditions_ok={conditions_ok} ===")

    # persist pooled K for Phase 2 to pick up
    with open(PHASE1_DIR / "pooled_k.txt", "w") as f:
        f.write(f"{pooled_k_final:.8e}\n")

    return conditions_ok, pooled_k_final


if __name__ == "__main__":
    main()
