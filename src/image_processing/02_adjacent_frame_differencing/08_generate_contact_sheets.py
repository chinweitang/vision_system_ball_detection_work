# 08_generate_contact_sheets.py
#
# Generates contact sheets (same 4-row-per-chunk layout as
# 04_stereo_three_frame_diff.py: back diff / fwd diff / AND+morph mask /
# detection) for the 10-flight validation sample, using the CANDIDATE config
# (stride=1, thresh=16, open_k=3) plus the updated exclusion mask and the
# trajectory-consistency filter - for manual visual review.
#
# Detection panel color code (distinguishes this from 04_'s plain green/red):
#   GREEN circle + contour  = kept detection (survived the trajectory filter)
#   ORANGE circle + contour = candidate detection REJECTED by the trajectory
#                             filter (shown so it's visible what's being
#                             filtered, not just silently dropped)
#   RED "NO DETECTION" text = no candidate blob at all this frame
#
# Does NOT touch any real flight data or analysis_3/4 folders - reads only
# from ball_in_frame/*.png, writes only to data/detector_tuning/contact_sheets/.
#
# Run from anywhere:
#   python path/to/code/08_generate_contact_sheets.py

from pathlib import Path
import sys
import json
import numpy as np
import cv2

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO_ROOT))
import detector_core as dc  # noqa: E402

SESSION_15 = REPO_ROOT / "data" / "2026_07_15_gym" / "ball_flights"
SESSION_21 = REPO_ROOT / "data" / "2026_07_21_gym" / "ball_flights"
DETECTOR_TUNING_DIR = REPO_ROOT / "results" / "detector_tuning"
CONFIG_PATH = DETECTOR_TUNING_DIR / "candidate_config.json"

FLIGHT_SAMPLE = [
    (SESSION_15, "2 ball contacts ground before plane/flight_01"),
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
CAMS = ["cam0", "cam1"]


def load_config(path=CONFIG_PATH):
    """Single source of truth for the "current best" detector config - see
    results/detector_tuning/candidate_config.json and the 2026-07-23 worklog."""
    with open(path) as f:
        return json.load(f)


CFG = load_config()
STRIDE, DIFF_THRESHOLD, OPEN_KERNEL, CLOSE_KERNEL = (
    CFG["stride"], CFG["diff_threshold"], CFG["open_kernel"], CFG["close_kernel"])
MIN_AREA, MAX_AREA, MIN_CIRC = CFG["min_area"], CFG["max_area"], CFG["min_circ"]
MAX_SPEED_PX_PER_FRAME, MIN_RUN_LENGTH = CFG["max_speed_px_per_frame"], CFG["min_run_length"]

# Stage subfolder auto-derived from the config in force at run time - same
# convention as 07_artifact_audit.py, so contact sheets and inspection crops
# for the same config land under matching names.
STAGE = f"area{MIN_AREA}_circ{MIN_CIRC}"
OUT_DIR = REPO_ROOT / "data" / "detector_tuning" / "contact_sheets" / STAGE

COLS_PER_ROW = 5
PANEL_W = 600


def scale_to_width(img_bgr, w):
    h0, w0 = img_bgr.shape[:2]
    h1 = max(1, int(h0 * w / w0))
    return cv2.resize(img_bgr, (w, h1), interpolation=cv2.INTER_AREA)


def put_text(panel, text, y, color):
    cv2.putText(panel, text, (5, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3)
    cv2.putText(panel, text, (5, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)


def build_contact_sheet(cam_dir: Path, cam_name: str, label: str):
    frame_paths = sorted(cam_dir.glob("frame_*.png"))
    if len(frame_paths) <= 2 * STRIDE:
        return None, 0, 0

    imgs = [cv2.imread(str(p), cv2.IMREAD_GRAYSCALE) for p in frame_paths]
    raw = dc.run_detection(cam_dir, cam_name, STRIDE, DIFF_THRESHOLD, OPEN_KERNEL, CLOSE_KERNEL,
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
        mask = dc.compute_mask(back, fwd, cam_name, DIFF_THRESHOLD, OPEN_KERNEL, CLOSE_KERNEL)
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
        is_rejected = frame_num in raw and not is_kept
        best_candidate = max(candidates, key=lambda d: d["area"]) if candidates else None

        if candidates:
            for d in candidates:
                if d is best_candidate:
                    continue
                cv2.drawContours(vis, [d["contour"]], -1, (0, 255, 255), 1)  # other candidates: yellow

        if best_candidate is not None:
            u, v = best_candidate["u"], best_candidate["v"]
            color = (0, 255, 0) if is_kept else (0, 165, 255)  # green kept, orange rejected
            cv2.drawContours(vis, [best_candidate["contour"]], -1, color, 2)  # actual blob shape
            cv2.circle(vis, (int(u), int(v)), 6, color, -1)  # filled centroid dot
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
    return grid, n_kept, n_rejected


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for ball_flights_dir, flight_subpath in FLIGHT_SAMPLE:
        flight_dir = ball_flights_dir / flight_subpath
        flight_label = Path(flight_subpath).name
        for cam in CAMS:
            cam_dir = flight_dir / cam / "ball_in_frame"
            label = f"{flight_subpath}/{cam}"
            grid, n_kept, n_rejected = build_contact_sheet(cam_dir, cam, label)
            if grid is None:
                print(f"{label}: no images found, skipping.")
                continue
            out_path = OUT_DIR / f"{flight_label}_{cam}_contact.png"
            cv2.imwrite(str(out_path), grid)
            print(f"{label}: kept={n_kept} rejected_as_artifact={n_rejected} -> {out_path}")


if __name__ == "__main__":
    main()
