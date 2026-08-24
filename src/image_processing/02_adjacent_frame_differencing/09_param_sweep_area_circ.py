# 09_param_sweep_area_circ.py
#
# Round 3 of detector tuning (see claude/logs/2026-07-23_ball_detection_rate_
# tuning_worklog.md). Rounds 1-2 found stride=1/thresh=16/open_k=3 plus a
# trajectory-outlier filter and 4 new exclusion-mask zones, landing at
# avg_combined_rate=0.8552 (baseline 0.2772), labeled_recall=0.9259 (baseline
# 0.9074). This round grids MIN_AREA x MIN_CIRC: across the 10-flight sample,
# 196 NO_DETECTION frames have a real-looking blob (area 88-200,
# circ 0.40-0.74, clearly distinguishable from noise at circ 0.17-0.33)
# rejected purely by MIN_AREA=200 - this sweep tests whether loosening it
# recovers those frames without letting new noise in.
#
# Modeled on 06_param_sweep.py's structure (FLIGHT_SAMPLE, ProcessPoolExecutor,
# recall-gated ranking), with 3 differences:
#   1. stride/diff_threshold/open_kernel/close_kernel/max_area/
#      max_speed_px_per_frame/min_run_length are loaded from
#      candidate_config.json (fixed for this sweep) instead of hardcoded -
#      only MIN_AREA and MIN_CIRC are gridded.
#   2. evaluate_config() applies filter_trajectory_outliers() on top of
#      run_detection()'s raw output before scoring - 06's evaluate_config
#      predates the trajectory filter and used raw detections directly,
#      which would make this round's numbers incomparable to the
#      0.8552/0.9259 baseline being improved upon.
#   3. Labeled recall now comes from TWO hand-labeled flights (flight_01: 27
#      frames/cam, flight_22: 93 frames/cam - user labeled flight_22 mid-task,
#      240 labeled points total vs. the original 54), read directly from each
#      flight's own flight_{name}_cam{0,1}_labels.csv (centroid_x, centroid_y,
#      diameter_px columns) rather than the labels_uv.csv convenience file
#      (only flight_01 has one). The recall-gate threshold is RECOMPUTED
#      against this merged 240-point set (see compute_baseline_recall() below)
#      rather than reusing the stale 0.9074 (measured on the old 54-point set)
#      - not a fair comparison otherwise.
#
# meets_recall_gate/is_baseline are computed IN-SCRIPT (06's on-disk CSV has
# these columns but its own .py doesn't produce them - added out-of-band last
# round; not repeating that gap here).
#
# Does NOT touch any real flight data or analysis_3 folders - reads only
# from ball_in_frame/*.png, writes only to
# results/detector_tuning/sweep_results_min_area_circ.csv.
#
# Run from anywhere:
#   python path/to/code/09_param_sweep_area_circ.py

from pathlib import Path
import sys
import csv
import json
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
CONFIG_PATH = OUT_DIR / "candidate_config.json"

CAMS = ["cam0", "cam1"]

# Same 10-flight sample as 06_param_sweep.py/08_generate_contact_sheets.py.
FLIGHT_SAMPLE = [
    (SESSION_15, "2 ball contacts ground before plane/flight_01"),  # labeled
    (SESSION_15, "flight_22"),  # labeled (added mid-task, round 3)
    (SESSION_15, "flight_55"),
    (SESSION_21, "flight_126"),
    (SESSION_21, "flight_47"),
    (SESSION_21, "flight_59"),
    (SESSION_21, "flight_53"),
    (SESSION_21, "flight_60"),
    (SESSION_21, "flight_33"),
    (SESSION_21, "flight_84"),
]

LABELED_FLIGHT_SUBPATHS = [
    "2 ball contacts ground before plane/flight_01",
    "flight_22",
]

LABEL_TOLERANCE_PX_FALLBACK = 20.0  # used if a frame's diameter_px is missing

# -- Fixed this round (loaded from the single-source-of-truth config) --------
CFG = json.load(open(CONFIG_PATH))
STRIDE = CFG["stride"]
DIFF_THRESHOLD = CFG["diff_threshold"]
OPEN_KERNEL = CFG["open_kernel"]
CLOSE_KERNEL = CFG["close_kernel"]
MAX_AREA = CFG["max_area"]
MAX_SPEED_PX_PER_FRAME = CFG["max_speed_px_per_frame"]
MIN_RUN_LENGTH = CFG["min_run_length"]

# -- Grid (this round's variables) -------------------------------------------
MIN_AREAS = [30, 50, 75, 100, 150, 200]
MIN_CIRCS = [0.2, 0.25, 0.3, 0.35]

BASELINE_MIN_AREA = 200  # current config's value, within this grid
BASELINE_MIN_CIRC = 0.3


def load_labels_for_flight(flight_dir: Path) -> dict:
    """Returns {(cam_name, frame_number): (u, v, tolerance_px)} read directly
    from that flight's own flight_{name}_cam{0,1}_labels.csv files
    (centroid_x, centroid_y, diameter_px columns) - generalizes across
    labeled flights, not all of which have a consolidated labels_uv.csv (only
    flight_01 does)."""
    name = flight_dir.name  # already e.g. "flight_01"/"flight_22"
    labels = {}
    for cam_name in CAMS:
        p = flight_dir / f"{name}_{cam_name}_labels.csv"
        if not p.is_file():
            continue
        with open(p, newline="") as f:
            for row in csv.DictReader(f):
                fn = int(row["frame_number"])
                u, v = float(row["centroid_x"]), float(row["centroid_y"])
                d = row.get("diameter_px", "")
                tol = (float(d) / 2.0) if d else LABEL_TOLERANCE_PX_FALLBACK
                labels[(cam_name, fn)] = (u, v, tol)
    return labels


def load_all_labels() -> dict:
    """Returns {flight_subpath: {(cam_name, frame_number): (u, v, tol)}} for
    every entry in LABELED_FLIGHT_SUBPATHS."""
    out = {}
    for ball_flights_dir, flight_subpath in FLIGHT_SAMPLE:
        if flight_subpath not in LABELED_FLIGHT_SUBPATHS:
            continue
        out[flight_subpath] = load_labels_for_flight(ball_flights_dir / flight_subpath)
    return out


LABELS_BY_FLIGHT = load_all_labels()


def score_labels(det: dict) -> tuple:
    """(hits, total) across every labeled flight, for a {flight_subpath:
    {cam: {frame_number: (u,v)}}}-shaped detections dict."""
    hits = total = 0
    for flight_subpath, labels in LABELS_BY_FLIGHT.items():
        for (cam_name, fn), (true_u, true_v, tol) in labels.items():
            total += 1
            frame_det = det.get(flight_subpath, {}).get(cam_name, {})
            if fn in frame_det:
                pu, pv = frame_det[fn]
                if ((pu - true_u) ** 2 + (pv - true_v) ** 2) ** 0.5 <= tol:
                    hits += 1
    return hits, total


def compute_historical_baseline_recall() -> float:
    """Recall of the ORIGINAL untuned baseline config (stride=1, thresh=20,
    open_k=7, min_area=200, min_circ=0.3, NO trajectory filter - matches how
    the historical 0.9074 figure was computed in 06_param_sweep.py, before
    the trajectory filter existed) against the CURRENT merged label set
    (flight_01 + flight_22, 240 points). FYI/logging only - NOT used as the
    recall gate (see GATE_RECALL below for why).

    The original 0.9074 was measured on flight_01's 54 points alone. Naively
    recomputing the SAME year-zero config against the bigger merged set drops
    this to ~0.24 - flight_22 was deliberately chosen as one of the 10 sample
    flights BECAUSE it scored 0.000 combined_rate under this exact untuned
    config, so of course its recall here is near-zero too. That's real, but
    it answers "how bad was the very first pre-tuning baseline," not "does
    this round's MIN_AREA/MIN_CIRC choice regress what we have RIGHT NOW" -
    which is what the gate should actually be checking (see GATE_RECALL)."""
    det = {}
    for ball_flights_dir, flight_subpath in FLIGHT_SAMPLE:
        if flight_subpath not in LABELED_FLIGHT_SUBPATHS:
            continue
        flight_dir = ball_flights_dir / flight_subpath
        det[flight_subpath] = {}
        for cam in CAMS:
            cam_dir = flight_dir / cam / "ball_in_frame"
            det[flight_subpath][cam] = dc.run_detection(
                cam_dir, cam, 1, 20, 7, 30, 200, 50000, 0.3)  # original defaults, no filter
    hits, total = score_labels(det)
    return hits / total if total else 0.0


HISTORICAL_BASELINE_RECALL = compute_historical_baseline_recall()


def run_one_config(min_area, min_circ):
    """Pure computation for one (min_area, min_circ): avg_combined_rate and
    labeled_recall under the full current pipeline (stride/thresh/open_k/
    close_k from candidate_config.json + trajectory filter). No gate logic
    here - see evaluate_config(), which wraps this and adds the gate fields
    (kept separate to avoid a circular dependency: the gate threshold itself
    is this function's own result at the baseline min_area/min_circ)."""
    per_flight_combined = []
    det_by_flight = {}

    for ball_flights_dir, flight_subpath in FLIGHT_SAMPLE:
        flight_dir = ball_flights_dir / flight_subpath
        proc, det = {}, {}
        for cam in CAMS:
            cam_dir = flight_dir / cam / "ball_in_frame"
            proc[cam] = dc.processable_frame_numbers(cam_dir, STRIDE)
            raw = dc.run_detection(cam_dir, cam, STRIDE, DIFF_THRESHOLD, OPEN_KERNEL, CLOSE_KERNEL,
                                    min_area, MAX_AREA, min_circ)
            det[cam] = dc.filter_trajectory_outliers(
                raw, max_speed_px_per_frame=MAX_SPEED_PX_PER_FRAME, min_run_length=MIN_RUN_LENGTH)

        co_processable = proc["cam0"] & proc["cam1"]
        co_detected = set(det["cam0"]) & set(det["cam1"])
        if co_processable:
            per_flight_combined.append(len(co_detected) / len(co_processable))

        if flight_subpath in LABELED_FLIGHT_SUBPATHS:
            det_by_flight[flight_subpath] = det

    avg_combined_rate = sum(per_flight_combined) / len(per_flight_combined) if per_flight_combined else 0.0
    label_hits, label_total = score_labels(det_by_flight)
    labeled_recall = (label_hits / label_total) if label_total else None
    return avg_combined_rate, labeled_recall


def compute_gate_recall() -> float:
    """Recall of the CURRENT full pipeline (this round's fixed stride/thresh/
    open_k/close_k + trajectory filter, at min_area=200/min_circ=0.3 - i.e.
    unchanged from candidate_config.json) against the merged label set. THIS
    is the recall gate: does a new MIN_AREA/MIN_CIRC choice do at least as
    well as what we already have, not "at least as well as the very first
    untuned baseline" (HISTORICAL_BASELINE_RECALL above, ~0.24 - such a low
    bar it would gate almost nothing)."""
    _, recall = run_one_config(BASELINE_MIN_AREA, BASELINE_MIN_CIRC)
    return recall


GATE_RECALL = compute_gate_recall()


def evaluate_config(config):
    min_area, min_circ = config
    avg_combined_rate, labeled_recall = run_one_config(min_area, min_circ)
    return {
        "min_area": min_area,
        "min_circ": min_circ,
        "avg_combined_rate": avg_combined_rate,
        "labeled_recall": labeled_recall,
        "meets_recall_gate": labeled_recall is not None and labeled_recall >= GATE_RECALL,
        "is_baseline": (min_area == BASELINE_MIN_AREA and min_circ == BASELINE_MIN_CIRC),
    }


def main():
    n_label_points = sum(len(v) for v in LABELS_BY_FLIGHT.values())
    print(f"Historical baseline recall (year-zero config, no trajectory filter) against "
          f"merged flight_01+flight_22 label set ({n_label_points} points): "
          f"{HISTORICAL_BASELINE_RECALL:.4f} (FYI only, NOT the gate)")
    print(f"Gate recall (current full pipeline at min_area=200/min_circ=0.3): {GATE_RECALL:.4f} "
          f"(THIS is the meets_recall_gate threshold)")

    configs = list(itertools.product(MIN_AREAS, MIN_CIRCS))
    print(f"Sweeping {len(configs)} MIN_AREA x MIN_CIRC configs over {len(FLIGHT_SAMPLE)} flights "
          f"(stride={STRIDE} thresh={DIFF_THRESHOLD} open_k={OPEN_KERNEL} fixed)...")

    results = []
    with ProcessPoolExecutor() as ex:
        futures = {ex.submit(evaluate_config, c): c for c in configs}
        done = 0
        for fut in as_completed(futures):
            results.append(fut.result())
            done += 1
            if done % 8 == 0 or done == len(configs):
                print(f"  {done}/{len(configs)} configs done")

    results.sort(key=lambda r: (not r["meets_recall_gate"], -r["avg_combined_rate"]))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "sweep_results_min_area_circ.csv"
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["min_area", "min_circ", "avg_combined_rate",
                                           "labeled_recall", "meets_recall_gate", "is_baseline"])
        w.writeheader()
        w.writerows(results)

    print(f"\nWrote {len(results)} config(s) -> {out_path}")
    print(f"\nGate-passing candidates (labeled_recall >= {GATE_RECALL:.4f}), ranked by avg_combined_rate:")
    for r in [r for r in results if r["meets_recall_gate"]]:
        base = " [BASELINE]" if r["is_baseline"] else ""
        lr = f"{r['labeled_recall']:.4f}" if r["labeled_recall"] is not None else "n/a"
        print(f"  min_area={r['min_area']:>3} min_circ={r['min_circ']:.2f}  "
              f"avg_combined_rate={r['avg_combined_rate']:.4f}  labeled_recall={lr}{base}")


if __name__ == "__main__":
    main()
