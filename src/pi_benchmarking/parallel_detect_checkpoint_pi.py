#!/usr/bin/env python3
"""parallel_detect_checkpoint_pi.py -- RUNS ON THE PI. Step 1 CHECKPOINT.

Measures, on real Pi hardware, whether cam0+cam1 detection run CONCURRENTLY
(Python threading) is actually faster than SERIAL -- the pass/fail hinge for
the whole prediction-pipeline-sweep latency model (concurrent-with-capture
vs batched-after-window). Does NOT assume TBB-parallel cv2 threads compose
cleanly with our own Python-level threading -- measures it directly.

For every frame-pair index, on the SAME frames (fair same-run comparison,
not reusing an older serial number from a different run/date):
  - SERIAL: detect cam0 then cam1 sequentially, wall-clock the pair.
  - THREADED: threading.Thread per camera launched together, .join()ed,
    wall-clock the PAIR (not the sum of each thread's own reported time --
    concurrent execution means the pair's real timeline contribution is
    max(cam0_time, cam1_time) + thread/join overhead; only wall-clock
    around the join captures that correctly).

If threaded speedup < 1.7x: also tries a multiprocessing.Pool fallback
(one process per camera, frame arrays passed via the pool -- cheap, ~1.5MB
grayscale arrays) and reports which approach wins.

Uses the SAME rect-kernel mask mirror as two_axis_fit_window_sweep_pi.py
(decision 63) -- does NOT modify detector_core.py.

Usage (on the Pi, inside the venv):
    ~/benchmark/venv/bin/python3 parallel_detect_checkpoint_pi.py \
        --flights flights_manifest.json --out checkpoint_results.json
"""
import argparse
import json
import statistics
import sys
import threading
import time
from multiprocessing import Pool
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
DETECTOR_DIR = REPO_ROOT / "src" / "image_processing" / "02_adjacent_frame_differencing"
IMAGE_PROC_DIR = REPO_ROOT / "src" / "image_processing"
for _p in (str(DETECTOR_DIR), str(IMAGE_PROC_DIR), str(REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import detector_core as dc  # noqa: E402
from exclusion_mask import apply_exclusion  # noqa: E402

CONFIG_PATH = REPO_ROOT / "results" / "detector_tuning" / "candidate_config.json"
CADENCE_MS = 1000.0 / 60.0  # 16.666...ms
SPEEDUP_FALLBACK_THRESHOLD = 1.7


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


def perf_ms():
    return time.perf_counter() * 1000.0


def detect_one(back, fwd, cam_name, cfg):
    """One camera's detection work for one frame-pair (diff+mask+contours)."""
    mask = compute_mask_rect_close(back, fwd, cam_name, cfg["diff_threshold"],
                                    cfg["open_kernel"], cfg["close_kernel"])
    return dc.extract_candidates(mask, cfg["min_area"], cfg["max_area"], cfg["min_circ"])


def _mp_worker(args):
    """Top-level (picklable) worker for the multiprocessing fallback."""
    back, fwd, cam_name, cfg = args
    return detect_one(back, fwd, cam_name, cfg)


def global_cache_warmup(cfg):
    """One-time cache-priming before ANY timed measurement -- established
    fix (two_axis_fit_window_sweep_pi.py) for the per-flight-warmup
    undercount bug. Warms both the serial and threaded code paths."""
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
    return {"n": n, "median": pct(0.5), "p95": pct(0.95), "mean": statistics.fmean(s),
            "max": s[-1], "min": s[0]}


def measure_flight(flight_dir, cfg, pool):
    """Returns (serial_pair_ms: list, threaded_pair_ms: list, mp_pair_ms: list-or-None)."""
    cam0_dir = flight_dir / "cam0" / "ball_in_frame"
    cam1_dir = flight_dir / "cam1" / "ball_in_frame"
    paths0 = sorted(cam0_dir.glob("frame_*.png"))
    paths1 = sorted(cam1_dir.glob("frame_*.png"))
    imgs0 = [cv2.imread(str(p), cv2.IMREAD_GRAYSCALE) for p in paths0]  # untimed decode
    imgs1 = [cv2.imread(str(p), cv2.IMREAD_GRAYSCALE) for p in paths1]
    stride = cfg["stride"]
    n = min(len(imgs0), len(imgs1))
    if n <= 2 * stride:
        return [], [], []

    idx_range = range(stride, n - stride)
    serial_ms, threaded_ms, mp_ms = [], [], []

    for i in idx_range:
        back0 = cv2.absdiff(imgs0[i], imgs0[i - stride])
        fwd0 = cv2.absdiff(imgs0[i + stride], imgs0[i])
        back1 = cv2.absdiff(imgs1[i], imgs1[i - stride])
        fwd1 = cv2.absdiff(imgs1[i + stride], imgs1[i])

        # -- SERIAL --
        t0 = perf_ms()
        detect_one(back0, fwd0, "cam0", cfg)
        detect_one(back1, fwd1, "cam1", cfg)
        serial_ms.append(perf_ms() - t0)

        # -- THREADED (wall-clock the pair, not the sum of per-thread times) --
        results = {}
        def _run(cam_name, back, fwd):
            results[cam_name] = detect_one(back, fwd, cam_name, cfg)
        t0 = perf_ms()
        th0 = threading.Thread(target=_run, args=("cam0", back0, fwd0))
        th1 = threading.Thread(target=_run, args=("cam1", back1, fwd1))
        th0.start(); th1.start()
        th0.join(); th1.join()
        threaded_ms.append(perf_ms() - t0)

        # -- MULTIPROCESSING (only if pool provided -- fallback path) --
        if pool is not None:
            t0 = perf_ms()
            pool.map(_mp_worker, [(back0, fwd0, "cam0", cfg), (back1, fwd1, "cam1", cfg)])
            mp_ms.append(perf_ms() - t0)

    return serial_ms, threaded_ms, mp_ms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--flights", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    cfg = json.loads(CONFIG_PATH.read_text())
    flight_list = json.loads(Path(args.flights).read_text())

    print("Global cache warm-up (one-time)...", flush=True)
    global_cache_warmup(cfg)

    all_serial, all_threaded = [], []
    for session, flight in flight_list:
        flight_dir = REPO_ROOT / "data" / session / "ball_flights" / flight
        print(f"=== {session}/{flight} ===", flush=True)
        s_ms, t_ms, _ = measure_flight(flight_dir, cfg, pool=None)
        all_serial.extend(s_ms)
        all_threaded.extend(t_ms)

    serial_stats = phase_stats(all_serial)
    threaded_stats = phase_stats(all_threaded)
    speedup = serial_stats["median"] / threaded_stats["median"] if threaded_stats.get("median") else float("nan")

    print()
    print(f"SERIAL   per-pair: n={serial_stats['n']} median={serial_stats['median']:.3f}ms "
          f"p95={serial_stats['p95']:.3f}ms mean={serial_stats['mean']:.3f}ms")
    print(f"THREADED per-pair: n={threaded_stats['n']} median={threaded_stats['median']:.3f}ms "
          f"p95={threaded_stats['p95']:.3f}ms mean={threaded_stats['mean']:.3f}ms")
    print(f"Speedup (serial/threaded, median): {speedup:.2f}x")

    mp_stats = None
    winner = "threaded"
    if speedup < SPEEDUP_FALLBACK_THRESHOLD:
        print(f"\nSpeedup {speedup:.2f}x < {SPEEDUP_FALLBACK_THRESHOLD}x threshold -- "
              f"trying multiprocessing fallback...", flush=True)
        all_mp = []
        with Pool(processes=2) as pool:
            for session, flight in flight_list:
                flight_dir = REPO_ROOT / "data" / session / "ball_flights" / flight
                _, _, mp_ms = measure_flight(flight_dir, cfg, pool=pool)
                all_mp.extend(mp_ms)
        mp_stats = phase_stats(all_mp)
        mp_speedup = serial_stats["median"] / mp_stats["median"] if mp_stats.get("median") else float("nan")
        print(f"MULTIPROCESS per-pair: n={mp_stats['n']} median={mp_stats['median']:.3f}ms "
              f"p95={mp_stats['p95']:.3f}ms mean={mp_stats['mean']:.3f}ms")
        print(f"Speedup (serial/multiprocess, median): {mp_speedup:.2f}x")
        if mp_stats["median"] < threaded_stats["median"]:
            winner = "multiprocess"
            print("WINNER: multiprocessing beats threading.")
        else:
            winner = "threaded"
            print("WINNER: threading still beats multiprocessing (despite being under the 1.7x bar).")

    winner_stats = threaded_stats if winner == "threaded" else mp_stats
    below_cadence = winner_stats["median"] <= CADENCE_MS
    print()
    print(f"*** HEADLINE: per-pair PARALLEL ({winner}) detect = {winner_stats['median']:.3f}ms "
          f"-- {'BELOW' if below_cadence else 'ABOVE'} {CADENCE_MS:.3f}ms (60fps cadence) ***")

    out = {
        "config": cfg, "flights": flight_list, "cadence_ms": CADENCE_MS,
        "serial": serial_stats, "threaded": threaded_stats,
        "speedup_threaded": speedup,
        "multiprocess": mp_stats,
        "winner": winner,
        "winner_median_ms": winner_stats["median"],
        "below_cadence": below_cadence,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
