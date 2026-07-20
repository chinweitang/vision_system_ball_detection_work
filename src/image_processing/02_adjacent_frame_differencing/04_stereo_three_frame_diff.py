# 04_stereo_three_frame_diff.py
# Same gym harness as 01_frame_diff.py (paths, exclusion mask, CSV format,
# contact-sheet writer, OUT_SUBDIR/OUT_SUFFIX override) with ONLY the diff
# step swapped for the 3-frame min-diff logic from 03_three_frame_diff.py:
#
#   back = absdiff(frame[i],       frame[i-STRIDE])
#   fwd  = absdiff(frame[i+STRIDE], frame[i])
#   combined = threshold(cv2.min(back, fwd), DIFF_THRESHOLD)
#
# then the SAME morphology + exclusion + contour filter + largest-blob pick
# as 01. Centroid is still plain contour moments -- no intensity weighting.
#
# Consequence, not papered over: this loses STRIDE frames at BOTH ends of the
# sequence (01 only lost the first), so the detections CSV is missing the
# first and last STRIDE frame(s) that 01/analysis_2 had.
#
# Run from anywhere:
#   python path/to/code/04_stereo_three_frame_diff.py

from pathlib import Path
import sys
import csv
import numpy as np
import cv2

# ---- paths ----
HERE       = Path(__file__).resolve().parent
REPO_ROOT  = HERE.parents[2]
BALL_FLIGHTS_DIR = REPO_ROOT / "data" / "2026_07_15_gym" / "ball_flights"

sys.path.insert(0, str(REPO_ROOT))
from src.image_processing.exclusion_mask import apply_exclusion

# ---- which flights/cams to process ----
FLIGHTS = ["2 ball contacts ground before plane/flight_01"]
CAMS    = ["cam0", "cam1"]

# ---- verification-run output override ----
# Set OUT_SUBDIR = None and OUT_SUFFIX = "" to restore normal (ball_in_frame /
# flight-folder) output locations.
OUT_SUBDIR = "analysis_3"
OUT_SUFFIX = "3"

# ---- 3-frame stride ----
STRIDE = 1   # frames of separation on each side of the target frame

# ---- contact sheet layout (unchanged from 01) ----
COLS_PER_ROW = 5
PANEL_W      = 600    # 5 × 600 = 3000 px wide

# ---- settled detection parameters (unchanged from 01) ----
DIFF_THRESHOLD = 20
OPEN_KERNEL    = 7
CLOSE_KERNEL   = 30
MIN_AREA       = 200
MAX_AREA       = 50000
MIN_CIRC       = 0.3

# ---- helpers ----
def run_detection(back, fwd, cam_name):
    """3-frame min-diff → threshold → morphology → exclusion → contour filter
    → pick largest. Returns (candidates, best|None, back, fwd, mask)."""
    min_diff = cv2.min(back, fwd)
    _, mask  = cv2.threshold(min_diff, DIFF_THRESHOLD, 255, cv2.THRESH_BINARY)
    open_k   = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (OPEN_KERNEL,  OPEN_KERNEL))
    close_k  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (CLOSE_KERNEL, CLOSE_KERNEL))
    mask     = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  open_k)
    mask     = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_k)
    mask     = apply_exclusion(mask, cam_name)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < MIN_AREA or area > MAX_AREA:
            continue
        perim = cv2.arcLength(c, True)
        if perim == 0:
            continue
        circ = 4 * np.pi * area / (perim * perim)
        if circ < MIN_CIRC:
            continue
        M = cv2.moments(c)
        u = M["m10"] / M["m00"]
        v = M["m01"] / M["m00"]
        candidates.append({"u": u, "v": v, "area": area, "circ": circ, "contour": c})
    best = max(candidates, key=lambda d: d["area"]) if candidates else None
    return candidates, best, mask


def scale_to_width(img_bgr, w):
    h0, w0 = img_bgr.shape[:2]
    h1 = max(1, int(h0 * w / w0))
    return cv2.resize(img_bgr, (w, h1), interpolation=cv2.INTER_AREA)


def put_text(panel, text, y, color):
    """Draw text with a black outline so it reads on any background."""
    cv2.putText(panel, text, (5, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3)
    cv2.putText(panel, text, (5, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)


# ---- process each flight/cam ----
for flight_name in FLIGHTS:
    flight_label = Path(flight_name).name   # last component only, safe for filenames
    for cam_name in CAMS:
        flight_dir = BALL_FLIGHTS_DIR / flight_name / cam_name / "ball_in_frame"
        label      = f"{flight_name}/{cam_name}"
        # Non-recursive, name-filtered glob: previously written contact
        # sheets / CSVs in this same folder are excluded automatically.
        frame_paths = sorted(
            list(flight_dir.glob("frame_*.jpg")) + list(flight_dir.glob("frame_*.png"))
        )

        if not frame_paths:
            print(f"{label}: no images found, skipping.\n")
            continue

        # Loses STRIDE frames at BOTH ends (01 only lost the first).
        n_processable = len(frame_paths) - 2 * STRIDE
        print(f"{label}: {len(frame_paths)} frames ({n_processable} processable, "
              f"STRIDE={STRIDE} lost at each end)")

        back_panels    = []
        fwd_panels     = []
        mask_panels    = []
        det_panels     = []
        detections_out = []   # (frame_number, u, v) for frames with a detection

        for i in range(STRIDE, len(frame_paths) - STRIDE):
            img_prev = cv2.imread(str(frame_paths[i - STRIDE]), cv2.IMREAD_GRAYSCALE)
            img_curr = cv2.imread(str(frame_paths[i]),           cv2.IMREAD_GRAYSCALE)
            img_next = cv2.imread(str(frame_paths[i + STRIDE]),  cv2.IMREAD_GRAYSCALE)
            name = frame_paths[i].stem

            back = cv2.absdiff(img_curr, img_prev)
            fwd  = cv2.absdiff(img_next, img_curr)
            img_bgr = cv2.cvtColor(img_curr, cv2.COLOR_GRAY2BGR)

            candidates, best, mask = run_detection(back, fwd, cam_name)

            # --- back diff panel ---
            bp = scale_to_width(cv2.cvtColor(back, cv2.COLOR_GRAY2BGR), PANEL_W)
            put_text(bp, f"{name} back", y=18, color=(255, 255, 255))
            back_panels.append(bp)

            # --- fwd diff panel ---
            fp = scale_to_width(cv2.cvtColor(fwd, cv2.COLOR_GRAY2BGR), PANEL_W)
            put_text(fp, f"{name} fwd", y=18, color=(255, 255, 255))
            fwd_panels.append(fp)

            # --- AND+morph mask panel (post exclusion, so the corner cut is visible too) ---
            mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
            mp = scale_to_width(mask_bgr, PANEL_W)
            put_text(mp, f"{name} AND+morph", y=18, color=(255, 255, 255))
            mask_panels.append(mp)

            # --- detection panel: annotate at full res, scale, then text ---
            vis = img_bgr.copy()
            if candidates:
                for d in candidates:
                    color = (0, 255, 0) if d is best else (0, 255, 255)
                    cv2.drawContours(vis, [d["contour"]], -1, color, 2)
                u, v, area, circ = best["u"], best["v"], best["area"], best["circ"]
                cv2.circle(vis, (int(u), int(v)), 6, (0, 255, 0), -1)

            dp = scale_to_width(vis, PANEL_W)
            put_text(dp, name, y=18, color=(255, 255, 255))

            if candidates:
                stats = f"u={u:.0f} v={v:.0f} a={int(area)} c={circ:.2f} n={len(candidates)}"
                put_text(dp, stats, y=36, color=(0, 255, 0))
                print(f"  {name}:  u={u:.1f} v={v:.1f} a={int(area)} c={circ:.2f} n={len(candidates)}")
                detections_out.append((int(name.split("_")[1]), u, v))
            else:
                put_text(dp, "NO DETECTION", y=36, color=(0, 0, 255))
                print(f"  {name}:  NO DETECTION")

            det_panels.append(dp)

        # ---- assemble 4-row contact sheet (back / fwd / AND+morph / detection) ----
        n = len(back_panels)
        blank = np.zeros_like(back_panels[0])
        rows  = []

        for i in range(0, n, COLS_PER_ROW):
            chunk_b = back_panels[i : i + COLS_PER_ROW]
            chunk_f = fwd_panels [i : i + COLS_PER_ROW]
            chunk_m = mask_panels[i : i + COLS_PER_ROW]
            chunk_v = det_panels [i : i + COLS_PER_ROW]
            # pad last row-group if not full
            if len(chunk_b) < COLS_PER_ROW:
                pad = COLS_PER_ROW - len(chunk_b)
                chunk_b += [blank] * pad
                chunk_f += [blank] * pad
                chunk_m += [blank] * pad
                chunk_v += [blank] * pad
            rows.append(np.hstack(chunk_b))   # row 0: back diff
            rows.append(np.hstack(chunk_f))   # row 1: fwd diff
            rows.append(np.hstack(chunk_m))   # row 2: AND+morph mask
            rows.append(np.hstack(chunk_v))   # row 3: detection

        grid = np.vstack(rows)
        flight_folder = flight_dir.parents[1]
        if OUT_SUBDIR:
            out_dir = flight_folder / OUT_SUBDIR
            out_dir.mkdir(parents=True, exist_ok=True)
            contact_dir = csv_dir = out_dir
        else:
            contact_dir = flight_dir
            csv_dir     = flight_folder

        out_path = contact_dir / f"{flight_label}_{cam_name}_stride1_contact{OUT_SUFFIX}.png"
        cv2.imwrite(str(out_path), grid)
        print(f"  -> {out_path}")

        # ---- write detected centroids to CSV (next to the labels CSV) ----
        csv_path = csv_dir / f"{flight_label}_{cam_name}_detections{OUT_SUFFIX}.csv"
        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["frame_number", "u", "v"])
            for fn, u_out, v_out in detections_out:
                w.writerow([fn, f"{u_out:.4f}", f"{v_out:.4f}"])
        print(f"  -> {csv_path}\n")

print("Done.")
