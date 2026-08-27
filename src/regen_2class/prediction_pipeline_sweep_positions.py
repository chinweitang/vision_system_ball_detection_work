#!/usr/bin/env python3
"""prediction_pipeline_sweep_pi.py -- RUNS ON THE PI. Step 2 (full sweep).

Sweeps prediction-cutoff time t (per flight, t=0 = first usable fit frame,
SAME clock as results/prediction/04_launch_to_crossing_budget/) and measures,
on real Pi hardware, the crossing-state prediction (position/velocity/
HIT-MISS) an early-cutoff Model-C fit would produce, against the FULL-ARC
fit already computed and frozen in 01_crossing_plane_setup/
crossing_classification.csv. Accuracy here is therefore a CONVERGENCE
result (early-cutoff vs full-fit reference), NOT ground-truth accuracy --
manual crossing-bracket labels are not ready yet. Every accuracy number in
this script's output is labelled as such.

TWO-CLOCK / CONCURRENT-WITH-CAPTURE MODEL (corrects the two-axis sweep's
batched-after-window assumption from earlier tonight): frames arrive every
16.666ms regardless of detect speed; Step 1's checkpoint measured real
THREADED (concurrent cam0+cam1) per-pair detect at 13.578ms median, BELOW
16.667ms -- so the pipeline is capture-bound (detection is hidden under the
capture cadence, no backlog), and per-flight latency(t) is modelled as:
    latency(t) = t_pair_ms(last pair in [0,t]) + triangulate_ms + ransac_ms
                 + predict_ms + ONE_FRAME_LAG_MS (16.667ms, 3-frame-diff lag)
using REAL measured Pi compute for every term, not assumed constants. Any
individual pair exceeding 16.667ms is flagged (diagnostic), not folded into
a backlog term, per the capture-bound regime confirmed at the checkpoint.

Reused, FROZEN, unmodified: crossing_plane_classification.{build_geometry,
TAPE_REGISTRATIONS, REG_KEY_FOR, APERTURE_SIZE_MM}, all_flights_common.
{load_session_calib, registration_for}, pixel_velocity_correction.
build_corrected_pairs, label_vs_detection.triangulate, trajectory_fit.
{build_model_fit_predict, ransac_fit, RANSAC_INLIER_THRESHOLD_MM,
RANSAC_MIN_SAMPLES}. detector_core.py / trajectory_fit.py NOT modified.

Reference/ground-truth (NOT recomputed on the Pi): crossing_Y/crossing_Z/
crossing_vel_xyz/cls pulled directly from crossing_classification.csv
(01_, already computed); t_cross_ms pulled from launch_to_crossing.csv
(04_, already computed, same clock). Velocity in BOTH the reference and the
early-cutoff prediction uses the SAME finite-difference approximation
classify_flight() itself uses (dt=1e-3s forward difference on predict_fn),
verified by reading crossing_plane_classification.py's source -- NOT the
true ODE velocity state -- so the two are genuinely comparable, not an
apples-to-oranges mismatch.

Early-cutoff crossing search is a NECESSARY GENERALIZATION of
classify_flight()'s bisection: classify_flight() only ever interpolates
within [0, t[-1]] because the FULL track already spans the crossing; an
early-cutoff fit's own last observed point is typically BEFORE the
crossing, so its own predicted crossing time must be found by EXTRAPOLATING
past t[-1] (bracket-expansion up to a generous horizon cap, then the same
brentq depth-root-search) -- same core numerical approach and frozen
geometry, not a re-implementation from scratch.

Usage (on the Pi, inside the venv):
    ~/benchmark/venv/bin/python3 prediction_pipeline_sweep_pi.py \
        --out sweep_results.json [--pilot N]
"""
import argparse
import csv
import json
import sys
import threading
import time
from ast import literal_eval
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import brentq

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
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
from all_flights_common import load_session_calib, registration_for  # noqa: E402
from trajectory_fit import (  # noqa: E402
    build_model_fit_predict, ransac_fit, RANSAC_INLIER_THRESHOLD_MM, RANSAC_MIN_SAMPLES,
)
from crossing_plane_classification import (  # noqa: E402
    build_geometry, TAPE_REGISTRATIONS, REG_KEY_FOR, APERTURE_SIZE_MM,
)

CONFIG_PATH = REPO_ROOT / "results" / "detector_tuning" / "candidate_config.json"
POOLED_K_PATH = REPO_ROOT / "results" / "trajectory_fit_comparison" / "all_flights" / "phase1" / "pooled_k.txt"
CROSSING_CSV = REPO_ROOT / "results" / "prediction" / "01_crossing_plane_setup" / "crossing_classification.csv"
LAUNCH_TO_CROSSING_CSV = REPO_ROOT / "results" / "prediction" / "04_launch_to_crossing_budget" / "launch_to_crossing.csv"

N_ITERATIONS = 3            # decisions 68/70 (adopted) -- realistic production-relevant cost
MIN_SAMPLES_C = RANSAC_MIN_SAMPLES["C"]  # 8
CADENCE_MS = 1000.0 / 60.0  # 16.666...ms
ONE_FRAME_LAG_MS = CADENCE_MS  # 3-frame-differencing lag: detector is always 1 frame behind
HORIZON_CAP_S = 2.5         # generous extrapolation cap (max reference t_cross=1.559s + buffer)
T_VALUES_MS = sorted(set(list(range(150, 1251, 50)) + [490]))  # guarantees the 490ms headline exists
G_FIXED_MAG = 9810.0


def elevation_bin(elevation_deg: float) -> str:
    """Same cuts as budget_by_elevation_bin.py / 02_candidate_reselection."""
    if elevation_deg < 15.0:
        return "FLAT"
    elif elevation_deg < 45.0:
        return "MID"
    return "LOB"


def compute_mask_rect_close(back, fwd, cam_name, diff_threshold, open_kernel, close_kernel):
    """Same mirror as decision 63 / two_axis_fit_window_sweep_pi.py."""
    min_diff = cv2.min(back, fwd)
    _, mask = cv2.threshold(min_diff, diff_threshold, 255, cv2.THRESH_BINARY)
    if open_kernel and open_kernel > 0:
        open_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_kernel, open_kernel))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, open_k)
    if close_kernel and close_kernel > 0:
        close_k = cv2.getStructuringElement(cv2.MORPH_RECT, (close_kernel, close_kernel))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_k)
    return apply_exclusion(mask, cam_name)


def detect_one(back, fwd, cam_name, cfg):
    mask = compute_mask_rect_close(back, fwd, cam_name, cfg["diff_threshold"],
                                    cfg["open_kernel"], cfg["close_kernel"])
    return dc.extract_candidates(mask, cfg["min_area"], cfg["max_area"], cfg["min_circ"])


def perf_ms():
    return time.perf_counter() * 1000.0


def global_cache_warmup(cfg):
    """One-time cache-priming -- established fix (two_axis_fit_window_sweep_pi.py)
    for the per-flight-warmup undercount bug; ALL frames timed for real."""
    dummy = np.zeros((1088, 1456), dtype=np.uint8)
    for cam_name in ("cam0", "cam1"):
        for _ in range(5):
            detect_one(dummy, dummy, cam_name, cfg)


def phase_stats(values_ms):
    if not values_ms:
        return {"n": 0}
    s = sorted(values_ms)
    n = len(s)
    def pct(p):
        idx = min(n - 1, max(0, int(round(p * (n - 1)))))
        return s[idx]
    return {"n": n, "median": pct(0.5), "p95": pct(0.95), "p99": pct(0.99),
            "mean": float(np.mean(s)), "max": s[-1], "min": s[0]}


def detect_flight_threaded(cam0_dir: Path, cam1_dir: Path, cfg: dict):
    """Detects cam0+cam1 CONCURRENTLY per frame-pair index (winning approach
    from Step 1's checkpoint: threading beat serial 1.27x and multiprocess
    lost outright). Frame index i in each camera's OWN sorted list is
    treated as "the same real-time capture step" -- a modelling
    simplification (both cameras nominally capture at the same 60fps; only
    rare independent drops could misalign this), stated explicitly, same
    simplification the Step-1 checkpoint already used.

    Returns (det0: {frame:(u,v)}, det1: {frame:(u,v)}, t_pair_ms: {frame0: ms}).
    t_pair_ms is keyed by CAM0's frame number (matches build_corrected_pairs'
    "cam0_frame" key on its output pairs, mirroring two_axis's t0_ms.get(f)
    lookup pattern, consolidated to one wall-clock number per pair since
    detection is now concurrent, not two separate serial numbers)."""
    paths0 = sorted(cam0_dir.glob("frame_*.png"))
    paths1 = sorted(cam1_dir.glob("frame_*.png"))
    imgs0 = [cv2.imread(str(p), cv2.IMREAD_GRAYSCALE) for p in paths0]  # untimed decode
    imgs1 = [cv2.imread(str(p), cv2.IMREAD_GRAYSCALE) for p in paths1]
    stride = cfg["stride"]
    n = min(len(imgs0), len(imgs1))
    det0, det1, t_pair_ms = {}, {}, {}
    if n <= 2 * stride:
        return det0, det1, t_pair_ms

    for i in range(stride, n - stride):
        back0 = cv2.absdiff(imgs0[i], imgs0[i - stride])
        fwd0 = cv2.absdiff(imgs0[i + stride], imgs0[i])
        back1 = cv2.absdiff(imgs1[i], imgs1[i - stride])
        fwd1 = cv2.absdiff(imgs1[i + stride], imgs1[i])

        results = {}
        def _run(cam_name, back, fwd):
            results[cam_name] = detect_one(back, fwd, cam_name, cfg)
        t0 = perf_ms()
        th0 = threading.Thread(target=_run, args=("cam0", back0, fwd0))
        th1 = threading.Thread(target=_run, args=("cam1", back1, fwd1))
        th0.start(); th1.start()
        th0.join(); th1.join()
        pair_ms = perf_ms() - t0

        frame_num0 = int(dc.FRAME_STEM_RE.search(paths0[i].stem).group(1))
        frame_num1 = int(dc.FRAME_STEM_RE.search(paths1[i].stem).group(1))
        cands0, cands1 = results["cam0"], results["cam1"]
        if cands0:
            best0 = max(cands0, key=lambda d: d["area"])
            det0[frame_num0] = (best0["u"], best0["v"])
        if cands1:
            best1 = max(cands1, key=lambda d: d["area"])
            det1[frame_num1] = (best1["u"], best1["v"])
        t_pair_ms[frame_num0] = pair_ms

    return det0, det1, t_pair_ms


def write_detections3_csv(path: Path, detections: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame_number", "u", "v"])
        for fn in sorted(detections):
            u, v = detections[fn]
            w.writerow([fn, u, v])


def load_pooled_k():
    return float(POOLED_K_PATH.read_text().strip())


def load_reference():
    """Joins crossing_classification.csv (01_, has crossing_Y/Z/vel/cls) with
    launch_to_crossing.csv (04_, has t_cross_ms, same clock) on
    (session,flight_id). Returns {(session,flight_id): {...}}. NOT
    recomputed -- both are already-frozen, already-validated outputs from
    earlier today (04_'s worklog verified 107/107 reproduced exactly
    against 01_'s frozen classify_flight())."""
    ref = {}
    with open(LAUNCH_TO_CROSSING_CSV, newline="") as f:
        for row in csv.DictReader(f):
            key = (row["session"], row["flight_id"])
            ref[key] = {
                "registration": row["registration"], "cls": row["cls"],
                "elevation_deg": float(row["elevation_deg"]), "speed_m_s": float(row["speed_m_s"]),
                "t_cross_ms": float(row["t_cross_ms"]),
            }
    with open(CROSSING_CSV, newline="") as f:
        for row in csv.DictReader(f):
            key = (row["session"], row["flight_id"])
            if key not in ref:
                continue
            ref[key]["crossing_Y"] = float(row["crossing_Y"])
            ref[key]["crossing_Z"] = float(row["crossing_Z"])
            ref[key]["crossing_vel_xyz"] = np.array(literal_eval(row["crossing_vel_xyz"]), dtype=np.float64)
    missing = [k for k, v in ref.items() if "crossing_Y" not in v]
    if missing:
        raise SystemExit(f"{len(missing)} flights in launch_to_crossing.csv missing from "
                          f"crossing_classification.csv join -- data inconsistency, stopping: {missing[:5]}")
    return ref


def find_own_crossing(params, predict_fn, X_world, plane_depth, t_last_observed_s):
    """Generalizes classify_flight()'s bisection (interpolation-only, valid
    there since the FULL track spans the crossing) to EXTRAPOLATION: an
    early-cutoff fit's own last observed point is typically before the
    crossing, so its own predicted crossing time must be searched for past
    t_last_observed_s via bracket expansion up to HORIZON_CAP_S. Returns
    t_cross_own (float) or None if the model never reaches the plane within
    the horizon (a real, possible outcome for poorly-constrained early
    fits -- handled as a real result, not an error)."""
    p0_fit = params[0]

    def depth_at(tt):
        if tt <= 0.0:
            return float(np.dot(p0_fit, X_world)) - plane_depth
        pos = predict_fn(params, np.array([tt]))[0]
        return float(np.dot(pos, X_world)) - plane_depth

    f0 = depth_at(0.0)
    hi = max(t_last_observed_s, 0.05)
    f_hi = depth_at(hi)
    step = hi
    while np.sign(f_hi) == np.sign(f0) and f_hi != 0.0 and hi < HORIZON_CAP_S:
        hi = min(hi + step, HORIZON_CAP_S)
        f_hi = depth_at(hi)
        step *= 1.5

    if np.sign(f_hi) == np.sign(f0) and f_hi != 0.0:
        return None  # never reaches plane within horizon
    if f0 == 0.0:
        return 0.0
    return brentq(depth_at, 1e-6, hi, xtol=1e-6)


def eval_pos_vel(params, predict_fn, t_cross):
    """SAME finite-difference velocity approach classify_flight() itself
    uses (verified by reading the source: dt=1e-3s forward difference on
    predict_fn, NOT the true ODE velocity state) -- required so the
    early-cutoff prediction and the reference (computed this same way in
    01_) are genuinely comparable, not an apples-to-oranges mismatch."""
    def eval_pos(tt):
        if tt <= 0.0:
            return params[0]
        return predict_fn(params, np.array([tt]))[0]
    pos = eval_pos(t_cross)
    dt = 1e-3
    pos2 = eval_pos(t_cross + dt)
    vel = (pos2 - pos) / dt
    return pos, vel


def process_flight(session, flight_id, cfg, pooled_k, ref_row, geometries):
    result = {"session": session, "flight": flight_id, "t_rows": []}
    flight_dir = REPO_ROOT / "data" / session / "ball_flights" / flight_id
    cam0_dir = flight_dir / "cam0" / "ball_in_frame"
    cam1_dir = flight_dir / "cam1" / "ball_in_frame"
    ts_csv = flight_dir / "timestamps.csv"

    reg = registration_for(session, flight_id)
    reg_key = REG_KEY_FOR[(session, reg)]
    geo = geometries[reg_key]
    X_world, plane_depth = geo["X_world"], geo["plane_depth"]

    # -- detect once, both cams CONCURRENT (threaded), real Pi wall-clock per pair --
    det0, det1, t_pair_ms = detect_flight_threaded(cam0_dir, cam1_dir, cfg)
    over_cadence = [f for f, ms in t_pair_ms.items() if ms > CADENCE_MS]

    c0_csv = REPO_ROOT / "results" / "tmp_pipeline_sweep_detections" / f"{session}_{flight_id}_cam0.csv"
    c1_csv = REPO_ROOT / "results" / "tmp_pipeline_sweep_detections" / f"{session}_{flight_id}_cam1.csv"
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
    t_avg_ns = np.array([(p["t0_ns"] + p["t1_ns"]) / 2.0 for p in pairs])  # REAL timestamps, no uniform-spacing assumption
    t_anchor_ns = float(t_avg_ns[0])
    t_full = (t_avg_ns - t_anchor_ns) / 1e9
    frames0_full = [p["cam0_frame"] for p in pairs]

    g_fixed = G_FIXED_MAG * (-geo["up"] / np.linalg.norm(geo["up"]))
    fit_fn, predict_fn = build_model_fit_predict("C", g_fixed, k_fixed=pooled_k)

    t_cross_ref_s = ref_row["t_cross_ms"] / 1000.0
    result["status"] = "ok"
    result["n_full_points"] = len(t_full)
    result["over_cadence_pair_count"] = len(over_cadence)
    result["over_cadence_pairs"] = over_cadence[:20]  # cap list length in output

    for T in T_VALUES_MS:
        row = {"T_ms": T}
        airborne = t_cross_ref_s * 1000.0 > T
        row["airborne"] = airborne

        w_s = T / 1000.0
        n_w = int(np.searchsorted(t_full, w_s, side="right"))
        row["n_detected"] = n_w
        row["n_ideal_cadence"] = T / CADENCE_MS

        if n_w < MIN_SAMPLES_C:
            row["status"] = "not_fit_eligible"
            row["reason"] = f"only {n_w} points (< min_samples={MIN_SAMPLES_C})"
            result["t_rows"].append(row)
            continue

        t_win = t_full[:n_w]
        xyz_win = xyz_full[:n_w]
        frames0_win = frames0_full[:n_w]

        t0 = perf_ms()
        _xyz_retri = triangulate(uv0[:n_w], uv1[:n_w], K0, D0, K1, D1, P0, P1)
        triangulate_ms = perf_ms() - t0

        t0 = perf_ms()
        try:
            res = ransac_fit(t_win, xyz_win, fit_fn, predict_fn, min_samples=MIN_SAMPLES_C,
                              inlier_threshold_mm=RANSAC_INLIER_THRESHOLD_MM,
                              n_iterations=N_ITERATIONS, random_seed=42, frame_numbers=frames0_win)
        except RuntimeError as e:
            row["status"] = "fit_failed"
            row["reason"] = str(e)
            result["t_rows"].append(row)
            continue
        ransac_ms = perf_ms() - t0
        params = res["params"]

        t0 = perf_ms()
        t_cross_own = find_own_crossing(params, predict_fn, X_world, plane_depth, t_win[-1])
        if t_cross_own is None:
            predict_ms = perf_ms() - t0
            row["status"] = "no_crossing_found"
            row["reason"] = f"model does not reach plane within {HORIZON_CAP_S}s horizon"
            row["triangulate_ms"] = triangulate_ms
            row["ransac_ms"] = ransac_ms
            row["predict_ms"] = predict_ms
            result["t_rows"].append(row)
            continue
        pos_own, vel_own = eval_pos_vel(params, predict_fn, t_cross_own)
        predict_ms = perf_ms() - t0

        p_far, u, up = geo["p_far"], geo["u"], geo["up"]
        cy_own = float(np.dot(pos_own - p_far, u))
        cz_own = float(np.dot(pos_own - p_far, up))
        inside = (0.0 <= cy_own <= APERTURE_SIZE_MM) and (0.0 <= cz_own <= APERTURE_SIZE_MM)
        cls_own = "HIT" if inside else "MISS_HIGH_WIDE"

        position_error_mm = float(np.hypot(cy_own - ref_row["crossing_Y"], cz_own - ref_row["crossing_Z"]))
        velocity_error_mm_s = float(np.linalg.norm(vel_own - ref_row["crossing_vel_xyz"]))
        hit_miss_match = (cls_own == ref_row["cls"])

        # -- latency(t), capture-bound (Step 1 checkpoint: 13.578ms median < 16.667ms cadence) --
        last_pair_detect_ms = t_pair_ms.get(frames0_win[-1], float("nan"))
        latency_ms = last_pair_detect_ms + triangulate_ms + ransac_ms + predict_ms + ONE_FRAME_LAG_MS

        row.update(
            status="ok", t_cross_own_ms=t_cross_own * 1000.0,
            last_pair_detect_ms=last_pair_detect_ms,
            triangulate_ms=triangulate_ms, ransac_ms=ransac_ms, predict_ms=predict_ms,
            latency_ms=latency_ms, latency_feasible=bool(latency_ms <= 490.0),
            position_error_mm=position_error_mm, velocity_error_mm_s=velocity_error_mm_s,
            cls_own=cls_own, hit_miss_match=hit_miss_match,
            # ---- THE ONLY COMPUTATIONAL CHANGE FROM THE Pi SCRIPT ----------
            # cy_own/cz_own are already computed above (lines 406-407) and were
            # discarded here; they are now persisted. cy_ref/cz_ref are the
            # reference in the SAME plane basis: crossing_classification.csv
            # stores them already projected through the same frozen
            # build_geometry() that produced p_far/u/up above, and the file
            # holds no 3D reference point that could be re-projected instead.
            # These are the exact two values position_error_mm is measured
            # against on line 411, so the pairing cannot drift.
            cy_own=cy_own, cz_own=cz_own,
            cy_ref=float(ref_row["crossing_Y"]), cz_ref=float(ref_row["crossing_Z"]),
        )
        result["t_rows"].append(row)

    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--csv", default=None,
                    help="also emit a positions CSV (timing columns omitted)")
    ap.add_argument("--pilot", type=int, default=0)
    args = ap.parse_args()

    cfg = json.loads(CONFIG_PATH.read_text())
    pooled_k = load_pooled_k()
    reference = load_reference()
    flight_list = sorted(reference.keys())
    if args.pilot:
        flight_list = flight_list[:args.pilot]
        print(f"PILOT MODE: {len(flight_list)} flights")

    print(f"T values (ms): {T_VALUES_MS}")
    print(f"n_iterations={N_ITERATIONS}, inlier_threshold={RANSAC_INLIER_THRESHOLD_MM}mm, "
          f"pooled_k={pooled_k:.6e}, {len(reference)} reference crossers loaded")

    geometries = {}
    for reg_key, tcfg in TAPE_REGISTRATIONS.items():
        geometries[reg_key] = build_geometry(reg_key, tcfg)
    print("Geometry built for all 3 registrations (frozen build_geometry()).")

    global_cache_warmup(cfg)
    print("Global cache warm-up done (one-time, not per-flight).", flush=True)

    results = []
    drift_samples = []  # (elapsed_s_since_start, flight_median_pair_ms) -- thermal-drift diagnostic
    t_start = time.time()
    for i, (session, flight) in enumerate(flight_list, 1):
        r = process_flight(session, flight, cfg, pooled_k, reference[(session, flight)], geometries)
        results.append(r)
        if r.get("status") == "ok":
            pair_times = [row.get("last_pair_detect_ms") for row in r["t_rows"] if row.get("status") == "ok"]
            elapsed = time.time() - t_start
            drift_samples.append((elapsed, r.get("over_cadence_pair_count", 0), r.get("n_full_points")))
        if i % 10 == 0 or i == len(flight_list):
            elapsed = time.time() - t_start
            print(f"  {i}/{len(flight_list)} flights done ({elapsed:.1f}s elapsed, "
                  f"{elapsed/i:.2f}s/flight)", flush=True)

    out = {"config": cfg, "pooled_k": pooled_k, "n_iterations": N_ITERATIONS,
           "inlier_threshold_mm": RANSAC_INLIER_THRESHOLD_MM, "T_values_ms": T_VALUES_MS,
           "cadence_ms": CADENCE_MS, "one_frame_lag_ms": ONE_FRAME_LAG_MS,
           "horizon_cap_s": HORIZON_CAP_S, "drift_samples": drift_samples, "flights": results}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {args.out}")

    # ---- CSV emit (added; the Pi script writes only JSON) -----------------
    # The Pi script's CSV is produced separately by pipeline_sweep_aggregate.py.
    # This copy emits its own CSV so the run is self-contained.
    #
    # TIMING COLUMNS ARE DELIBERATELY OMITTED. This is a LAPTOP run; every
    # timing it measures is void. Writing them out would leave void numbers
    # sitting in a file that looks like the Pi sweep. The columns kept are
    # positions, errors and classification only.
    if args.csv:
        csv_path = Path(args.csv)
        if csv_path.exists():
            raise SystemExit(f"refusing to overwrite existing file: {csv_path}")
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        cols = ["session", "flight", "T_ms", "status", "airborne", "n_detected",
                "cy_own", "cz_own", "cy_ref", "cz_ref",
                "position_error_mm", "velocity_error_mm_s",
                "cls_own", "hit_miss_match", "t_cross_own_ms"]
        n = 0
        with open(csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for fl in results:
                for row in fl.get("t_rows", []):
                    rec = {"session": fl["session"], "flight": fl["flight"]}
                    for c in cols[2:]:
                        rec[c] = row.get(c)
                    w.writerow(rec)
                    n += 1
        print(f"Wrote {csv_path}  ({n} rows)")


if __name__ == "__main__":
    main()
