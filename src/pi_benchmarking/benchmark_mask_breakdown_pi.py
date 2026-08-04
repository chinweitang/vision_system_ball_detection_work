#!/usr/bin/env python3
"""benchmark_mask_breakdown_pi.py -- RUNS ON THE PI.

Diagnostic: subdivides compute_mask's ~86-87ms/frame cost (Stage 1 finding,
src/pi_benchmarking/benchmark_pipeline_pi.py) into its 4 named substeps
(threshold, morph-open, morph-close, exclusion), across the same 8-flight
sample used in Stage 1/2. For morph-close specifically, ALSO times a
rectangular kernel of the same size (30x30) alongside the production
elliptical one -- a branch computation, timed and then discarded, that does
NOT replace or feed into the production detection path. Tests whether a
rectangular kernel (which OpenCV can optimize with a running min/max
algorithm independent of kernel size) drops close-kernel cost toward the
open-kernel (3x3) baseline -- confirming the bottleneck is kernel SHAPE
(non-rectangular morphology doesn't get that optimization) -- or whether it
stays expensive regardless of shape, meaning the bottleneck is something
else (most likely just kernel SIZE, 30x30 vs 3x3, ~78x more pixels in the
footprint either way).

Timing-only mirror of compute_mask's exact cv2 call sequence (threshold ->
morph-open -> morph-close -> exclusion) -- does NOT modify detector_core.py
(production, already-tuned code) or the downstream detection/candidate
extraction path. apply_exclusion is imported and called directly from the
real exclusion_mask.py (not duplicated -- it's a real, separately
importable function).

cam0 only: Stage 1 already showed cam0/cam1 detection-phase timing agree to
within ~1ms of each other -- this is a question about image size/kernel
shape, not camera identity, so cam1 wouldn't add information here.

Usage (on the Pi, inside the venv):
    ~/benchmark/venv/bin/python3 benchmark_mask_breakdown_pi.py \
        --flights flights_manifest.json --out mask_breakdown_results.json
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent           # .../src/pi_benchmarking
REPO_ROOT = HERE.parents[1]                        # mirror root
DETECTOR_DIR = REPO_ROOT / "src" / "image_processing" / "02_adjacent_frame_differencing"
IMAGE_PROC_DIR = REPO_ROOT / "src" / "image_processing"
for _p in (str(DETECTOR_DIR), str(IMAGE_PROC_DIR), str(REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import detector_core as dc  # noqa: E402  (only used for FRAME_STEM_RE-style glob; kept for parity)
from exclusion_mask import apply_exclusion  # noqa: E402

CONFIG_PATH = REPO_ROOT / "data" / "detector_tuning" / "candidate_config.json"
N_WARMUP_PAIRS = 5   # untimed warm-up pairs per flight, matches Stage 1 -- lets
                      # cv2/TBB thread pools and exclusion_mask's fillPoly cache
                      # spin up before any number counts


def perf_ms():
    return time.perf_counter() * 1000.0


def phase_stats(values_ms):
    if not values_ms:
        return {"n": 0}
    s = sorted(values_ms)
    n = len(s)
    def pct(p):
        idx = min(n - 1, max(0, int(round(p * (n - 1)))))
        return s[idx]
    return {
        "n": n, "median": pct(0.5), "p95": pct(0.95),
        "mean": statistics.fmean(s), "max": s[-1], "min": s[0],
    }


def run_flight(flight_dir: Path, cam_name: str, cfg: dict, timers: dict, warmup_pairs: int):
    cam_dir = flight_dir / cam_name / "ball_in_frame"
    paths = sorted(cam_dir.glob("frame_*.png"))
    imgs = [cv2.imread(str(p), cv2.IMREAD_GRAYSCALE) for p in paths]
    stride = cfg["stride"]
    n = len(imgs)
    if n <= 2 * stride:
        return

    open_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (cfg["open_kernel"], cfg["open_kernel"]))
    close_k_ellipse = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (cfg["close_kernel"], cfg["close_kernel"]))
    close_k_rect = cv2.getStructuringElement(cv2.MORPH_RECT, (cfg["close_kernel"], cfg["close_kernel"]))

    def one_pair(i, timed):
        back = cv2.absdiff(imgs[i], imgs[i - stride])
        fwd = cv2.absdiff(imgs[i + stride], imgs[i])
        min_diff = cv2.min(back, fwd)

        # threshold (includes the preceding cv2.min -- not separately requested,
        # bundled here rather than added as an unrequested 5th category)
        t0 = perf_ms()
        _, mask = cv2.threshold(min_diff, cfg["diff_threshold"], 255, cv2.THRESH_BINARY)
        t1 = perf_ms()
        if timed:
            timers["threshold"].append(t1 - t0)

        # morph-open, 3x3 elliptical (production)
        t0 = perf_ms()
        mask_open = cv2.morphologyEx(mask, cv2.MORPH_OPEN, open_k)
        t1 = perf_ms()
        if timed:
            timers["morph_open"].append(t1 - t0)

        # morph-close, 30x30 elliptical (PRODUCTION path -- feeds exclusion below)
        t0 = perf_ms()
        mask_close_ellipse = cv2.morphologyEx(mask_open, cv2.MORPH_CLOSE, close_k_ellipse)
        t1 = perf_ms()
        if timed:
            timers["morph_close_ellipse"].append(t1 - t0)

        # morph-close, 30x30 RECTANGULAR (branch experiment, same input,
        # result discarded -- does not feed exclusion/detection)
        t0 = perf_ms()
        _mask_close_rect = cv2.morphologyEx(mask_open, cv2.MORPH_CLOSE, close_k_rect)
        t1 = perf_ms()
        if timed:
            timers["morph_close_rect"].append(t1 - t0)

        # exclusion (production path continues on the elliptical-close result)
        t0 = perf_ms()
        _final_mask = apply_exclusion(mask_close_ellipse, cam_name)
        t1 = perf_ms()
        if timed:
            timers["exclusion"].append(t1 - t0)

    idx_range = list(range(stride, n - stride))
    warm = idx_range[:warmup_pairs]
    real = idx_range[warmup_pairs:]
    for i in warm:
        one_pair(i, timed=False)
    for i in real:
        one_pair(i, timed=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--flights", required=True, help="JSON manifest: [[session, flight_id], ...]")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    flight_list = json.loads(Path(args.flights).read_text())
    cfg = json.loads(CONFIG_PATH.read_text())

    timers = {"threshold": [], "morph_open": [], "morph_close_ellipse": [],
              "morph_close_rect": [], "exclusion": []}

    for session, flight in flight_list:
        print(f"=== {session}/{flight} ===", flush=True)
        flight_dir = REPO_ROOT / "data" / session / "ball_flights" / flight
        run_flight(flight_dir, "cam0", cfg, timers, N_WARMUP_PAIRS)

    summary = {name: phase_stats(vals) for name, vals in timers.items()}

    print()
    for name, s in summary.items():
        if s["n"] == 0:
            continue
        print(f"{name:22s} n={s['n']:4d}  median={s['median']:7.3f}ms  p95={s['p95']:7.3f}ms  "
              f"mean={s['mean']:7.3f}ms  max={s['max']:7.3f}ms")

    ellipse_med = summary["morph_close_ellipse"]["median"]
    rect_med = summary["morph_close_rect"]["median"]
    open_med = summary["morph_open"]["median"]
    print()
    print(f"morph_open (3x3, baseline):        median={open_med:.3f}ms")
    print(f"morph_close ellipse (30x30, prod):  median={ellipse_med:.3f}ms")
    print(f"morph_close rect (30x30, branch):   median={rect_med:.3f}ms")
    print(f"rect / open ratio:    {rect_med / open_med:.2f}x")
    print(f"rect / ellipse ratio: {rect_med / ellipse_med:.2f}x")

    out = {
        "config": cfg,
        "n_warmup_pairs": N_WARMUP_PAIRS,
        "cam": "cam0",
        "flights": flight_list,
        "summary": summary,
        "ratios": {
            "rect_over_open": rect_med / open_med,
            "rect_over_ellipse": rect_med / ellipse_med,
            "ellipse_over_open": ellipse_med / open_med,
        },
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
