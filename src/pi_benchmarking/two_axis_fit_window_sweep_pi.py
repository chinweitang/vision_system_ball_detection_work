#!/usr/bin/env python3
"""two_axis_fit_window_sweep_pi.py -- RUNS ON THE PI.

The design-target validation this whole investigation has been building
toward: sweeps fit-window duration W and measures, on REAL Pi hardware,
both C(W) (real detect+triangulate+RANSAC compute time, rect kernel,
n_iterations=3, threshold=75mm -- decisions 63/68/70) and error(W) in
POSITION and VELOCITY, to find the largest W where W + C(W) <= 430ms.

Detection runs ONCE per flight (not once per W) -- the expensive part.
Records PER-FRAME-PAIR detect time (both cams) so each W's compute cost
can be reconstructed by summing only the real measured times for frames
that actually fall inside that W, without re-running detection 7x per
flight. Triangulation and the RANSAC fit ARE re-run per (flight, W), since
those genuinely depend on which points are in the window.

Velocity: trajectory_fit.simulate_drag() computes the full 6D ODE state
(position+velocity) internally but only returns position (verified by
reading the source, not assumed -- see worklog). simulate_drag_with_velocity()
below mirrors it exactly, keeping both halves of sol.y, and is called with
the REAL fitted (p0,v0) params that come out of the real, unmodified
ransac_fit()/build_model_fit_predict() chain -- only the final "evaluate at
query time" step is mirrored, not the fitting itself. Does not touch
trajectory_fit.py.

Two independent velocity "ground truths", reported separately, never
collapsed into one number (per explicit instruction):
  (a) Model C fit on the FULL observed trajectory (not W-limited), same
      flight, queried at target time -- a self-consistency check (same
      model, more data), NOT independent ground truth.
  (b) Finite-difference velocity from the 2 detected 3D points nearest the
      target time in the full track -- genuinely independent, no model,
      expected noisier.

Detection: cam0 then cam1, SERIAL (confirmed sufficient for the rect
branch by the throughput check -- concurrency not needed/not implemented).

Does NOT modify detector_core.py or trajectory_fit.py.

Usage (on the Pi, inside the venv):
    ~/benchmark/venv/bin/python3 two_axis_fit_window_sweep_pi.py \
        --flights all_flights_manifest.json --out sweep_results.json [--pilot N]
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent           # .../src/pi_benchmarking
REPO_ROOT = HERE.parents[1]                        # mirror root
DETECTOR_DIR = REPO_ROOT / "src" / "image_processing" / "02_adjacent_frame_differencing"
IMAGE_PROC_DIR = REPO_ROOT / "src" / "image_processing"
STEREO_DIR = REPO_ROOT / "src" / "stereo"
for _p in (str(DETECTOR_DIR), str(IMAGE_PROC_DIR), str(STEREO_DIR), str(REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import detector_core as dc  # noqa: E402
from exclusion_mask import apply_exclusion  # noqa: E402
from pixel_velocity_correction import build_corrected_pairs  # noqa: E402
from label_vs_detection import triangulate  # noqa: E402
from stereo_flight_sync_table import load_timestamps  # noqa: E402
from all_flights_common import load_session_calib, g_fixed_for, find_flight_dir  # noqa: E402
from trajectory_fit import (  # noqa: E402
    build_model_fit_predict, ransac_fit, RANSAC_INLIER_THRESHOLD_MM, RANSAC_MIN_SAMPLES,
    G_MAGNITUDE_MM_S2,
)
from scipy.integrate import solve_ivp  # noqa: E402

CONFIG_PATH = REPO_ROOT / "data" / "detector_tuning" / "candidate_config.json"
POOLED_K_PATH = REPO_ROOT / "data" / "trajectory_fit_comparison" / "all_flights" / "phase1" / "pooled_k.txt"
DURATIONS_CSV = REPO_ROOT / "data" / "trajectory_fit_comparison" / "all_flights" / "duration_distribution" / "flight_durations.csv"
FINAL_POINT_LABELS_CSV = REPO_ROOT / "data" / "final_point_labels" / "final_point_labels.csv"
TMP_DIR = REPO_ROOT / "results" / "tmp_two_axis_detections"

N_ITERATIONS = 3            # decision 68 (adopted)
MIN_SAMPLES_C = RANSAC_MIN_SAMPLES["C"]  # 8
DURATION_MIN_BUFFER_MS = 50.0
W_VALUES_MS = [150.0, 200.0, 250.0, 300.0, 350.0, 400.0, 430.0]


def compute_mask_rect_close(back, fwd, cam_name, diff_threshold, open_kernel, close_kernel):
    """Same mirror as decision 63 / compute_mask_rect_close_variant.py."""
    min_diff = cv2.min(back, fwd)
    _, mask = cv2.threshold(min_diff, diff_threshold, 255, cv2.THRESH_BINARY)
    if open_kernel and open_kernel > 0:
        open_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_kernel, open_kernel))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, open_k)
    if close_kernel and close_kernel > 0:
        close_k = cv2.getStructuringElement(cv2.MORPH_RECT, (close_kernel, close_kernel))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_k)
    return apply_exclusion(mask, cam_name)


def simulate_drag_with_velocity(p0, v0, k, g, t_array):
    """Mirrors trajectory_fit.simulate_drag() EXACTLY (identical deriv,
    identical solve_ivp call/tolerances) except it also returns velocity
    (sol.y[3:]), which the original discards. Verified by reading
    trajectory_fit.py's source first, not assumed -- see worklog."""
    t_array = np.asarray(t_array, dtype=np.float64)
    t0 = 0.0
    tf = float(max(t_array.max(), t0))

    def deriv(t, state):
        pos = state[:3]
        vel = state[3:]
        speed = np.linalg.norm(vel)
        acc = g - k * speed * vel
        return np.concatenate([vel, acc])

    state0 = np.concatenate([p0, v0])
    order = np.argsort(t_array)
    t_sorted = t_array[order]
    sol = solve_ivp(deriv, (t0, tf), state0, t_eval=t_sorted, method="RK45",
                     rtol=1e-8, atol=1e-6)
    if not sol.success:
        raise RuntimeError(f"simulate_drag_with_velocity: integration failed: {sol.message}")
    pos_sorted = sol.y[:3].T
    vel_sorted = sol.y[3:].T
    pos = np.empty_like(pos_sorted)
    vel = np.empty_like(vel_sorted)
    pos[order] = pos_sorted
    vel[order] = vel_sorted
    return pos, vel


def perf_ms():
    return time.perf_counter() * 1000.0


def load_pooled_k():
    return float(POOLED_K_PATH.read_text().strip())


def load_durations():
    out = {}
    with open(DURATIONS_CSV, newline="") as f:
        for row in csv.DictReader(f):
            out[(row["session"], row["flight"])] = float(row["total_duration_ms"])
    return out


def load_final_point_targets():
    out = {}
    with open(FINAL_POINT_LABELS_CSV, newline="") as f:
        for row in csv.DictReader(f):
            if not row["centroid_x"] or not row["centroid_y"]:
                continue
            key = (row["session"], row["flight"])
            out.setdefault(key, {})[row["cam"]] = (
                float(row["centroid_x"]), float(row["centroid_y"]), int(row["frame_number"]))
    return out


def global_cache_warmup(cfg):
    """ONE-TIME cache-priming (exclusion_mask's fillPoly cache per cam_name+
    shape, cv2/TBB thread-pool spin-up) before the per-flight loop starts --
    NOT a per-flight warm-up. Fixed bug: per-flight warm-up left the first
    N_WARMUP_PAIRS frames per camera with NO per-frame timing entry, and
    summing an arbitrary W-window's frames via dict.get(f, 0.0) silently
    contributed 0.0 for any window frame that happened to fall in that
    untimed range -- undercounting detect_sum_ms, worse for small W. Timing
    every frame for real, for every flight, removes that silent-zero risk
    entirely; a handful of one-time cache-priming calls up front is enough
    to avoid cold-start distortion on frame 1 of flight 1."""
    dummy = np.zeros((1088, 1456), dtype=np.uint8)
    for cam_name in ("cam0", "cam1"):
        for _ in range(5):
            mask = compute_mask_rect_close(dummy, dummy, cam_name, cfg["diff_threshold"],
                                            cfg["open_kernel"], cfg["close_kernel"])
            dc.extract_candidates(mask, cfg["min_area"], cfg["max_area"], cfg["min_circ"])


def detect_flight_timed(cam_dir: Path, cam_name: str, cfg: dict):
    """Runs the REAL rect-branch detector over every processable frame,
    timing EVERY frame-pair individually (no per-flight warm-up -- see
    global_cache_warmup). Returns (detections: {frame:(u,v)},
    per_frame_ms: {frame: detect_time_ms})."""
    paths = sorted(cam_dir.glob("frame_*.png"))
    imgs = [cv2.imread(str(p), cv2.IMREAD_GRAYSCALE) for p in paths]  # untimed decode
    stride = cfg["stride"]
    n = len(imgs)
    detections, per_frame_ms = {}, {}
    if n <= 2 * stride:
        return detections, per_frame_ms

    for i in range(stride, n - stride):
        t0 = perf_ms()
        back = cv2.absdiff(imgs[i], imgs[i - stride])
        fwd = cv2.absdiff(imgs[i + stride], imgs[i])
        mask = compute_mask_rect_close(back, fwd, cam_name, cfg["diff_threshold"],
                                        cfg["open_kernel"], cfg["close_kernel"])
        candidates = dc.extract_candidates(mask, cfg["min_area"], cfg["max_area"], cfg["min_circ"])
        t1 = perf_ms()
        frame_num = int(dc.FRAME_STEM_RE.search(paths[i].stem).group(1))
        if candidates:
            best = max(candidates, key=lambda d: d["area"])
            detections[frame_num] = (best["u"], best["v"])
        per_frame_ms[frame_num] = t1 - t0
    return detections, per_frame_ms


def write_detections3_csv(path: Path, detections: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame_number", "u", "v"])
        for fn in sorted(detections):
            u, v = detections[fn]
            w.writerow([fn, u, v])


def target_time_sec(session, flight_id, target_frame0, target_frame1, t_anchor_ns):
    flight_dir = find_flight_dir(session, flight_id)
    ts_csv = flight_dir / "timestamps.csv"
    cam0_entries, cam1_entries = load_timestamps(ts_csv)
    ts0, ts1 = dict(cam0_entries), dict(cam1_entries)
    if target_frame0 not in ts0 or target_frame1 not in ts1:
        return None
    avg_ns = (ts0[target_frame0] + ts1[target_frame1]) / 2.0
    return (avg_ns - t_anchor_ns) / 1e9


def process_flight(session, flight_id, cfg, pooled_k, durations, targets):
    result = {"session": session, "flight": flight_id, "w_rows": []}
    flight_dir = REPO_ROOT / "data" / session / "ball_flights" / flight_id
    cam0_dir = flight_dir / "cam0" / "ball_in_frame"
    cam1_dir = flight_dir / "cam1" / "ball_in_frame"
    ts_csv = flight_dir / "timestamps.csv"

    tgt = targets.get((session, flight_id))
    if tgt is None or "cam0" not in tgt or "cam1" not in tgt:
        result["status"] = "skipped"
        result["reason"] = "missing final-point label"
        return result

    # -- detect once, both cams, SERIAL, real Pi timing per frame-pair (no
    # per-flight warm-up -- see global_cache_warmup, called once in main()) --
    det0, t0_ms = detect_flight_timed(cam0_dir, "cam0", cfg)
    det1, t1_ms = detect_flight_timed(cam1_dir, "cam1", cfg)

    c0_csv = TMP_DIR / f"{session}_{flight_id}_cam0.csv"
    c1_csv = TMP_DIR / f"{session}_{flight_id}_cam1.csv"
    write_detections3_csv(c0_csv, det0)
    write_detections3_csv(c1_csv, det1)

    pairs = build_corrected_pairs(c0_csv, c1_csv, ts_csv,
                                   max_speed_px_per_frame=cfg["max_speed_px_per_frame"],
                                   min_run_length=cfg["min_run_length"])
    if len(pairs) < MIN_SAMPLES_C:
        result["status"] = "skipped"
        result["reason"] = f"only {len(pairs)} corrected pairs (< min_samples={MIN_SAMPLES_C})"
        return result
    pairs = sorted(pairs, key=lambda p: (p["t0_ns"] + p["t1_ns"]) / 2.0)

    K0, D0, K1, D1, P0, P1 = load_session_calib(session)
    uv0 = np.array([(p["u0_corr"], p["v0_corr"]) for p in pairs])
    uv1 = np.array([(p["u1_corr"], p["v1_corr"]) for p in pairs])
    xyz_full = triangulate(uv0, uv1, K0, D0, K1, D1, P0, P1)
    t_avg_ns = np.array([(p["t0_ns"] + p["t1_ns"]) / 2.0 for p in pairs])
    t_anchor_ns = float(t_avg_ns[0])
    t_full = (t_avg_ns - t_anchor_ns) / 1e9
    frames0_full = [p["cam0_frame"] for p in pairs]
    frames1_full = [p["cam1_frame"] for p in pairs]

    u0, v0, f0 = tgt["cam0"]
    u1, v1, f1 = tgt["cam1"]
    target_xyz = triangulate(np.array([[u0, v0]]), np.array([[u1, v1]]), K0, D0, K1, D1, P0, P1)[0]
    t_target = target_time_sec(session, flight_id, f0, f1, t_anchor_ns)
    if t_target is None:
        result["status"] = "skipped"
        result["reason"] = "target frame not found in timestamps.csv"
        return result

    keep_idx = [i for i, fr in enumerate(frames0_full) if fr != f0]
    if len(keep_idx) < MIN_SAMPLES_C:
        result["status"] = "skipped"
        result["reason"] = f"only {len(keep_idx)} points after excluding target frame"
        return result
    frames0 = [frames0_full[i] for i in keep_idx]
    frames1 = [frames1_full[i] for i in keep_idx]
    t_all = t_full[np.array(keep_idx)]
    xyz_all = xyz_full[np.array(keep_idx)]

    if t_target <= t_all[0]:
        result["status"] = "skipped"
        result["reason"] = "target time before track start"
        return result

    g_fixed = g_fixed_for(session, flight_id)
    fit_fn, predict_fn = build_model_fit_predict("C", g_fixed, k_fixed=pooled_k)

    # -- velocity method (a): full-trajectory fit, self-consistency check --
    try:
        params_full = fit_fn(t_all, xyz_all)
        pos_a, vel_a = simulate_drag_with_velocity(params_full[0], params_full[1], pooled_k,
                                                     g_fixed, np.array([t_target]))
        vel_method_a = vel_a[0]
    except RuntimeError as e:
        result["status"] = "skipped"
        result["reason"] = f"full-trajectory fit failed: {e}"
        return result

    # -- velocity method (b): finite difference, 2 nearest detected points to target --
    order_by_dist = np.argsort(np.abs(t_all - t_target))
    idx2 = sorted(order_by_dist[:2])
    t_b0, t_b1 = t_all[idx2[0]], t_all[idx2[1]]
    p_b0, p_b1 = xyz_all[idx2[0]], xyz_all[idx2[1]]
    if abs(t_b1 - t_b0) < 1e-6:
        vel_method_b = None
    else:
        vel_method_b = (p_b1 - p_b0) / (t_b1 - t_b0)

    result["status"] = "ok"
    result["n_full_points"] = len(t_all)
    result["vel_method_a"] = vel_method_a.tolist()
    result["vel_method_b"] = vel_method_b.tolist() if vel_method_b is not None else None
    result["fd_frames_used"] = [frames0[idx2[0]], frames0[idx2[1]]]
    result["fd_dt_ms"] = float((t_b1 - t_b0) * 1000.0)

    duration_ms = durations.get((session, flight_id))

    for W in W_VALUES_MS:
        row = {"W_ms": W}
        if duration_ms is None or duration_ms < W + DURATION_MIN_BUFFER_MS:
            row["status"] = "skipped"
            row["reason"] = f"total_duration_ms={duration_ms} < W+{DURATION_MIN_BUFFER_MS:.0f}ms buffer"
            result["w_rows"].append(row)
            continue

        w_s = W / 1000.0
        n_w = int(np.searchsorted(t_all, w_s, side="right"))
        if n_w < MIN_SAMPLES_C:
            row["status"] = "skipped"
            row["reason"] = f"only {n_w} points within W={W:.0f}ms (< min_samples={MIN_SAMPLES_C})"
            result["w_rows"].append(row)
            continue

        t_win = t_all[:n_w]
        xyz_win = xyz_all[:n_w]
        frames0_win = frames0[:n_w]
        frames1_win = frames1[:n_w]

        lead_time_ms = (t_target - t_win[-1]) * 1000.0
        if lead_time_ms <= 0:
            row["status"] = "skipped"
            row["reason"] = "window already reached/passed target time"
            result["w_rows"].append(row)
            continue

        # real measured per-frame-pair detect time, summed over the window's frames
        detect_sum_ms = sum(t0_ms.get(f, 0.0) for f in frames0_win) + \
                         sum(t1_ms.get(f, 0.0) for f in frames1_win)

        t0 = perf_ms()
        uv0_win = np.array([(det0[f][0], det0[f][1]) for f in frames0_win])
        uv1_win = np.array([(det1[f][0], det1[f][1]) for f in frames1_win])
        _xyz_retriangulated = triangulate(uv0_win, uv1_win, K0, D0, K1, D1, P0, P1)
        triangulate_ms = perf_ms() - t0

        t0 = perf_ms()
        try:
            res = ransac_fit(t_win, xyz_win, fit_fn, predict_fn, min_samples=MIN_SAMPLES_C,
                              inlier_threshold_mm=RANSAC_INLIER_THRESHOLD_MM,
                              n_iterations=N_ITERATIONS, random_seed=42, frame_numbers=frames0_win)
            ransac_ms = perf_ms() - t0
            p0_fit, v0_fit = res["params"]
            pos_pred, vel_pred = simulate_drag_with_velocity(p0_fit, v0_fit, pooled_k, g_fixed,
                                                                np.array([t_target]))
            pos_pred, vel_pred = pos_pred[0], vel_pred[0]
            position_error_mm = float(np.linalg.norm(pos_pred - target_xyz))
            vel_err_a_mm_s = float(np.linalg.norm(vel_pred - vel_method_a))
            vel_err_b_mm_s = float(np.linalg.norm(vel_pred - vel_method_b)) if vel_method_b is not None else None

            row.update(status="ok", n_points=n_w, detect_sum_ms=detect_sum_ms,
                       triangulate_ms=triangulate_ms, ransac_ms=ransac_ms,
                       total_compute_ms=detect_sum_ms + triangulate_ms + ransac_ms,
                       w_plus_compute_ms=W + detect_sum_ms + triangulate_ms + ransac_ms,
                       position_error_mm=position_error_mm,
                       velocity_error_a_mm_s=vel_err_a_mm_s,
                       velocity_error_b_mm_s=vel_err_b_mm_s,
                       lead_time_ms=lead_time_ms)
        except RuntimeError as e:
            row["status"] = "fit_failed"
            row["reason"] = str(e)
        result["w_rows"].append(row)

    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--flights", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pilot", type=int, default=0)
    args = ap.parse_args()

    cfg = json.loads(CONFIG_PATH.read_text())
    pooled_k = load_pooled_k()
    durations = load_durations()
    targets = load_final_point_targets()
    flight_list = json.loads(Path(args.flights).read_text())
    if args.pilot:
        flight_list = flight_list[:args.pilot]
        print(f"PILOT MODE: {len(flight_list)} flights")

    print(f"W values: {W_VALUES_MS}")
    print(f"n_iterations={N_ITERATIONS}, inlier_threshold={RANSAC_INLIER_THRESHOLD_MM}mm, "
          f"pooled_k={pooled_k:.6e}")

    global_cache_warmup(cfg)
    print("Global cache warm-up done (one-time, not per-flight).")

    results = []
    t0 = time.time()
    for i, (session, flight) in enumerate(flight_list, 1):
        r = process_flight(session, flight, cfg, pooled_k, durations, targets)
        results.append(r)
        if i % 10 == 0 or i == len(flight_list):
            elapsed = time.time() - t0
            print(f"  {i}/{len(flight_list)} flights done ({elapsed:.1f}s elapsed, "
                  f"{elapsed/i:.2f}s/flight)", flush=True)

    out = {"config": cfg, "pooled_k": pooled_k, "n_iterations": N_ITERATIONS,
           "inlier_threshold_mm": RANSAC_INLIER_THRESHOLD_MM, "W_values_ms": W_VALUES_MS,
           "duration_min_buffer_ms": DURATION_MIN_BUFFER_MS, "flights": results}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
