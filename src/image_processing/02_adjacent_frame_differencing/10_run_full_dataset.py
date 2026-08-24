# 10_run_full_dataset.py
#
# Full-dataset production run (all 163 flights, both sessions) at the
# current best config (results/detector_tuning/candidate_config.json) - the
# conclusion of the 2026-07-23/24 tuning session (see the worklog and
# results/detector_tuning/history/results_history.csv).
#
# Two outputs, both centralized under results/detector_tuning/ rather than
# scattered per-flight (the 04_stereo_three_frame_diff.py convention writes
# an analysis_N folder inside EACH flight - hard to browse across 163
# flights in 2 session directories):
#   1. Contact sheets (same 4-row layout as 08_generate_contact_sheets.py)
#      for every flight/cam -> data/detector_tuning/contact_sheets/<STAGE>/
#   2. Full per-flight combined_rate breakdown, overwriting
#      results/detector_tuning/candidate_config_validated_results.csv (this
#      file is established as "current state, OK to overwrite" - see
#      results_history.csv for the permanent record of every prior stage).
#
# STAGE is set BY HAND below, not auto-derived from the config - "round
# number" is a documentation concept, not a config property (user's
# decision, 2026-07-24).
#
# Parallelized per (flight, cam) via ProcessPoolExecutor - 08's single-
# threaded approach took a few minutes for 20 sheets (10-flight sample);
# scaled linearly to 326 sheets (163 flights) that would be too slow.
#
# Run from anywhere:
#   python path/to/code/10_run_full_dataset.py

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

STAGE = "03_stride1_thresh16_openk3_area30_circ0.3"  # bump by hand each round

SESSION_15 = REPO_ROOT / "data" / "2026_07_15_gym" / "ball_flights"
SESSION_21 = REPO_ROOT / "data" / "2026_07_21_gym" / "ball_flights"
DETECTOR_TUNING_DIR = REPO_ROOT / "results" / "detector_tuning"
CONFIG_PATH = DETECTOR_TUNING_DIR / "candidate_config.json"
CONTACT_SHEETS_DIR = REPO_ROOT / "data" / "detector_tuning" / "contact_sheets" / STAGE
VALIDATED_RESULTS_CSV = DETECTOR_TUNING_DIR / "candidate_config_validated_results.csv"

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
    """Yield (flight_id, flight_dir) for every dir with a populated
    ball_in_frame, at any depth - same enumeration convention as
    07_artifact_audit.py, but flight_id is session-qualified
    ("<session_name>/<relative_path>"), NOT just flight_dir.name.

    2026_07_21_gym covers flight_1-149 and 2026_07_15_gym separately has
    flight_11-60 (plus nested subfolders) - 36 of its 37 flight numbers
    collide with a same-named flight in the other session. Using bare
    flight_dir.name as an identifier silently overwrote contact sheets
    across sessions and produced indistinguishable duplicate CSV rows the
    first time this ran across the full dataset - session-qualifying fixes
    both.

    Uses flight_dir.name (not the full relative path) after the session
    prefix - confirmed no basename collides with another flight WITHIN the
    same session, so this stays unique, and it matters: the one nested
    flight ("2 ball contacts ground before plane/flight_01") produced a
    281-character path once session-prefixed AND fully-nested, over
    Windows' 260-char MAX_PATH - both its contact sheets silently failed to
    write. Dropping the intermediate subfolder from the identifier (session
    + basename only) fixes the path length while staying unique."""
    seen = set()
    for bif in sorted(base.rglob("ball_in_frame")):
        if not any(bif.glob("frame_*.png")):
            continue
        flight_dir = bif.parent.parent
        if flight_dir in seen:
            continue
        seen.add(flight_dir)
        flight_id = f"{base.parent.name}/{flight_dir.name}"  # base.parent.name e.g. "2026_07_15_gym"
        yield flight_id, flight_dir


def sanitize_for_filename(flight_id: str) -> str:
    return flight_id.replace("/", "_").replace(" ", "_")


def load_labels_for_flight(flight_dir: Path) -> dict:
    """{(cam_name, frame_number): (u, v, tolerance_px)} from that flight's
    own flight_{name}_cam{0,1}_labels.csv - same as 09_param_sweep_area_circ.py."""
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
    """Runs detection, writes this flight/cam's contact sheet, and returns
    what the orchestrating process needs to compute combined_rate (the
    processable set and the kept-detections dict) plus labeled-recall
    ingredients for the 2 labeled flights."""
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
        put_text(mp, f"{name} AND+morph", y=18, color=(255, 255, 255))
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
    print(f"Running full dataset: {len(flights)} flights x {len(CAMS)} cams "
          f"(stride={STRIDE} thresh={DIFF_THRESHOLD} open_k={OPEN_KERNEL} "
          f"min_area={MIN_AREA} min_circ={MIN_CIRC})...")
    print(f"Contact sheets -> {CONTACT_SHEETS_DIR}")

    tasks = [(str(fd), label, cam) for label, fd in flights for cam in CAMS]
    per_flight = {}  # flight_dir_str -> {"label": ..., cam: (processable, kept)}

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
                 "combined_rate": f"stride={STRIDE} thresh={DIFF_THRESHOLD} open_k={OPEN_KERNEL} "
                                   f"close_k={CLOSE_KERNEL} min_area={MIN_AREA} max_area={MAX_AREA} "
                                   f"min_circ={MIN_CIRC} + exclusion_mask_v4(12 zones total) + "
                                   f"trajectory_filter(max_speed={MAX_SPEED_PX_PER_FRAME},"
                                   f"min_run={MIN_RUN_LENGTH}) - FULL {len(flights)}-FLIGHT DATASET"})

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
