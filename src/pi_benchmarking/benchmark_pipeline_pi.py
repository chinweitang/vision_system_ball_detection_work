#!/usr/bin/env python3
"""benchmark_pipeline_pi.py -- RUNS ON THE PI.

End-to-end real-time feasibility benchmark: detect(cam0) -> detect(cam1) ->
pair+correct -> triangulate -> predict, timed phase-by-phase, on real
pre-captured ball_in_frame frames fed in as if arriving live. See
claude/prompts/2026-08-03_1154_pi_realtime_benchmark.md and this session's
worklog (claude/claude_logs/2026-08-03_pi_realtime_benchmark_worklog.md) for
the full design rationale.

Deliberately reuses the real, unmodified production modules rather than
reimplementing any of them -- detector_core.py (detection), all_flights_common
+ label_vs_detection (calibration + triangulation), pixel_velocity_correction
(sub-frame-corrected pairing), trajectory_fit (Model C fit + RANSAC). This
script is the only new logic: it wires them together in real pipeline order
and times each phase. Expects to run inside a repo tree mirrored at the same
relative paths as the real repo (src/, calibration_outputs/, data/) -- see
run_pi_benchmark.ps1, which builds that mirror via scp.

Usage (on the Pi, inside the venv):
    ~/benchmark/venv/bin/python3 benchmark_pipeline_pi.py \
        --flights flights_manifest.json --out results.json
"""
import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent           # .../src/pi_benchmarking
REPO_ROOT = HERE.parents[1]                        # mirror root
DETECTOR_DIR = REPO_ROOT / "src" / "image_processing" / "02_adjacent_frame_differencing"
STEREO_DIR = REPO_ROOT / "src" / "stereo"
for _p in (str(DETECTOR_DIR), str(STEREO_DIR), str(REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import detector_core as dc  # noqa: E402
from pixel_velocity_correction import build_corrected_pairs  # noqa: E402
from label_vs_detection import triangulate as lvd_triangulate  # noqa: E402
from all_flights_common import g_fixed_for, load_session_calib  # noqa: E402
from trajectory_fit import (  # noqa: E402
    build_model_fit_predict, ransac_fit,
    RANSAC_INLIER_THRESHOLD_MM, RANSAC_MIN_SAMPLES, RANSAC_N_ITERATIONS, RANSAC_SEED,
)

CONFIG_PATH = REPO_ROOT / "results" / "detector_tuning" / "candidate_config.json"
POOLED_K_PATH = REPO_ROOT / "results" / "trajectory_fit_comparison" / "all_flights" / "phase1" / "pooled_k.txt"
TMP_DETECTIONS_DIR = REPO_ROOT / "results" / "tmp_detections"

N_WARMUP_PAIRS = 5          # untimed warm-up pairs per camera, before timing starts
ROLLING_REFIT_POINTS = 10   # ~evenly spaced refit checkpoints per flight, not every single new point
                             # (an every-point rolling refit could be 80+ nonlinear fits per flight --
                             #  too slow for a first exploratory run; this still shows the cost-vs-N trend)


def perf_ms():
    return time.perf_counter() * 1000.0


def load_frames(cam_dir: Path):
    """Sorted (frame_number, image) pairs for every frame_*.png in cam_dir."""
    paths = sorted(cam_dir.glob("frame_*.png"))
    out = []
    for p in paths:
        num = int(dc.FRAME_STEM_RE.search(p.stem).group(1))
        img = __import__("cv2").imread(str(p), __import__("cv2").IMREAD_GRAYSCALE)
        out.append((num, img))
    return out


def run_detection_timed(frames, cam_name, cfg, warmup_pairs):
    """Runs the real 3-frame min-diff detector (detector_core.compute_mask +
    extract_candidates, unmodified) over `frames`, timing diff/mask/contours
    separately per pair. First `warmup_pairs` pairs are run untimed first (lets
    cv2/TBB thread pools and exclusion_mask's fillPoly cache spin up before
    any number counts). Returns (detections: {frame_num: (u, v)}, phase_times_ms:
    {"diff": [...], "mask": [...], "contours": [...], "total": [...]})."""
    import cv2
    stride = cfg["stride"]
    n = len(frames)
    detections = {}
    phase_times = {"diff": [], "mask": [], "contours": [], "total": []}
    if n <= 2 * stride:
        return detections, phase_times

    imgs = [im for _, im in frames]
    nums = [fn for fn, _ in frames]

    def one_pair(i, timed):
        t0 = perf_ms()
        back = cv2.absdiff(imgs[i], imgs[i - stride])
        fwd = cv2.absdiff(imgs[i + stride], imgs[i])
        t1 = perf_ms()
        mask = dc.compute_mask(back, fwd, cam_name, cfg["diff_threshold"],
                                cfg["open_kernel"], cfg["close_kernel"])
        t2 = perf_ms()
        candidates = dc.extract_candidates(mask, cfg["min_area"], cfg["max_area"], cfg["min_circ"])
        t3 = perf_ms()
        if timed:
            phase_times["diff"].append(t1 - t0)
            phase_times["mask"].append(t2 - t1)
            phase_times["contours"].append(t3 - t2)
            phase_times["total"].append(t3 - t0)
        if candidates:
            best = max(candidates, key=lambda d: d["area"])
            detections[nums[i]] = (best["u"], best["v"])

    idx_range = list(range(stride, n - stride))
    warm = idx_range[:warmup_pairs]
    real = idx_range[warmup_pairs:]
    for i in warm:
        one_pair(i, timed=False)
    for i in real:
        one_pair(i, timed=True)

    return detections, phase_times


def write_detections3_csv(path: Path, detections: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame_number", "u", "v"])
        for fn in sorted(detections):
            u, v = detections[fn]
            w.writerow([fn, u, v])


def phase_stats(values_ms):
    if not values_ms:
        return {"n": 0}
    s = sorted(values_ms)
    n = len(s)
    def pct(p):
        idx = min(n - 1, max(0, int(round(p * (n - 1)))))
        return s[idx]
    return {
        "n": n, "mean": statistics.fmean(s), "median": pct(0.5),
        "p95": pct(0.95), "p99": pct(0.99), "max": s[-1], "min": s[0],
    }


def benchmark_flight(session, flight_id, flight_dir: Path, cfg, pooled_k, K0, D0, K1, D1, P0, P1):
    result = {"session": session, "flight": flight_id}

    cam0_dir = flight_dir / "cam0" / "ball_in_frame"
    cam1_dir = flight_dir / "cam1" / "ball_in_frame"
    ts_csv = flight_dir / "timestamps.csv"

    t_load0 = perf_ms()
    frames0 = load_frames(cam0_dir)
    frames1 = load_frames(cam1_dir)
    result["load_ms"] = perf_ms() - t_load0
    result["n_frames_cam0"] = len(frames0)
    result["n_frames_cam1"] = len(frames1)

    det0, phases0 = run_detection_timed(frames0, "cam0", cfg, N_WARMUP_PAIRS)
    det1, phases1 = run_detection_timed(frames1, "cam1", cfg, N_WARMUP_PAIRS)
    result["detect_cam0"] = {k: phase_stats(v) for k, v in phases0.items()}
    result["detect_cam1"] = {k: phase_stats(v) for k, v in phases1.items()}
    result["n_det_cam0"] = len(det0)
    result["n_det_cam1"] = len(det1)

    # also stash raw per-frame output for Stage 2's correctness diff
    result["raw_detections_cam0"] = {str(k): v for k, v in det0.items()}
    result["raw_detections_cam1"] = {str(k): v for k, v in det1.items()}

    cam0_csv = TMP_DETECTIONS_DIR / f"{session}_{flight_id}_cam0_detections3.csv"
    cam1_csv = TMP_DETECTIONS_DIR / f"{session}_{flight_id}_cam1_detections3.csv"
    write_detections3_csv(cam0_csv, det0)
    write_detections3_csv(cam1_csv, det1)

    t0 = perf_ms()
    pairs = build_corrected_pairs(cam0_csv, cam1_csv, ts_csv,
                                   max_speed_px_per_frame=cfg["max_speed_px_per_frame"],
                                   min_run_length=cfg["min_run_length"])
    result["pair_correct_ms"] = perf_ms() - t0
    result["n_pairs"] = len(pairs)

    if len(pairs) < RANSAC_MIN_SAMPLES["C"]:
        result["skipped_reason"] = f"only {len(pairs)} pairs, need >= {RANSAC_MIN_SAMPLES['C']} for Model C RANSAC"
        return result

    pairs = sorted(pairs, key=lambda p: (p["t0_ns"] + p["t1_ns"]) / 2.0)
    uv0 = np.array([(p["u0_corr"], p["v0_corr"]) for p in pairs])
    uv1 = np.array([(p["u1_corr"], p["v1_corr"]) for p in pairs])
    frame_nums = [p["cam0_frame"] for p in pairs]

    t0 = perf_ms()
    xyz = lvd_triangulate(uv0, uv1, K0, D0, K1, D1, P0, P1)
    result["triangulate_ms"] = perf_ms() - t0

    t_avg_ns = np.array([(p["t0_ns"] + p["t1_ns"]) / 2.0 for p in pairs])
    t_sec = (t_avg_ns - t_avg_ns[0]) / 1e9

    g_fixed = g_fixed_for(session, flight_id)
    fit_fn, predict_fn = build_model_fit_predict("C", g_fixed, k_fixed=pooled_k)

    N = len(pairs)

    # single-shot bare fit at full available N
    t0 = perf_ms()
    try:
        fit_fn(t_sec, xyz)
        single_shot_ok = True
    except Exception as e:
        single_shot_ok = False
        result["single_shot_fit_error"] = str(e)
    result["single_shot_fit_ms"] = perf_ms() - t0
    result["single_shot_fit_ok"] = single_shot_ok
    result["single_shot_fit_n"] = N

    # single-shot RANSAC-wrapped fit at full available N
    t0 = perf_ms()
    try:
        ransac_fit(t_sec, xyz, fit_fn, predict_fn,
                   min_samples=RANSAC_MIN_SAMPLES["C"],
                   inlier_threshold_mm=RANSAC_INLIER_THRESHOLD_MM,
                   n_iterations=RANSAC_N_ITERATIONS["C"],
                   random_seed=RANSAC_SEED, frame_numbers=frame_nums)
        ransac_ok = True
    except Exception as e:
        ransac_ok = False
        result["ransac_fit_error"] = str(e)
    result["ransac_fit_ms"] = perf_ms() - t0
    result["ransac_fit_ok"] = ransac_ok
    result["ransac_fit_n_iterations"] = RANSAC_N_ITERATIONS["C"]

    # rolling refit: ~ROLLING_REFIT_POINTS evenly-spaced checkpoints from
    # min_samples up to N, refit-from-scratch each time on the real
    # accumulated stream so far (not every single new point -- see
    # ROLLING_REFIT_POINTS comment above)
    min_k = RANSAC_MIN_SAMPLES["C"]
    if N > min_k:
        ks = sorted(set(np.linspace(min_k, N, num=min(ROLLING_REFIT_POINTS, N - min_k + 1), dtype=int).tolist()))
    else:
        ks = [N]
    rolling = []
    for k in ks:
        t0 = perf_ms()
        try:
            fit_fn(t_sec[:k], xyz[:k])
            ok = True
        except Exception:
            ok = False
        rolling.append({"k": k, "ms": perf_ms() - t0, "ok": ok})
    result["rolling_refit"] = rolling

    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--flights", required=True, help="JSON manifest: [[session, flight_id], ...]")
    ap.add_argument("--out", required=True, help="output results JSON path")
    args = ap.parse_args()

    with open(args.flights) as f:
        flight_list = json.load(f)

    cfg = json.loads(CONFIG_PATH.read_text())
    pooled_k = float(POOLED_K_PATH.read_text().strip())

    import cv2
    machine_info = {
        "cv2_version": cv2.__version__,
        "numpy_version": np.__version__,
        "python_version": sys.version,
    }

    results = []
    for session, flight_id in flight_list:
        flight_dir = REPO_ROOT / "data" / session / "ball_flights" / flight_id
        print(f"=== {session}/{flight_id} ===", flush=True)
        K0, D0, K1, D1, P0, P1 = load_session_calib(session)
        t0 = perf_ms()
        r = benchmark_flight(session, flight_id, flight_dir, cfg, pooled_k, K0, D0, K1, D1, P0, P1)
        r["wall_clock_ms"] = perf_ms() - t0
        print(f"    done in {r['wall_clock_ms']:.0f}ms wall clock", flush=True)
        results.append(r)

    out = {
        "machine_info": machine_info,
        "config": cfg,
        "pooled_k": pooled_k,
        "n_warmup_pairs": N_WARMUP_PAIRS,
        "flights": results,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
