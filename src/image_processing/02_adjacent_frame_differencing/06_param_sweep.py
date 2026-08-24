# 06_param_sweep.py
#
# Grid search over the 3-frame min-diff detector's mask-generation
# parameters (STRIDE, DIFF_THRESHOLD, OPEN_KERNEL), scored against a
# 10-flight sample spanning both sessions and the full existing
# detection-rate range (see conversation / detection_rate_summary.csv).
#
# Primary metric: average combined_rate (co-detection in both cams, same
# frame) across the 10 sample flights - NOT total-detections/processable,
# since triangulation needs both cams to see the ball in the same frame.
# Chosen over pure recall-on-the-one-labeled-flight because that flight was
# already hand-tuned to ~96% and clearly hasn't generalised (session-wide
# average sits far lower) - optimizing against it alone would re-overfit.
#
# Secondary/regression-check metric: recall against the ONE labeled flight
# (2026_07_15_gym/.../flight_01, hand-clicked ground truth in labels_uv.csv)
# - shown alongside, not optimized for, so we can confirm centroid accuracy
# isn't quietly regressing while chasing broader detection rate.
#
# min_area/max_area/min_circ are held at their current defaults for this
# sweep (per the agreed order: mask-generation params first, candidate
# filters after) - CLOSE_KERNEL also held fixed.
#
# Does NOT touch any real flight data or analysis_3 folders - reads only
# from ball_in_frame/*.png, writes only to results/detector_tuning/.
#
# Run from anywhere:
#   python path/to/code/06_param_sweep.py

from pathlib import Path
import sys
import csv
import itertools
from concurrent.futures import ProcessPoolExecutor, as_completed

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO_ROOT))

import detector_core as dc  # noqa: E402

SESSION_15 = REPO_ROOT / "data" / "2026_07_15_gym" / "ball_flights"
SESSION_21 = REPO_ROOT / "data" / "2026_07_21_gym" / "ball_flights"

OUT_DIR = REPO_ROOT / "results" / "detector_tuning"

CAMS = ["cam0", "cam1"]

# (ball_flights_dir, flight_subpath) - subpath handles the nested session
# folder for the one labeled flight.
FLIGHT_SAMPLE = [
    (SESSION_15, "2 ball contacts ground before plane/flight_01"),  # labeled
    (SESSION_15, "flight_22"),
    (SESSION_15, "flight_55"),
    (SESSION_21, "flight_126"),
    (SESSION_21, "flight_47"),
    (SESSION_21, "flight_59"),
    (SESSION_21, "flight_53"),
    (SESSION_21, "flight_60"),
    (SESSION_21, "flight_33"),
    (SESSION_21, "flight_84"),
]

LABELED_FLIGHT_IDX = 0  # index into FLIGHT_SAMPLE of the one with ground truth
LABEL_TOLERANCE_PX_FALLBACK = 20.0  # used if a frame's diameter_px is missing

# -- Fixed (not swept this round) ---------------------------------------
CLOSE_KERNEL = 30
MIN_AREA = 200
MAX_AREA = 50000
MIN_CIRC = 0.3

# -- Grid ------------------------------------------------------------------
STRIDES = [1, 2, 3]
DIFF_THRESHOLDS = [8, 12, 16, 20]
OPEN_KERNELS = [0, 3, 5, 7]


def load_labels():
    """Returns {(cam_name, frame_number): (u, v, tolerance_px)} for the one
    labeled flight."""
    flight_dir = FLIGHT_SAMPLE[LABELED_FLIGHT_IDX][0] / FLIGHT_SAMPLE[LABELED_FLIGHT_IDX][1]

    diam = {}  # (cam_name, frame_number) -> diameter_px
    for cam_idx, cam_name in enumerate(CAMS):
        p = flight_dir / f"flight_01_{cam_name}_labels.csv"
        if not p.is_file():
            continue
        with open(p, newline="") as f:
            for row in csv.DictReader(f):
                fn = int(row["frame_number"])
                d = row.get("diameter_px", "")
                if d:
                    diam[(cam_name, fn)] = float(d)

    labels = {}
    with open(flight_dir / "labels_uv.csv", newline="") as f:
        for row in csv.DictReader(f):
            fn = int(row["frame_index"])
            cam_name = CAMS[int(row["cam"])]
            u, v = float(row["u"]), float(row["v"])
            tol = diam.get((cam_name, fn), LABEL_TOLERANCE_PX_FALLBACK * 2) / 2.0
            labels[(cam_name, fn)] = (u, v, tol)
    return labels


LABELS = load_labels()


def evaluate_config(config):
    stride, diff_threshold, open_kernel = config

    per_flight_combined = []
    label_hits = 0
    label_total = 0

    for ball_flights_dir, flight_subpath in FLIGHT_SAMPLE:
        flight_dir = ball_flights_dir / flight_subpath
        proc = {}
        det = {}
        for cam in CAMS:
            cam_dir = flight_dir / cam / "ball_in_frame"
            proc[cam] = dc.processable_frame_numbers(cam_dir, stride)
            det[cam] = dc.run_detection(
                cam_dir, cam, stride, diff_threshold, open_kernel, CLOSE_KERNEL,
                MIN_AREA, MAX_AREA, MIN_CIRC,
            )

        co_processable = proc["cam0"] & proc["cam1"]
        co_detected = set(det["cam0"].keys()) & set(det["cam1"].keys())
        if co_processable:
            per_flight_combined.append(len(co_detected) / len(co_processable))

        if flight_subpath == FLIGHT_SAMPLE[LABELED_FLIGHT_IDX][1]:
            for cam in CAMS:
                for fn, (true_u, true_v, tol) in LABELS.items():
                    cam_name, frame_num = fn
                    if cam_name != cam:
                        continue
                    label_total += 1
                    hit = frame_num in det[cam]
                    if hit:
                        pu, pv = det[cam][frame_num]
                        if ((pu - true_u) ** 2 + (pv - true_v) ** 2) ** 0.5 <= tol:
                            label_hits += 1

    avg_combined_rate = sum(per_flight_combined) / len(per_flight_combined) if per_flight_combined else 0.0
    labeled_recall = (label_hits / label_total) if label_total else None

    return {
        "stride": stride,
        "diff_threshold": diff_threshold,
        "open_kernel": open_kernel,
        "avg_combined_rate": avg_combined_rate,
        "labeled_recall": labeled_recall,
    }


def main():
    configs = list(itertools.product(STRIDES, DIFF_THRESHOLDS, OPEN_KERNELS))
    print(f"Sweeping {len(configs)} configs over {len(FLIGHT_SAMPLE)} flights...")

    results = []
    with ProcessPoolExecutor() as ex:
        futures = {ex.submit(evaluate_config, c): c for c in configs}
        done = 0
        for fut in as_completed(futures):
            results.append(fut.result())
            done += 1
            if done % 8 == 0 or done == len(configs):
                print(f"  {done}/{len(configs)} configs done")

    results.sort(key=lambda r: r["avg_combined_rate"], reverse=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "sweep_results.csv"
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["stride", "diff_threshold", "open_kernel",
                                           "avg_combined_rate", "labeled_recall"])
        w.writeheader()
        w.writerows(results)

    print(f"\nWrote {len(results)} config(s) -> {out_path}")
    print("\nTop 10 by avg_combined_rate:")
    for r in results[:10]:
        lr = f"{r['labeled_recall']:.3f}" if r["labeled_recall"] is not None else "n/a"
        print(f"  stride={r['stride']} thresh={r['diff_threshold']} open_k={r['open_kernel']:2d}  "
              f"avg_combined_rate={r['avg_combined_rate']:.4f}  labeled_recall={lr}")


if __name__ == "__main__":
    main()
