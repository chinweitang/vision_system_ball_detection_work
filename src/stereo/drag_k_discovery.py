# drag_k_discovery.py
# Phase 1 of the gravity-vs-drag comparison (see
# claude/prompts/2026-07-27_1818_gravity_vs_drag_trajectory_fitting.md and
# claude/claude_logs/2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md).
#
# On flight_01 and flight_22's full, densely-labelled arcs (2026_07_15_gym):
#   Model A (free gravity)          -- reference point only
#   Model B (fixed gravity, linear) -- fit_constant_accel_fixed_g
#   Model C (fixed gravity + drag)  -- sweep K, then refine via nonlinear fit
# Then compare the two flights' independently-fitted K, and (if they agree)
# pool both flights into one joint fit sharing K (but NOT p0/v0 -- see the
# worklog for why a literal single fit_drag_free_k call across both flights'
# concatenated points would be physically meaningless).
#
# Usage:
#   python src/stereo/drag_k_discovery.py

import csv
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.stereo.label_vs_detection import load_calib, triangulate, load_points_csv, FRAME_DT
from src.stereo.trajectory_fit import (
    fit_constant_accel, predict_at,
    fit_constant_accel_fixed_g, predict_at_fixed_g,
    simulate_drag, fit_drag_given_k, fit_drag_free_k,
    load_g_fixed,
    ransac_fit, build_model_fit_predict,
    RANSAC_INLIER_THRESHOLD_MM, RANSAC_MIN_SAMPLES, RANSAC_N_ITERATIONS, RANSAC_SEED,
)

CALIB_DIR = REPO_ROOT / "calibration_outputs"
EXTRINSICS = REPO_ROOT / "calibration_outputs" / "2026_07_15" / "stereo_extrinsic.npz"
G_FIXED_NPZ = (REPO_ROOT / "data" / "2026_07_15_gym" / "flight_binning" /
               "world_frame_validation" / "registration_world_transform.npz")

LOG_PATH = REPO_ROOT / "claude" / "claude_logs" / "2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md"

RESULTS_DIR = REPO_ROOT / "data" / "trajectory_fit_comparison"
PHASE1_DIR = RESULTS_DIR / "phase1"

# K sweep centered on a physically-derived volleyball estimate:
# k ~= 0.5 * rho_air * Cd * A / m, rho_air=1.2, Cd=0.4, A=0.0346 m^2, m=0.27 kg
# -> k ~ 0.0308 (1/m, SI). Units note: simulate_drag's k multiplies |v|*v with
# v in mm/s, so this SI k (1/m = 1/(m/s)^2 * (m/s^2)) must be scaled: a = -k*|v|*v
# with v in m/s gives a in m/s^2; converting v to mm/s (factor 1000) and a to
# mm/s^2 (factor 1000) means k_mm = k_SI / 1000 to keep the same physical drag.
K_SI_ESTIMATE = 0.5 * 1.2 * 0.4 * 0.0346 / 0.27  # ~0.0308 (1/m)
K_MM_ESTIMATE = K_SI_ESTIMATE / 1000.0  # ~3.08e-5 (1/mm), so simulate_drag's k*|v_mm|*v_mm ~ matches k_SI*|v_m|*v_m in mm/s^2

FLIGHTS = ["flight_01", "flight_22"]
FLIGHT_DIRS = {
    "flight_01": REPO_ROOT / "data" / "2026_07_15_gym" / "ball_flights" /
                 "2 ball contacts ground before plane" / "flight_01",
    "flight_22": REPO_ROOT / "data" / "2026_07_15_gym" / "ball_flights" / "flight_22",
}


def log_append(message: str) -> None:
    with open(LOG_PATH, "a") as f:
        f.write(f"- [{datetime.now().strftime('%H:%M:%S')}] {message}\n")


def load_flight_01_labels():
    """flight_01 already has a combined labels_uv.csv (frame_index,cam,u,v)."""
    pts = load_points_csv(FLIGHT_DIRS["flight_01"] / "labels_uv.csv")
    return pts


def load_flight_22_labels():
    """flight_22 only has per-cam label CSVs (frame_number,...,centroid_x,
    centroid_y,...) -- adapt into the same {cam: {frame: (u,v)}} shape as
    load_points_csv, using the centroid columns."""
    d = FLIGHT_DIRS["flight_22"]
    pts = {0: {}, 1: {}}
    for cam, fname in ((0, "flight_22_cam0_labels.csv"), (1, "flight_22_cam1_labels.csv")):
        with open(d / fname, newline="") as f:
            for row in csv.DictReader(f):
                pts[cam][int(row["frame_number"])] = (float(row["centroid_x"]), float(row["centroid_y"]))
    return pts


LOADERS = {"flight_01": load_flight_01_labels, "flight_22": load_flight_22_labels}


def triangulate_full_track(flight_name, K0, D0, K1, D1, P0, P1):
    pts = LOADERS[flight_name]()
    common = sorted(set(pts[0]) & set(pts[1]))
    uv0 = np.array([pts[0][f] for f in common])
    uv1 = np.array([pts[1][f] for f in common])
    xyz = triangulate(uv0, uv1, K0, D0, K1, D1, P0, P1)
    t0_frame = common[0]
    t = np.array([(f - t0_frame) * FRAME_DT for f in common])
    return common, t, xyz


def rms_residual(xyz, pred):
    return float(np.sqrt(np.mean(np.sum((xyz - pred) ** 2, axis=1))))


def discover_k_for_flight(flight_name, t, xyz, g_fixed):
    print(f"\n=== {flight_name}: n={len(t)} points, span={t[-1] - t[0]:.3f} s ===")
    log_append(f"{flight_name}: n={len(t)} labelled points, t span={t[-1]-t[0]:.3f}s -- "
               f"starting Model A/B/C discovery")

    # Model A: free gravity
    p0_a, v0_a, a_a = fit_constant_accel(t, xyz)
    pred_a = np.array([predict_at(p0_a, v0_a, a_a, tt) for tt in t])
    rms_a = rms_residual(xyz, pred_a)
    print(f"Model A (free gravity):  |a|={np.linalg.norm(a_a)/1000:.3f} m/s^2  residual_rms={rms_a:.2f} mm")

    # Model B: fixed gravity, linear
    p0_b, v0_b = fit_constant_accel_fixed_g(t, xyz, g_fixed)
    pred_b = np.array([predict_at_fixed_g(p0_b, v0_b, g_fixed, tt) for tt in t])
    rms_b = rms_residual(xyz, pred_b)
    print(f"Model B (fixed gravity): residual_rms={rms_b:.2f} mm")

    # Model C: sweep K (seeded p0/v0 guess from Model A -- p0/v0 are nuisance
    # params here, not borrowed as gravity per decision #3)
    k_values = np.linspace(K_MM_ESTIMATE * 0.1, K_MM_ESTIMATE * 5.0, 30)
    sweep_results = []
    for k in k_values:
        try:
            p0_c, v0_c, rms_c = fit_drag_given_k(t, xyz, k, g_fixed, p0_a.copy(), v0_a.copy())
            sweep_results.append((k, rms_c, p0_c, v0_c))
        except RuntimeError as e:
            log_append(f"{flight_name}: K={k:.6e} sweep point FAILED to converge -- {e} -- skipping")
            continue
    if not sweep_results:
        log_append(f"{flight_name}: ALL K-sweep points failed -- cannot proceed with Model C")
        return dict(rms_a=rms_a, rms_b=rms_b, k_sweep_best=None, rms_c_sweep=None,
                    k_refined=None, rms_c_refined=None, p0_a=p0_a, v0_a=v0_a,
                    k_values=k_values, sweep_results=[])

    best_k, best_rms, best_p0, best_v0 = min(sweep_results, key=lambda r: r[1])
    at_edge = (best_k <= k_values[1]) or (best_k >= k_values[-2])
    print(f"Model C sweep: best K={best_k:.6e} (1/mm)  residual_rms={best_rms:.2f} mm  "
          f"(sweep range [{k_values[0]:.2e}, {k_values[-1]:.2e}]) {'*** AT EDGE ***' if at_edge else ''}")
    log_append(f"{flight_name}: K-sweep best K={best_k:.6e} 1/mm, residual={best_rms:.2f}mm "
               f"(range [{k_values[0]:.2e},{k_values[-1]:.2e}]){'  AT EDGE -- widen sweep' if at_edge else ''}")
    if at_edge:
        print("  WARNING: best K at sweep edge -- widening would be advisable (see log).")

    # Refine via free-K nonlinear fit, seeded from the sweep's best point
    try:
        p0_r, v0_r, k_r, rms_r = fit_drag_free_k(t, xyz, g_fixed, best_p0, best_v0, best_k)
        print(f"Model C refined: K={k_r:.6e} (1/mm)  residual_rms={rms_r:.2f} mm")
        log_append(f"{flight_name}: Model C refined (free-K nonlinear fit) K={k_r:.6e} 1/mm, "
                   f"residual={rms_r:.2f}mm")
    except RuntimeError as e:
        log_append(f"{flight_name}: Model C free-K refinement FAILED -- {e}")
        k_r, rms_r = best_k, best_rms

    return dict(rms_a=rms_a, rms_b=rms_b, k_sweep_best=best_k, rms_c_sweep=best_rms,
                k_refined=k_r, rms_c_refined=rms_r, p0_a=p0_a, v0_a=v0_a,
                k_values=k_values, sweep_results=sweep_results)


def ransac_discover_for_flight(flight_name, common, t, xyz, g_fixed, k_reference, k_values):
    """Runs ransac_fit once per model (A/B/C) on the flight's FULL labelled
    track, logs accepted/rejected frames, then reuses Model C's RANSAC
    inlier set to recompute the K-sweep (plain fit_drag_given_k, NOT full
    RANSAC at every grid point -- decision #2) restricted to those inliers."""
    print(f"\n--- {flight_name}: RANSAC pass (labelled track, n={len(t)}) ---")
    log_append(f"{flight_name}: RANSAC starting -- inlier_threshold={RANSAC_INLIER_THRESHOLD_MM}mm, "
               f"seed={RANSAC_SEED}, min_samples={RANSAC_MIN_SAMPLES}, "
               f"n_iterations={RANSAC_N_ITERATIONS}")

    ransac_results = {}
    for model in ("A", "B", "C"):
        fit_fn, predict_fn = build_model_fit_predict(model, g_fixed, k_fixed=k_reference if model == "C" else None)
        try:
            res = ransac_fit(t, xyz, fit_fn, predict_fn,
                              min_samples=RANSAC_MIN_SAMPLES[model],
                              inlier_threshold_mm=RANSAC_INLIER_THRESHOLD_MM,
                              n_iterations=RANSAC_N_ITERATIONS[model],
                              random_seed=RANSAC_SEED, frame_numbers=common)
        except RuntimeError as e:
            log_append(f"{flight_name} model {model}: RANSAC FAILED -- {e}")
            ransac_results[model] = None
            continue
        ransac_results[model] = res
        print(f"Model {model} RANSAC: n_inliers={res['n_inliers']}/{len(t)}  "
              f"residual_rms={res['residual_rms_mm']:.2f}mm  rejected={res['rejected_frames']}")
        log_append(f"{flight_name} model {model}: RANSAC n_inliers={res['n_inliers']}/{len(t)}, "
                   f"residual_rms={res['residual_rms_mm']:.2f}mm, "
                   f"rejected_frames={res['rejected_frames']}")

    # ---- K-sweep on Model C's RANSAC-selected inlier set only ----
    k_sweep_ransac = []
    c_res = ransac_results.get("C")
    if c_res is not None:
        accepted_set = set(c_res["accepted_frames"])
        idx = [i for i, f in enumerate(common) if f in accepted_set]
        t_in, xyz_in = t[idx], xyz[idx]
        p0_seed, v0_seed, _ = fit_constant_accel(t_in, xyz_in)
        for k in k_values:
            try:
                _p0, _v0, rms = fit_drag_given_k(t_in, xyz_in, k, g_fixed, p0_seed.copy(), v0_seed.copy())
                k_sweep_ransac.append((k, rms))
            except RuntimeError as e:
                log_append(f"{flight_name}: RANSAC-inlier K-sweep point K={k:.6e} FAILED -- {e} -- skipping")
        log_append(f"{flight_name}: RANSAC-inlier K-sweep complete, {len(k_sweep_ransac)}/{len(k_values)} "
                   f"points, on {len(idx)} inlier points (of {len(t)})")
    else:
        log_append(f"{flight_name}: Model C RANSAC failed, skipping RANSAC-inlier K-sweep")

    return dict(ransac_results=ransac_results, k_sweep_ransac=k_sweep_ransac,
                n_inliers_C=c_res["n_inliers"] if c_res is not None else None)


def write_ransac_outputs(results, ransac_by_flight, n_points_by_flight):
    """residual_vs_K_ransac.png (plain vs RANSAC, one panel per flight +
    pooled) and models_full_arc_residual_ransac.png (grouped bars, each
    model paired with its RANSAC variant) + matching CSVs. Does NOT touch
    the existing plain-fit files (decision #4)."""
    PHASE1_DIR.mkdir(parents=True, exist_ok=True)

    # ---- k_sweep_ransac.csv + residual_vs_K_ransac.png ----
    csv_path = PHASE1_DIR / "k_sweep_ransac.csv"
    rows = []
    for flight_name in FLIGHTS:
        for k, rms, _, _ in results[flight_name]["sweep_results"]:
            rows.append(dict(flight=flight_name, variant="plain", k=k, residual_rms_mm=rms))
        for k, rms in ransac_by_flight[flight_name]["k_sweep_ransac"]:
            rows.append(dict(flight=flight_name, variant="ransac", k=k, residual_rms_mm=rms))

    n1, n2 = n_points_by_flight["flight_01"], n_points_by_flight["flight_22"]
    plain1 = {k: rms for k, rms, _, _ in results["flight_01"]["sweep_results"]}
    plain2 = {k: rms for k, rms, _, _ in results["flight_22"]["sweep_results"]}
    common_k_plain = sorted(set(plain1) & set(plain2))
    for k in common_k_plain:
        pooled_rms = float(np.sqrt((n1 * plain1[k] ** 2 + n2 * plain2[k] ** 2) / (n1 + n2)))
        rows.append(dict(flight="pooled", variant="plain", k=k, residual_rms_mm=pooled_rms))

    ransac1 = dict(ransac_by_flight["flight_01"]["k_sweep_ransac"])
    ransac2 = dict(ransac_by_flight["flight_22"]["k_sweep_ransac"])
    n1_in = ransac_by_flight["flight_01"]["n_inliers_C"]
    n2_in = ransac_by_flight["flight_22"]["n_inliers_C"]
    common_k_ransac = sorted(set(ransac1) & set(ransac2))
    for k in common_k_ransac:
        pooled_rms = float(np.sqrt((n1_in * ransac1[k] ** 2 + n2_in * ransac2[k] ** 2) / (n1_in + n2_in)))
        rows.append(dict(flight="pooled", variant="ransac", k=k, residual_rms_mm=pooled_rms))

    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["flight", "variant", "k", "residual_rms_mm"])
        w.writeheader()
        for r in rows:
            w.writerow({"flight": r["flight"], "variant": r["variant"], "k": f"{r['k']:.8e}",
                        "residual_rms_mm": f"{r['residual_rms_mm']:.4f}"})
    print(f"-> {csv_path}")
    log_append(f"wrote {csv_path} ({len(rows)} rows)")

    fig, axes = plt.subplots(1, 3, figsize=(16, 5.5), sharey=False)
    panels = [("flight_01", plain1, ransac1), ("flight_22", plain2, ransac2)]
    plain_pooled = {k: np.sqrt((n1 * plain1[k] ** 2 + n2 * plain2[k] ** 2) / (n1 + n2)) for k in common_k_plain}
    ransac_pooled = {k: np.sqrt((n1_in * ransac1[k] ** 2 + n2_in * ransac2[k] ** 2) / (n1_in + n2_in)) for k in common_k_ransac}
    panels.append(("pooled", plain_pooled, ransac_pooled))

    for ax, (name, plain_d, ransac_d) in zip(axes, panels):
        ks_p = sorted(plain_d)
        ks_r = sorted(ransac_d)
        ax.plot(ks_p, [plain_d[k] for k in ks_p], marker="o", color="tab:gray", label="plain (all points)")
        ax.plot(ks_r, [ransac_d[k] for k in ks_r], marker="s", color="tab:red", label="RANSAC (inliers only)")
        ax.set_xlabel("K (1/mm)")
        ax.set_title(name)
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("full-arc residual RMS (mm)")
    fig.suptitle("Model C: residual vs K -- plain vs RANSAC (small multiples, decision #5)")
    fig.tight_layout()
    plot_path = PHASE1_DIR / "residual_vs_K_ransac.png"
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)
    print(f"-> {plot_path}")
    log_append(f"wrote {plot_path}")

    # ---- models_full_arc_residual_ransac.csv/.png ----
    csv_path2 = PHASE1_DIR / "models_full_arc_residual_ransac.csv"
    with open(csv_path2, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["flight", "model", "variant", "residual_rms_mm", "n_inliers", "n_total"])
        for flight_name in FLIGHTS:
            r = results[flight_name]
            rr = ransac_by_flight[flight_name]["ransac_results"]
            n_total = n_points_by_flight[flight_name]
            w.writerow([flight_name, "A_free_gravity", "plain", f"{r['rms_a']:.4f}", n_total, n_total])
            w.writerow([flight_name, "B_fixed_gravity", "plain", f"{r['rms_b']:.4f}", n_total, n_total])
            w.writerow([flight_name, "C_fixed_gravity_drag_refined", "plain", f"{r['rms_c_refined']:.4f}", n_total, n_total])
            for model, key in (("A", "A_free_gravity"), ("B", "B_fixed_gravity"), ("C", "C_fixed_gravity_drag_refined")):
                res_m = rr.get(model)
                if res_m is None:
                    w.writerow([flight_name, key, "ransac", "", "", n_total])
                else:
                    w.writerow([flight_name, key, "ransac", f"{res_m['residual_rms_mm']:.4f}", res_m["n_inliers"], n_total])
    print(f"-> {csv_path2}")
    log_append(f"wrote {csv_path2}")

    fig, ax = plt.subplots(figsize=(10, 6))
    model_keys = [("rms_a", "A"), ("rms_b", "B"), ("rms_c_refined", "C")]
    model_names = ["A (free gravity)", "B (fixed gravity)", "C (fixed gravity + drag)"]
    x = np.arange(len(FLIGHTS))
    n_groups = len(model_keys)
    width = 0.8 / (n_groups * 2)
    for i, (plain_key, model) in enumerate(model_keys):
        plain_vals = [results[f][plain_key] for f in FLIGHTS]
        ransac_vals = [ransac_by_flight[f]["ransac_results"][model]["residual_rms_mm"]
                       if ransac_by_flight[f]["ransac_results"].get(model) is not None else np.nan
                       for f in FLIGHTS]
        offset_plain = (i * 2 - n_groups + 0.5) * width
        offset_ransac = (i * 2 + 1 - n_groups + 0.5) * width
        ax.bar(x + offset_plain, plain_vals, width, color=f"C{i}", alpha=0.5,
               label=f"{model_names[i]} (plain)")
        ax.bar(x + offset_ransac, ransac_vals, width, color=f"C{i}", alpha=1.0,
               label=f"{model_names[i]} (RANSAC)")
    ax.set_xticks(x)
    ax.set_xticklabels(FLIGHTS)
    ax.set_ylabel("full-arc residual RMS (mm)")
    ax.set_title("Model A/B/C full-arc residual: plain vs RANSAC (paired bars, decision #5)")
    ax.legend(fontsize=7, ncol=2)
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    plot_path2 = PHASE1_DIR / "models_full_arc_residual_ransac.png"
    fig.savefig(plot_path2, dpi=150)
    plt.close(fig)
    print(f"-> {plot_path2}")
    log_append(f"wrote {plot_path2}")


def joint_fit_shared_k(tracks, g_fixed, k_guess):
    """Fit a SEPARATE (p0, v0) per flight but a SINGLE shared k across all
    flights, minimizing combined position residual. NOT a literal single
    fit_drag_free_k call across concatenated points (which would force one
    p0/v0 across physically unrelated arcs) -- see worklog for why this is
    the physically meaningful interpretation of "pooling for K". tracks:
    list of (t, xyz, p0_guess, v0_guess)."""
    n_flights = len(tracks)
    x0 = []
    for t, xyz, p0_guess, v0_guess in tracks:
        x0.extend(p0_guess.tolist())
        x0.extend(v0_guess.tolist())
    x0.append(k_guess)
    x0 = np.array(x0, dtype=np.float64)

    def resid(x):
        k = x[-1]
        out = []
        for i, (t, xyz, _, _) in enumerate(tracks):
            p0 = x[i * 6: i * 6 + 3]
            v0 = x[i * 6 + 3: i * 6 + 6]
            pred = simulate_drag(p0, v0, k, g_fixed, t)
            out.append((pred - xyz).ravel())
        return np.concatenate(out)

    result = least_squares(resid, x0, method="lm", max_nfev=6000)
    k_fit = float(result.x[-1])
    rms = float(np.sqrt(np.mean(result.fun ** 2)))
    return k_fit, rms


def write_k_sweep_outputs(results, n_points_by_flight):
    """CSV of every candidate K tested (flight_01, flight_22, and a
    count-weighted 'pooled' row per K -- combining each flight's own best-fit
    residual at that K, valid because the pooled model shares K but fits
    p0/v0 independently per flight, so the per-flight sweep fits ARE the
    per-flight-optimal fits at each K) + a residual-vs-K plot per flight."""
    PHASE1_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = PHASE1_DIR / "k_sweep.csv"

    rows = []
    for flight_name in FLIGHTS:
        for k, rms, _, _ in results[flight_name]["sweep_results"]:
            rows.append(dict(flight=flight_name, k=k, residual_rms_mm=rms))

    # pooled: for each k present in BOTH flights' sweeps (same grid, so this
    # is just zip), combine via count-weighted RMS (see worklog for the
    # derivation -- equivalent to the joint fit's per-k residual since p0/v0
    # are fit independently per flight in the pooled model too).
    n1 = n_points_by_flight["flight_01"]
    n2 = n_points_by_flight["flight_22"]
    sweep1 = {k: rms for k, rms, _, _ in results["flight_01"]["sweep_results"]}
    sweep2 = {k: rms for k, rms, _, _ in results["flight_22"]["sweep_results"]}
    common_k = sorted(set(sweep1) & set(sweep2))
    for k in common_k:
        rms1, rms2 = sweep1[k], sweep2[k]
        pooled_rms = float(np.sqrt((n1 * rms1 ** 2 + n2 * rms2 ** 2) / (n1 + n2)))
        rows.append(dict(flight="pooled", k=k, residual_rms_mm=pooled_rms))

    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["flight", "k", "residual_rms_mm"])
        w.writeheader()
        for r in rows:
            w.writerow({"flight": r["flight"], "k": f"{r['k']:.8e}",
                        "residual_rms_mm": f"{r['residual_rms_mm']:.4f}"})
    print(f"-> {csv_path}")
    log_append(f"wrote {csv_path} ({len(rows)} rows: {len(results['flight_01']['sweep_results'])} "
               f"flight_01 + {len(results['flight_22']['sweep_results'])} flight_22 + "
               f"{len(common_k)} pooled)")

    fig, ax = plt.subplots(figsize=(9, 6))
    colors = {"flight_01": "tab:blue", "flight_22": "tab:orange", "pooled": "tab:green"}
    for flight_name in FLIGHTS:
        ks = [k for k, rms, _, _ in results[flight_name]["sweep_results"]]
        rmss = [rms for k, rms, _, _ in results[flight_name]["sweep_results"]]
        ax.plot(ks, rmss, marker="o", color=colors[flight_name], label=flight_name)
        k_r = results[flight_name]["k_refined"]
        if k_r is not None:
            ax.axvline(k_r, color=colors[flight_name], linestyle="--", alpha=0.5,
                       label=f"{flight_name} refined K={k_r:.3e}")
    pooled_rmss = [np.sqrt((n1 * sweep1[k] ** 2 + n2 * sweep2[k] ** 2) / (n1 + n2)) for k in common_k]
    ax.plot(common_k, pooled_rmss, marker="s", color=colors["pooled"], label="pooled (count-weighted)")
    ax.set_xlabel("K (1/mm)")
    ax.set_ylabel("full-arc residual RMS (mm)")
    ax.set_title("Model C: residual vs K (sweep grid)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    plot_path = PHASE1_DIR / "residual_vs_K.png"
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)
    print(f"-> {plot_path}")
    log_append(f"wrote {plot_path}")


def write_model_comparison_outputs(results):
    """Bar chart + CSV comparing Models A/B/C(refined) full-arc residual per
    flight."""
    csv_path = PHASE1_DIR / "models_full_arc_residual.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["flight", "model", "residual_rms_mm"])
        for flight_name in FLIGHTS:
            r = results[flight_name]
            w.writerow([flight_name, "A_free_gravity", f"{r['rms_a']:.4f}"])
            w.writerow([flight_name, "B_fixed_gravity", f"{r['rms_b']:.4f}"])
            w.writerow([flight_name, "C_fixed_gravity_drag_refined", f"{r['rms_c_refined']:.4f}"])
    print(f"-> {csv_path}")
    log_append(f"wrote {csv_path}")

    fig, ax = plt.subplots(figsize=(8, 6))
    model_names = ["A (free gravity)", "B (fixed gravity)", "C (fixed gravity + drag)"]
    x = np.arange(len(FLIGHTS))
    width = 0.25
    for i, key in enumerate(["rms_a", "rms_b", "rms_c_refined"]):
        vals = [results[f][key] for f in FLIGHTS]
        ax.bar(x + (i - 1) * width, vals, width, label=model_names[i])
    ax.set_xticks(x)
    ax.set_xticklabels(FLIGHTS)
    ax.set_ylabel("full-arc residual RMS (mm)")
    ax.set_title("Model A/B/C full-arc fit residual per flight (Phase 1 diagnostic, NOT the decisive test)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    plot_path = PHASE1_DIR / "models_full_arc_residual.png"
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)
    print(f"-> {plot_path}")
    log_append(f"wrote {plot_path}")


def main():
    log_append("=== drag_k_discovery.py: Phase 1 K discovery starting ===")

    g_fixed = load_g_fixed(G_FIXED_NPZ)
    log_append(f"g_fixed loaded: {g_fixed}, |g_fixed|={np.linalg.norm(g_fixed):.2f} mm/s^2")
    log_append(f"K estimate (physical, volleyball): K_SI~{K_SI_ESTIMATE:.4f} (1/m) "
               f"-> K_mm~{K_MM_ESTIMATE:.6e} (1/mm), sweep centered here (0.1x-5x)")

    K0, D0, K1, D1, R, T = load_calib(CALIB_DIR, EXTRINSICS)
    P0 = np.hstack([np.eye(3), np.zeros((3, 1))])
    P1 = np.hstack([R, T.reshape(3, 1)])

    results = {}
    tracks_for_pooling = {}
    tracks_with_common = {}
    n_points_by_flight = {}
    for flight_name in FLIGHTS:
        common, t, xyz = triangulate_full_track(flight_name, K0, D0, K1, D1, P0, P1)
        log_append(f"{flight_name}: triangulated {len(common)} labelled points "
                   f"[frames {common[0]}..{common[-1]}]")
        res = discover_k_for_flight(flight_name, t, xyz, g_fixed)
        results[flight_name] = res
        tracks_for_pooling[flight_name] = (t, xyz, res["p0_a"], res["v0_a"])
        tracks_with_common[flight_name] = (common, t, xyz, res["k_refined"])
        n_points_by_flight[flight_name] = len(common)

    write_k_sweep_outputs(results, n_points_by_flight)
    write_model_comparison_outputs(results)

    # ---- RANSAC pass (task: 2026-07-28 RANSAC continuation) ----
    ransac_by_flight = {}
    for flight_name in FLIGHTS:
        common, t, xyz, k_ref = tracks_with_common[flight_name]
        ransac_by_flight[flight_name] = ransac_discover_for_flight(
            flight_name, common, t, xyz, g_fixed, k_ref, results[flight_name]["k_values"])
    write_ransac_outputs(results, ransac_by_flight, n_points_by_flight)

    print("\n=== Per-flight summary ===")
    for flight_name in FLIGHTS:
        r = results[flight_name]
        print(f"{flight_name}: A_rms={r['rms_a']:.2f}mm  B_rms={r['rms_b']:.2f}mm  "
              f"C_sweep_rms={r['rms_c_sweep']:.2f}mm (K={r['k_sweep_best']:.4e})  "
              f"C_refined_rms={r['rms_c_refined']:.2f}mm (K={r['k_refined']:.4e})")

    # ---- compare per-flight K before pooling ----
    k1 = results["flight_01"]["k_refined"]
    k2 = results["flight_22"]["k_refined"]
    ratio = max(k1, k2) / min(k1, k2) if min(k1, k2) > 0 else float("inf")
    print(f"\nK agreement: flight_01 K={k1:.4e}  flight_22 K={k2:.4e}  ratio={ratio:.2f}x")
    log_append(f"K comparison: flight_01 K={k1:.6e}, flight_22 K={k2:.6e}, ratio={ratio:.2f}x")

    AGREEMENT_RATIO_THRESHOLD = 3.0  # more than 3x apart = substantial disagreement
    if ratio > AGREEMENT_RATIO_THRESHOLD:
        print(f"\n*** SUBSTANTIAL DISAGREEMENT (ratio={ratio:.2f}x > {AGREEMENT_RATIO_THRESHOLD}x) ***")
        print("Per decision #1: reporting this as a finding, NOT silently pooling. "
              "Waiting for guidance before choosing a final K.")
        log_append(f"*** K DISAGREEMENT: ratio={ratio:.2f}x exceeds {AGREEMENT_RATIO_THRESHOLD}x threshold "
                   "-- flagging as a finding, not pooling automatically ***")
        return

    # ---- pool: shared K, separate p0/v0 per flight ----
    k_guess = (k1 + k2) / 2.0
    tracks = [tracks_for_pooling[f] for f in FLIGHTS]
    k_pooled, rms_pooled = joint_fit_shared_k(tracks, g_fixed, k_guess)
    print(f"\nPooled joint fit (shared K, separate p0/v0 per flight): "
          f"K={k_pooled:.4e}  combined_residual_rms={rms_pooled:.2f} mm")
    log_append(f"Pooled joint fit: K={k_pooled:.6e} 1/mm, combined_residual_rms={rms_pooled:.2f}mm "
               f"(fit over {sum(len(t) for t,_,_,_ in tracks)} points across {len(tracks)} flights, "
               f"time origin = each flight's own first labelled frame, t=0 independently per flight)")

    log_append("=== drag_k_discovery.py: Phase 1 K discovery complete ===")


if __name__ == "__main__":
    main()
