# trajectory_model_prediction_sweep.py
# Phase 2 (the decisive test) of the gravity-vs-drag comparison -- see
# claude/prompts/2026-07-27_1818_gravity_vs_drag_trajectory_fitting.md and
# claude/claude_logs/2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md.
#
# Extends predict_sweep.py's own N-sweep methodology (fit first N frames of a
# window -> predict forward -> compare to the flight's own withheld LAST
# labelled frame) to 3 models x 2 point sources = 6 curves per flight:
#   Model A (free gravity)          -- fit_constant_accel
#   Model B (fixed gravity, linear) -- fit_constant_accel_fixed_g
#   Model C (fixed gravity + drag)  -- fit_drag_given_k, K FIXED at Phase 1's
#                                       pooled result (NOT refit per window --
#                                       decision #4)
# on BOTH the labelled-points track (model floor) and the detected-points
# track (tuned detector output, decision #5 -- NOT analysis_3).
#
# Usage:
#   python src/stereo/trajectory_model_prediction_sweep.py

import csv
import sys
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

from src.stereo.label_vs_detection import load_calib, triangulate, FRAME_DT
from src.stereo.trajectory_fit import (
    fit_constant_accel, predict_at,
    fit_constant_accel_fixed_g, predict_at_fixed_g,
    fit_drag_given_k, load_g_fixed,
    ransac_fit, build_model_fit_predict,
    RANSAC_INLIER_THRESHOLD_MM, RANSAC_MIN_SAMPLES, RANSAC_N_ITERATIONS, RANSAC_SEED,
)
from src.stereo.drag_k_discovery import LOADERS as LABEL_LOADERS

CALIB_DIR = REPO_ROOT / "calibration_outputs"
EXTRINSICS = REPO_ROOT / "calibration_outputs" / "2026_07_15" / "stereo_extrinsic.npz"
G_FIXED_NPZ = (REPO_ROOT / "data" / "2026_07_15_gym" / "flight_binning" /
               "world_frame_validation" / "registration_world_transform.npz")

# Phase 1's pooled, Checkpoint-1-approved K (shared K, separate p0/v0 per
# flight joint fit over flight_01 + flight_22's full labelled tracks) --
# HELD FIXED here, not refit per window (decision #4). See the 2026-07-27
# worklog's "[phase 1 results]" section for the full derivation.
K_FIXED = 6.053818e-05  # 1/mm

TUNED_DETECTIONS_DIR = (REPO_ROOT / "results" / "detector_tuning" / "detections" /
                         "03_stride1_thresh16_openk3_area30_circ0.3" / "2026_07_15_gym")

FLIGHTS = ["flight_01", "flight_22"]

LOG_PATH = REPO_ROOT / "claude" / "claude_logs" / "2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md"
RESULTS_DIR = REPO_ROOT / "results" / "trajectory_fit_comparison"
PHASE2_DIR = RESULTS_DIR / "phase2"


def log_append(message: str) -> None:
    with open(LOG_PATH, "a") as f:
        f.write(f"- [{datetime.now().strftime('%H:%M:%S')}] {message}\n")


def load_tuned_detections(flight_name):
    """Tuned-detector per-cam CSVs (frame_number,u,v) -> {cam: {frame: (u,v)}}
    -- adapter combining the two separate per-cam files into the same shape
    load_points_csv/LABEL_LOADERS produce, per decision #5 (tuned detections,
    NOT analysis_3)."""
    dets = {0: {}, 1: {}}
    for cam in (0, 1):
        csv_path = TUNED_DETECTIONS_DIR / f"{flight_name}_cam{cam}_detections.csv"
        with open(csv_path, newline="") as f:
            for row in csv.DictReader(f):
                dets[cam][int(row["frame_number"])] = (float(row["u"]), float(row["v"]))
    return dets


def fit_and_predict(model, t_win, xyz_win, g_fixed, t_target):
    """Returns predicted xyz at t_target for the given model, fit on
    (t_win, xyz_win). Raises RuntimeError if the fit fails (caller skips)."""
    if model == "A":
        p0, v0, a = fit_constant_accel(t_win, xyz_win)
        return predict_at(p0, v0, a, t_target)
    elif model == "B":
        p0, v0 = fit_constant_accel_fixed_g(t_win, xyz_win, g_fixed)
        return predict_at_fixed_g(p0, v0, g_fixed, t_target)
    elif model == "C":
        # seed p0/v0 from Model A's own fit on this window (nuisance params,
        # not borrowed gravity -- K is fixed, g is fixed, only p0/v0 vary)
        p0_a, v0_a, _ = fit_constant_accel(t_win, xyz_win)
        p0, v0, _rms = fit_drag_given_k(t_win, xyz_win, K_FIXED, g_fixed, p0_a, v0_a)
        from src.stereo.trajectory_fit import simulate_drag
        return simulate_drag(p0, v0, K_FIXED, g_fixed, np.array([t_target]))[0]
    raise ValueError(model)


def fit_and_predict_ransac(model, t_win, xyz_win, frame_win, g_fixed, t_target):
    """RANSAC-robustified counterpart of fit_and_predict. If the window is
    too small for RANSAC's min_samples, falls back to the plain fit (RANSAC
    isn't meaningfully applicable to an already-underdetermined window --
    this is exactly why Model A's low-N blowup is expected to be
    UNCHANGED by RANSAC, per decision #1). Returns (pred, rejected_frames or
    None-if-fallback)."""
    min_samples = RANSAC_MIN_SAMPLES[model]
    if len(t_win) < min_samples:
        pred = fit_and_predict(model, t_win, xyz_win, g_fixed, t_target)
        return pred, None
    fit_fn, predict_fn = build_model_fit_predict(model, g_fixed, k_fixed=K_FIXED if model == "C" else None)
    res = ransac_fit(t_win, xyz_win, fit_fn, predict_fn,
                      min_samples=min_samples, inlier_threshold_mm=RANSAC_INLIER_THRESHOLD_MM,
                      n_iterations=RANSAC_N_ITERATIONS[model], random_seed=RANSAC_SEED,
                      frame_numbers=frame_win)
    pred = predict_fn(res["params"], np.array([t_target]))[0]
    return pred, res["rejected_frames"]


def run_flight(flight_name, K0, D0, K1, D1, P0, P1, g_fixed):
    print(f"\n=== {flight_name} ===")
    log_append(f"{flight_name}: Phase 2 prediction sweep starting")

    labels = LABEL_LOADERS[flight_name]()
    dets = load_tuned_detections(flight_name)

    label_common = sorted(set(labels[0]) & set(labels[1]))
    det_common = sorted(set(dets[0]) & set(dets[1]))
    print(f"label_common: {len(label_common)} frames [{label_common[0]}..{label_common[-1]}]")
    print(f"det_common:   {len(det_common)} frames [{det_common[0]}..{det_common[-1]}]")
    log_append(f"{flight_name}: label_common={len(label_common)} frames, "
               f"det_common={len(det_common)} frames (tuned detections)")

    target_frame = label_common[-1]
    target_uv0 = np.array([labels[0][target_frame]])
    target_uv1 = np.array([labels[1][target_frame]])
    target_xyz = triangulate(target_uv0, target_uv1, K0, D0, K1, D1, P0, P1)[0]

    fit_frames = sorted((set(label_common) & set(det_common)) - {target_frame})
    print(f"fit_frames (label & det, target excluded): {len(fit_frames)} "
          f"[{fit_frames[0]}..{fit_frames[-1]}]")
    log_append(f"{flight_name}: target_frame={target_frame}, "
               f"fit_frames={len(fit_frames)} [{fit_frames[0]}..{fit_frames[-1]}]")

    if len(fit_frames) < 3:
        log_append(f"{flight_name}: SKIPPED -- only {len(fit_frames)} usable fit frames (<3)")
        return None

    fit_uv0_label = np.array([labels[0][f] for f in fit_frames])
    fit_uv1_label = np.array([labels[1][f] for f in fit_frames])
    xyz_label_pts = triangulate(fit_uv0_label, fit_uv1_label, K0, D0, K1, D1, P0, P1)

    fit_uv0_det = np.array([dets[0][f] for f in fit_frames])
    fit_uv1_det = np.array([dets[1][f] for f in fit_frames])
    xyz_det_pts = triangulate(fit_uv0_det, fit_uv1_det, K0, D0, K1, D1, P0, P1)

    t0_frame = fit_frames[0]
    t_full = np.array([(f - t0_frame) * FRAME_DT for f in fit_frames])
    t_target = (target_frame - t0_frame) * FRAME_DT

    N_max = len(fit_frames)
    N_values = list(range(3, N_max + 1))

    rows = []
    n_converge_fail = 0
    n_converge_fail_ransac = 0
    n_ransac_fallback = 0
    # flight_22's confirmed hand-pickup frames -- scoped to flight_22 ONLY.
    # A plain, unscoped frame-number set would spuriously "match" other
    # flights' own frame numbers (e.g. flight_01's fit_frames happen to
    # start at frame 44 too, a coincidence with nothing to do with
    # contamination -- caught this exact false-positive tag in an earlier
    # run, see worklog).
    known_bad_frames = {44, 45, 46, 47} if flight_name == "flight_22" else set()
    for N in N_values:
        t_win = t_full[:N]
        frame_win = fit_frames[:N]
        last_fit_frame = frame_win[-1]
        t_extrap_ms = (target_frame - last_fit_frame) * FRAME_DT * 1000.0

        row = dict(N=N, last_fit_frame=last_fit_frame, t_extrap_ms=t_extrap_ms)
        for model in ("A", "B", "C"):
            for source, xyz_pts in (("label", xyz_label_pts), ("det", xyz_det_pts)):
                # ---- plain fit (unchanged, feeds the existing prediction_sweep.csv) ----
                try:
                    pred = fit_and_predict(model, t_win, xyz_pts[:N], g_fixed, t_target)
                    err = float(np.linalg.norm(pred - target_xyz))
                except RuntimeError as e:
                    log_append(f"{flight_name} N={N} model={model} source={source}: "
                               f"FIT FAILED TO CONVERGE -- {e} -- skipping this point")
                    err = np.nan
                    n_converge_fail += 1
                row[f"err_{model}_{source}_mm"] = err

                # ---- RANSAC fit (new, feeds prediction_sweep_ransac.csv) ----
                try:
                    pred_r, rejected = fit_and_predict_ransac(model, t_win, xyz_pts[:N], frame_win, g_fixed, t_target)
                    err_r = float(np.linalg.norm(pred_r - target_xyz))
                    if rejected is None:
                        n_ransac_fallback += 1
                    elif rejected:
                        overlap = known_bad_frames & set(rejected)
                        tag = " <- includes KNOWN hand-pickup frame(s)" if overlap else ""
                        log_append(f"{flight_name} N={N} model={model} source={source}: "
                                   f"RANSAC rejected {rejected}{tag}")
                except RuntimeError as e:
                    log_append(f"{flight_name} N={N} model={model} source={source}: "
                               f"RANSAC FIT FAILED TO CONVERGE -- {e} -- skipping this point")
                    err_r = np.nan
                    n_converge_fail_ransac += 1
                row[f"err_{model}_{source}_ransac_mm"] = err_r
        rows.append(row)

    if n_converge_fail:
        log_append(f"{flight_name}: {n_converge_fail} (N, model, source) plain-fit points failed to "
                   f"converge across the full sweep (of {len(N_values) * 6} total) -- see above for detail")
    if n_converge_fail_ransac:
        log_append(f"{flight_name}: {n_converge_fail_ransac} (N, model, source) RANSAC-fit points failed "
                   f"to converge (of {len(N_values) * 6} total)")
    log_append(f"{flight_name}: {n_ransac_fallback} (N, model, source) points had N < RANSAC's "
               f"min_samples -- fell back to the plain fit (expected at low N, matches decision #1)")

    print(f"{flight_name}: swept N={N_values[0]}..{N_values[-1]}, "
          f"{n_converge_fail} plain convergence failures, {n_converge_fail_ransac} RANSAC convergence failures")
    log_append(f"{flight_name}: sweep complete, {len(rows)} N-values, "
               f"{n_converge_fail} plain + {n_converge_fail_ransac} RANSAC convergence failures")

    return dict(rows=rows, target_frame=target_frame, N_values=N_values)


def write_csv(all_results):
    PHASE2_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = PHASE2_DIR / "prediction_sweep.csv"
    fieldnames = ["flight", "N", "last_fit_frame", "t_extrap_ms",
                  "err_A_label_mm", "err_A_det_mm",
                  "err_B_label_mm", "err_B_det_mm",
                  "err_C_label_mm", "err_C_det_mm"]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for flight_name, res in all_results.items():
            if res is None:
                continue
            for r in res["rows"]:
                out = {"flight": flight_name}
                for k in fieldnames[1:]:
                    v = r[k]
                    out[k] = f"{v:.4f}" if isinstance(v, float) and not np.isnan(v) else \
                        ("" if isinstance(v, float) else v)
                w.writerow(out)
    print(f"-> {csv_path}")
    log_append(f"wrote {csv_path}")


def write_csv_ransac(all_results):
    """New file, additive -- does NOT touch prediction_sweep.csv (decision #4)."""
    PHASE2_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = PHASE2_DIR / "prediction_sweep_ransac.csv"
    fieldnames = ["flight", "N", "last_fit_frame", "t_extrap_ms",
                  "err_A_label_ransac_mm", "err_A_det_ransac_mm",
                  "err_B_label_ransac_mm", "err_B_det_ransac_mm",
                  "err_C_label_ransac_mm", "err_C_det_ransac_mm"]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for flight_name, res in all_results.items():
            if res is None:
                continue
            for r in res["rows"]:
                out = {"flight": flight_name}
                for k in fieldnames[1:]:
                    v = r[k]
                    out[k] = f"{v:.4f}" if isinstance(v, float) and not np.isnan(v) else \
                        ("" if isinstance(v, float) else v)
                w.writerow(out)
    print(f"-> {csv_path}")
    log_append(f"wrote {csv_path}")


def plot_flight_ransac(flight_name, res):
    """decision #5: one row of 3 subplots (one per model), each showing that
    model's plain-vs-RANSAC pair (label and det) -- small multiples, not 6
    lines on one axis."""
    rows = res["rows"]
    N_values = np.array(res["N_values"])

    model_titles = {"A": "A: free gravity", "B": "B: fixed gravity", "C": "C: fixed gravity + drag"}
    fig, axes = plt.subplots(1, 3, figsize=(17, 5.5), sharex=True)
    for ax, model in zip(axes, ("A", "B", "C")):
        for source, plain_style, ransac_style, color in (
            ("label", ("-", "o", "tab:gray"), ("-", "o", "tab:blue"), None),
            ("det", ("--", "s", "tab:gray"), ("--", "s", "tab:red"), None),
        ):
            plain_ys = np.array([r[f"err_{model}_{source}_mm"] for r in rows])
            ransac_ys = np.array([r[f"err_{model}_{source}_ransac_mm"] for r in rows])
            ls, mk, c = plain_style
            ax.plot(N_values, plain_ys, linestyle=ls, marker=mk, markersize=3, color=c, alpha=0.6,
                    label=f"plain ({source})")
            ls, mk, c = ransac_style
            ax.plot(N_values, ransac_ys, linestyle=ls, marker=mk, markersize=3, color=c,
                    label=f"RANSAC ({source})")
        ax.set_yscale("log")
        ax.set_xlabel("N (frames in fit window)")
        ax.set_title(model_titles[model])
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3, which="both")
    axes[0].set_ylabel("prediction error at target (mm, log scale)")
    fig.suptitle(f"{flight_name}: plain vs RANSAC prediction error, per model -- target frame {res['target_frame']}")
    fig.tight_layout()
    plot_path = PHASE2_DIR / f"prediction_sweep_ransac_{flight_name}.png"
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)
    print(f"-> {plot_path}")
    log_append(f"wrote {plot_path}")


def plot_zoom_flight_22(res):
    """decision #5: focused before/after pair zoomed on N~40-50 (the one
    confirmed contamination case) -- matters more than the comprehensive
    view, so gets its own dedicated plot."""
    rows = res["rows"]
    N_values = np.array(res["N_values"])
    zoom_mask = (N_values >= 35) & (N_values <= 55)
    N_zoom = N_values[zoom_mask]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), sharey=True)
    for ax, source in zip(axes, ("label", "det")):
        for model, color in (("A", "tab:blue"), ("B", "tab:orange"), ("C", "tab:green")):
            plain_ys = np.array([r[f"err_{model}_{source}_mm"] for r in rows])[zoom_mask]
            ransac_ys = np.array([r[f"err_{model}_{source}_ransac_mm"] for r in rows])[zoom_mask]
            ax.plot(N_zoom, plain_ys, linestyle="--", marker="o", markersize=4, color=color, alpha=0.5,
                    label=f"{model} plain")
            ax.plot(N_zoom, ransac_ys, linestyle="-", marker="s", markersize=4, color=color,
                    label=f"{model} RANSAC")
        ax.axvspan(44, 47, color="red", alpha=0.08, label="known hand-pickup frames (44-47)")
        ax.set_yscale("log")
        ax.set_xlabel("N (frames in fit window)")
        ax.set_title(f"flight_22, {source} points")
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3, which="both")
    axes[0].set_ylabel("prediction error at target (mm, log scale)")
    fig.suptitle("flight_22: zoomed N~35-55 -- plain vs RANSAC around the confirmed contamination window")
    fig.tight_layout()
    plot_path = PHASE2_DIR / "prediction_sweep_ransac_zoom_flight_22.png"
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)
    print(f"-> {plot_path}")
    log_append(f"wrote {plot_path}")


def plot_flight(flight_name, res):
    rows = res["rows"]
    N_values = np.array(res["N_values"])
    t_extrap = np.array([r["t_extrap_ms"] for r in rows])

    model_colors = {"A": "tab:blue", "B": "tab:orange", "C": "tab:green"}
    model_labels = {"A": "A: free gravity", "B": "B: fixed gravity", "C": "C: fixed gravity + drag"}

    fig, ax = plt.subplots(figsize=(10, 7))
    for model in ("A", "B", "C"):
        for source, linestyle, marker in (("label", "-", "o"), ("det", "--", "s")):
            ys = np.array([r[f"err_{model}_{source}_mm"] for r in rows])
            ax.plot(N_values, ys, linestyle=linestyle, marker=marker, markersize=4,
                    color=model_colors[model],
                    label=f"{model_labels[model]} ({source})")
    ax.set_xlabel("N (frames in fit window)")
    ax.set_ylabel("prediction error at target (mm, log scale)")
    ax.set_yscale("log")
    ax.set_title(f"{flight_name}: A/B/C prediction error vs N -- target frame {res['target_frame']}")
    ax.legend(fontsize=7, loc="upper right")
    ax.grid(True, alpha=0.3, which="both")

    N_sorted = N_values.astype(float)
    t_sorted = t_extrap.astype(float)
    def n_to_t(n):
        return np.interp(n, N_sorted, t_sorted)
    def t_to_n(t):
        return np.interp(t, t_sorted[::-1], N_sorted[::-1])
    secax = ax.secondary_xaxis("top", functions=(n_to_t, t_to_n))
    secax.set_xlabel("t_extrap (ms)")

    fig.tight_layout()
    plot_path = PHASE2_DIR / f"prediction_sweep_{flight_name}.png"
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)
    print(f"-> {plot_path}")
    log_append(f"wrote {plot_path}")


def main():
    log_append("=== trajectory_model_prediction_sweep.py: Phase 2 starting ===")
    print(f"K_FIXED (from Phase 1 pooled fit, held fixed per decision #4): {K_FIXED:.6e} 1/mm")
    log_append(f"K_FIXED = {K_FIXED:.6e} 1/mm (Phase 1 pooled result, Checkpoint-1 approved)")

    g_fixed = load_g_fixed(G_FIXED_NPZ)
    log_append(f"g_fixed loaded: |g_fixed|={np.linalg.norm(g_fixed):.2f} mm/s^2")
    log_append(f"RANSAC config: inlier_threshold={RANSAC_INLIER_THRESHOLD_MM}mm, "
               f"min_samples={RANSAC_MIN_SAMPLES}, n_iterations={RANSAC_N_ITERATIONS}, "
               f"seed={RANSAC_SEED} (shared constants from trajectory_fit.py)")

    K0, D0, K1, D1, R, T = load_calib(CALIB_DIR, EXTRINSICS)
    P0 = np.hstack([np.eye(3), np.zeros((3, 1))])
    P1 = np.hstack([R, T.reshape(3, 1)])

    all_results = {}
    for flight_name in FLIGHTS:
        all_results[flight_name] = run_flight(flight_name, K0, D0, K1, D1, P0, P1, g_fixed)

    write_csv(all_results)
    write_csv_ransac(all_results)
    for flight_name, res in all_results.items():
        if res is not None:
            plot_flight(flight_name, res)
            plot_flight_ransac(flight_name, res)
    if all_results.get("flight_22") is not None:
        plot_zoom_flight_22(all_results["flight_22"])

    log_append("=== trajectory_model_prediction_sweep.py: Phase 2 complete ===")


if __name__ == "__main__":
    main()
