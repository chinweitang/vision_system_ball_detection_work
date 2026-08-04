#!/usr/bin/env python3
"""benchmark_detection_rect_total_pi.py -- RUNS ON THE PI.

Directly measures the rect-branch's full per-frame-pair detection cost
(diff -> threshold -> morph-open(ellipse) -> morph-close(RECT) -> exclusion
-> contours+moments) as ONE continuous timed block, end-to-end -- not
assembled from separately-measured phases. This replaces the ~9.78ms
estimate used in the throughput check (that number combined Stage 1's
ellipse-branch diff/contours timing with decision 63's rect-branch mask-only
timing from two different measurement runs).

Same 8-flight sample, same warm-up convention, cam0 only (matching decision
63's convention -- Stage 1 already showed cam0/cam1 detection timing agree
to ~1ms) as the existing Pi benchmark scripts.

Timing-only mirror of detector_core's per-frame call sequence with the
close kernel swapped to cv2.MORPH_RECT (open kernel stays MORPH_ELLIPSE,
matching every other rect-branch script this session) -- does NOT modify
detector_core.py. apply_exclusion is imported and called for real.

Usage (on the Pi, inside the venv):
    ~/benchmark/venv/bin/python3 benchmark_detection_rect_total_pi.py \
        --flights flights_manifest.json --out rect_total_results.json
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
DETECTOR_DIR = REPO_ROOT / "src" / "image_processing" / "02_adjacent_frame_differencing"
IMAGE_PROC_DIR = REPO_ROOT / "src" / "image_processing"
for _p in (str(DETECTOR_DIR), str(IMAGE_PROC_DIR), str(REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import detector_core as dc  # noqa: E402
from exclusion_mask import apply_exclusion  # noqa: E402

CONFIG_PATH = REPO_ROOT / "data" / "detector_tuning" / "candidate_config.json"
N_WARMUP_PAIRS = 5


def compute_mask_rect_close(back, fwd, cam_name, diff_threshold, open_kernel, close_kernel):
    """Identical to detector_core.compute_mask except the CLOSE kernel is
    cv2.MORPH_RECT (open kernel, threshold, exclusion unchanged) -- same
    mirror already used and validated in decision 63 / compute_mask_rect_close_variant.py."""
    min_diff = cv2.min(back, fwd)
    _, mask = cv2.threshold(min_diff, diff_threshold, 255, cv2.THRESH_BINARY)
    if open_kernel and open_kernel > 0:
        open_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_kernel, open_kernel))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, open_k)
    if close_kernel and close_kernel > 0:
        close_k = cv2.getStructuringElement(cv2.MORPH_RECT, (close_kernel, close_kernel))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_k)
    return apply_exclusion(mask, cam_name)


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
    return {"n": n, "median": pct(0.5), "p95": pct(0.95), "mean": statistics.fmean(s),
            "max": s[-1], "min": s[0]}


def run_flight(flight_dir: Path, cam_name: str, cfg: dict, timed_totals: list, warmup_pairs: int):
    cam_dir = flight_dir / cam_name / "ball_in_frame"
    paths = sorted(cam_dir.glob("frame_*.png"))
    imgs = [cv2.imread(str(p), cv2.IMREAD_GRAYSCALE) for p in paths]
    stride = cfg["stride"]
    n = len(imgs)
    if n <= 2 * stride:
        return

    def one_pair(i, timed):
        t0 = perf_ms()
        back = cv2.absdiff(imgs[i], imgs[i - stride])
        fwd = cv2.absdiff(imgs[i + stride], imgs[i])
        mask = compute_mask_rect_close(back, fwd, cam_name, cfg["diff_threshold"],
                                        cfg["open_kernel"], cfg["close_kernel"])
        _candidates = dc.extract_candidates(mask, cfg["min_area"], cfg["max_area"], cfg["min_circ"])
        t1 = perf_ms()
        if timed:
            timed_totals.append(t1 - t0)

    idx_range = list(range(stride, n - stride))
    for i in idx_range[:warmup_pairs]:
        one_pair(i, timed=False)
    for i in idx_range[warmup_pairs:]:
        one_pair(i, timed=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--flights", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    flight_list = json.loads(Path(args.flights).read_text())
    cfg = json.loads(CONFIG_PATH.read_text())

    totals = []
    for session, flight in flight_list:
        print(f"=== {session}/{flight} ===", flush=True)
        flight_dir = REPO_ROOT / "data" / session / "ball_flights" / flight
        run_flight(flight_dir, "cam0", cfg, totals, N_WARMUP_PAIRS)

    stats = phase_stats(totals)
    print()
    print(f"rect-branch TOTAL (diff+mask_rect+contours), end-to-end, single timed block:")
    print(f"  n={stats['n']}  median={stats['median']:.3f}ms  p95={stats['p95']:.3f}ms  "
          f"mean={stats['mean']:.3f}ms  max={stats['max']:.3f}ms  min={stats['min']:.3f}ms")

    ESTIMATE_MS = 9.78
    delta = stats["median"] - ESTIMATE_MS
    print(f"\nPrevious combined estimate: {ESTIMATE_MS}ms")
    print(f"Direct measurement (median): {stats['median']:.3f}ms")
    print(f"Delta: {delta:+.3f}ms ({delta/ESTIMATE_MS*100:+.1f}%)")

    out = {"config": cfg, "n_warmup_pairs": N_WARMUP_PAIRS, "cam": "cam0",
           "flights": flight_list, "stats": stats,
           "previous_estimate_ms": ESTIMATE_MS, "delta_ms": delta}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
