# 12_run_full_dataset_rect_close_kernel.py
#
# Detection-ACCURACY validation of the rect-close-kernel fix found during the
# Pi real-time benchmark (see claude/decision_log.md #63,
# claude/claude_logs/2026-08-03_pi_realtime_benchmark_worklog.md,
# data/pi_benchmarking/mask_breakdown_results_20260803.json): swapping
# compute_mask's morph-close structuring element from cv2.MORPH_ELLIPSE to
# cv2.MORPH_RECT (same 30x30 size) cut that step's Pi timing 17.6x (84.05ms
# -> 4.77ms), which would bring the whole detection budget inside the
# 16.6ms/frame real-time target. This script checks whether that speed win
# costs any detection ACCURACY, using the exact same methodology, flight set,
# and metrics as the original full-163-flight baseline
# (10_run_full_dataset.py -> data/detector_tuning/candidate_config_validated_results.csv,
# avg_combined_rate=0.9667, labeled_recall=0.9250).
#
# Runs on the LAPTOP, not the Pi -- this is a pure algorithm/accuracy
# question, independent of hardware speed. All flight data and labels
# already live here.
#
# Does NOT modify detector_core.py. The rect-close variant of compute_mask is
# defined below, IDENTICAL to detector_core.compute_mask except the close
# kernel's shape (MORPH_ELLIPSE -> MORPH_RECT, same 30x30 size) -- everything
# else (threshold, open kernel, exclusion) unchanged -- and is installed via
# monkey-patching detector_core.compute_mask at runtime (reassigning the
# module-level name), not by editing the file. Since run_detection ->
# _detect_in_pair -> compute_mask is a normal Python call resolved via the
# module's namespace at call time, this patch takes effect throughout
# detector_core.run_detection() and detector_core.filter_trajectory_outliers()
# runs completely unmodified either way.
#
# Orchestration (flight enumeration, contact-sheet layout, combined_rate /
# labeled_recall computation, parallelization) is a close copy of
# 10_run_full_dataset.py's, reused as closely as possible rather than
# importing that numbered script as a module (numbered scripts in this
# pipeline stage are one-shot, not meant for cross-importing -- unnumbered
# modules like detector_core.py are the reuse boundary). Writes to NEW output
# paths, does not touch the existing ellipse baseline's CSV or contact sheets.
#
# Run from anywhere:
#   python path/to/code/12_run_full_dataset_rect_close_kernel.py

from pathlib import Path
import sys
import csv
import json
import numpy as np
import cv2
from concurrent.futures import ProcessPoolExecutor, as_completed

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO_ROOT))
import detector_core as dc  # noqa: E402
from compute_mask_rect_close_variant import compute_mask_rect_close  # noqa: E402

dc.compute_mask = compute_mask_rect_close  # monkey-patch -- see module docstring

STAGE = "12_rect_close_kernel_validation"

SESSION_15 = REPO_ROOT / "data" / "2026_07_15_gym" / "ball_flights"
SESSION_21 = REPO_ROOT / "data" / "2026_07_21_gym" / "ball_flights"
DETECTOR_TUNING_DIR = REPO_ROOT / "data" / "detector_tuning"
CONFIG_PATH = DETECTOR_TUNING_DIR / "candidate_config.json"
CONTACT_SHEETS_DIR = DETECTOR_TUNING_DIR / "contact_sheets" / STAGE
VALIDATED_RESULTS_CSV = DETECTOR_TUNING_DIR / "candidate_config_rect_close_results.csv"  # NEW file, does not touch the ellipse baseline

CAMS = ["cam0", "cam1"]

LABELED_FLIGHT_SUBPATHS = [
    "2 ball contacts ground before plane/flight_01",
    "flight_22",
]
LABEL_TOLERANCE_PX_FALLBACK = 20.0

COLS_PER_ROW = 5
PANEL_W = 600


def load_config(path=CONFIG_PATH):
    with open(path) as f:
        return json.load(f)


CFG = load_config()
STRIDE, DIFF_THRESHOLD, OPEN_KERNEL, CLOSE_KERNEL = (
    CFG["stride"], CFG["diff_threshold"], CFG["open_kernel"], CFG["close_kernel"])
MIN_AREA, MAX_AREA, MIN_CIRC = CFG["min_area"], CFG["max_area"], CFG["min_circ"]
MAX_SPEED_PX_PER_FRAME, MIN_RUN_LENGTH = CFG["max_speed_px_per_frame"], CFG["min_run_length"]


def find_flight_dirs(base: Path):
    """Same enumeration as 10_run_full_dataset.py -- session-qualified flight
    IDs (session + basename, no intermediate subfolder) to avoid both the
    cross-session flight-number collision and the Windows MAX_PATH issue
    that script already found and fixed."""
    seen = set()
    for bif in sorted(base.rglob("ball_in_frame")):
        if not any(bif.glob("frame_*.png")):
            continue
        flight_dir = bif.parent.parent
        if flight_dir in seen:
            continue
        seen.add(flight_dir)
        flight_id = f"{base.parent.name}/{flight_dir.name}"
        yield flight_id, flight_dir


def sanitize_for_filename(flight_id: str) -> str:
    return flight_id.replace("/", "_").replace(" ", "_")


def load_labels_for_flight(flight_dir: Path) -> dict:
    name = flight_dir.name
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


def scale_to_width(img_bgr, w):
    h0, w0 = img_bgr.shape[:2]
    h1 = max(1, int(h0 * w / w0))
    return cv2.resize(img_bgr, (w, h1), interpolation=cv2.INTER_AREA)


def put_text(panel, text, y, color):
    cv2.putText(panel, text, (5, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3)
    cv2.putText(panel, text, (5, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)


def process_flight_cam(args):
    """Same as 10_run_full_dataset.py's version, but dc.compute_mask is the
    monkey-patched rect-close variant throughout (both dc.run_detection()
    below and the direct dc.compute_mask() call in the visualization loop)."""
    flight_dir_str, flight_id, cam = args
    flight_dir = Path(flight_dir_str)
    cam_dir = flight_dir / cam / "ball_in_frame"
    frame_paths = sorted(cam_dir.glob("frame_*.png"))

    processable = dc.processable_frame_numbers(cam_dir, STRIDE)
    if len(frame_paths) <= 2 * STRIDE:
        return flight_dir_str, flight_id, cam, processable, {}, 0, 0

    imgs = [cv2.imread(str(p), cv2.IMREAD_GRAYSCALE) for p in frame_paths]
    raw = dc.run_detection(cam_dir, cam, STRIDE, DIFF_THRESHOLD, OPEN_KERNEL, CLOSE_KERNEL,
                            MIN_AREA, MAX_AREA, MIN_CIRC)
    kept = dc.filter_trajectory_outliers(raw, max_speed_px_per_frame=MAX_SPEED_PX_PER_FRAME,
                                          min_run_length=MIN_RUN_LENGTH)

    back_panels, fwd_panels, mask_panels, det_panels = [], [], [], []
    n_kept = n_rejected = 0

    for i in range(STRIDE, len(frame_paths) - STRIDE):
        img_prev, img_curr, img_next = imgs[i - STRIDE], imgs[i], imgs[i + STRIDE]
        frame_num = int(dc.FRAME_STEM_RE.search(frame_paths[i].stem).group(1))
        name = frame_paths[i].stem

        back = cv2.absdiff(img_curr, img_prev)
        fwd = cv2.absdiff(img_next, img_curr)
        mask = dc.compute_mask(back, fwd, cam, DIFF_THRESHOLD, OPEN_KERNEL, CLOSE_KERNEL)
        candidates = dc.extract_candidates(mask, MIN_AREA, MAX_AREA, MIN_CIRC)
        img_bgr = cv2.cvtColor(img_curr, cv2.COLOR_GRAY2BGR)

        bp = scale_to_width(cv2.cvtColor(back, cv2.COLOR_GRAY2BGR), PANEL_W)
        put_text(bp, f"{name} back", y=18, color=(255, 255, 255))
        back_panels.append(bp)

        fp = scale_to_width(cv2.cvtColor(fwd, cv2.COLOR_GRAY2BGR), PANEL_W)
        put_text(fp, f"{name} fwd", y=18, color=(255, 255, 255))
        fwd_panels.append(fp)

        mp = scale_to_width(cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR), PANEL_W)
        put_text(mp, f"{name} AND+morph(RECT close)", y=18, color=(255, 255, 255))
        mask_panels.append(mp)

        vis = img_bgr.copy()
        is_kept = frame_num in kept
        best_candidate = max(candidates, key=lambda d: d["area"]) if candidates else None

        if candidates:
            for d in candidates:
                if d is best_candidate:
                    continue
                cv2.drawContours(vis, [d["contour"]], -1, (0, 255, 255), 1)

        if best_candidate is not None:
            u, v = best_candidate["u"], best_candidate["v"]
            color = (0, 255, 0) if is_kept else (0, 165, 255)
            cv2.drawContours(vis, [best_candidate["contour"]], -1, color, 2)
            cv2.circle(vis, (int(u), int(v)), 6, color, -1)
            status = "KEPT" if is_kept else "REJECTED (artifact)"
            put_text(vis, f"{status} u={u:.0f} v={v:.0f}", y=36, color=color)
            if is_kept:
                n_kept += 1
            else:
                n_rejected += 1
        else:
            put_text(vis, "NO DETECTION", y=36, color=(0, 0, 255))

        dp = scale_to_width(vis, PANEL_W)
        put_text(dp, name, y=18, color=(255, 255, 255))
        det_panels.append(dp)

    n = len(back_panels)
    blank = np.zeros_like(back_panels[0])
    rows = []
    for i in range(0, n, COLS_PER_ROW):
        chunk_b = back_panels[i:i + COLS_PER_ROW]
        chunk_f = fwd_panels[i:i + COLS_PER_ROW]
        chunk_m = mask_panels[i:i + COLS_PER_ROW]
        chunk_v = det_panels[i:i + COLS_PER_ROW]
        if len(chunk_b) < COLS_PER_ROW:
            pad = COLS_PER_ROW - len(chunk_b)
            chunk_b += [blank] * pad
            chunk_f += [blank] * pad
            chunk_m += [blank] * pad
            chunk_v += [blank] * pad
        rows.append(np.hstack(chunk_b))
        rows.append(np.hstack(chunk_f))
        rows.append(np.hstack(chunk_m))
        rows.append(np.hstack(chunk_v))

    grid = np.vstack(rows)
    CONTACT_SHEETS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CONTACT_SHEETS_DIR / f"{sanitize_for_filename(flight_id)}_{cam}_contact.png"
    cv2.imwrite(str(out_path), grid)

    return flight_dir_str, flight_id, cam, processable, kept, n_kept, n_rejected


def main():
    flights = []
    for base in [SESSION_15, SESSION_21]:
        flights.extend(find_flight_dirs(base))
    print(f"Running full dataset (RECT close kernel): {len(flights)} flights x {len(CAMS)} cams "
          f"(stride={STRIDE} thresh={DIFF_THRESHOLD} open_k={OPEN_KERNEL}(ellipse) "
          f"close_k={CLOSE_KERNEL}(RECT) min_area={MIN_AREA} min_circ={MIN_CIRC})...")
    print(f"Contact sheets -> {CONTACT_SHEETS_DIR}")

    tasks = [(str(fd), label, cam) for label, fd in flights for cam in CAMS]
    per_flight = {}

    with ProcessPoolExecutor() as ex:
        futures = {ex.submit(process_flight_cam, t): t for t in tasks}
        done = 0
        for fut in as_completed(futures):
            flight_dir_str, flight_id, cam, processable, kept, n_kept, n_rejected = fut.result()
            per_flight.setdefault(flight_dir_str, {"label": flight_id})
            per_flight[flight_dir_str][cam] = (processable, kept)
            done += 1
            if done % 40 == 0 or done == len(tasks):
                print(f"  {done}/{len(tasks)} flight/cam jobs done")

    # -- Labeled recall (flight_01 + flight_22) --------------------------------
    label_hits = label_total = 0
    for base in [SESSION_15, SESSION_21]:
        for label, fd in find_flight_dirs(base):
            rel = str(fd.relative_to(base)).replace("\\", "/")
            if rel not in LABELED_FLIGHT_SUBPATHS:
                continue
            labels = load_labels_for_flight(fd)
            entry = per_flight.get(str(fd), {})
            for (cam_name, fn), (true_u, true_v, tol) in labels.items():
                label_total += 1
                _, kept = entry.get(cam_name, (set(), {}))
                if fn in kept:
                    pu, pv = kept[fn]
                    if ((pu - true_u) ** 2 + (pv - true_v) ** 2) ** 0.5 <= tol:
                        label_hits += 1
    labeled_recall = (label_hits / label_total) if label_total else None

    # -- Per-flight combined_rate -----------------------------------------------
    rows = []
    combined_rates = []
    for flight_dir_str, data in sorted(per_flight.items(), key=lambda kv: kv[1]["label"]):
        proc0, det0 = data.get("cam0", (set(), {}))
        proc1, det1 = data.get("cam1", (set(), {}))
        co_proc = proc0 & proc1
        co_det = set(det0) & set(det1)
        rate = len(co_det) / len(co_proc) if co_proc else 0.0
        combined_rates.append(rate)
        rows.append({"flight": data["label"], "combined_processable": len(co_proc),
                      "combined_detections": len(co_det), "combined_rate": f"{rate:.4f}"})

    avg_combined_rate = sum(combined_rates) / len(combined_rates) if combined_rates else 0.0
    rows.append({"flight": "AVERAGE", "combined_processable": "", "combined_detections": "",
                 "combined_rate": f"{avg_combined_rate:.4f}"})
    rows.append({"flight": "LABELED_RECALL (flight_01 + flight_22)", "combined_processable": "",
                 "combined_detections": "", "combined_rate": f"{labeled_recall:.4f}" if labeled_recall else ""})
    rows.append({"flight": "CONFIG", "combined_processable": "", "combined_detections": "",
                 "combined_rate": f"stride={STRIDE} thresh={DIFF_THRESHOLD} open_k={OPEN_KERNEL}(ELLIPSE) "
                                   f"close_k={CLOSE_KERNEL}(RECT, changed from ELLIPSE) min_area={MIN_AREA} "
                                   f"max_area={MAX_AREA} min_circ={MIN_CIRC} + exclusion_mask_v4(12 zones total) + "
                                   f"trajectory_filter(max_speed={MAX_SPEED_PX_PER_FRAME},"
                                   f"min_run={MIN_RUN_LENGTH}) - FULL {len(flights)}-FLIGHT DATASET, RECT CLOSE KERNEL VALIDATION"})

    with open(VALIDATED_RESULTS_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["flight", "combined_processable", "combined_detections", "combined_rate"])
        w.writeheader()
        w.writerows(rows)

    print(f"\navg_combined_rate: {avg_combined_rate:.4f}")
    print(f"labeled_recall: {labeled_recall:.4f}" if labeled_recall else "labeled_recall: n/a")
    print(f"Wrote {len(rows)} row(s) -> {VALIDATED_RESULTS_CSV}")
    print(f"Wrote {len(tasks)} contact sheet(s) -> {CONTACT_SHEETS_DIR}")


if __name__ == "__main__":
    main()
