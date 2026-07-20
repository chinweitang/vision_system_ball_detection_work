# 02_exposure_sweep_diff.py
# Adjacent frame differencing (diff = absdiff(frame_N, frame_N-1)) run over
# stereo exposure-sweep data: every exp*_gain* setting, both cam0/cam1.
# Same detector as 01_frame_diff.py, with identical parameters, so the only
# thing varying across outputs is the exposure/gain setting -- not the
# detector. Produces a 3-row contact sheet (diff / mask / detection) and a
# full-resolution ball-crop strip per (setting, camera).
#
# NOTE: this data has no manual centroid labels, so there is no ground truth
# and no centroid-error column. Most frames also contain no ball -- it
# crosses the frame in ~0.5s of a 3-6s burst -- so detection_pct over ALL
# frames is expected to be low. That is a diagnostic number, not a pass/fail
# metric for a given exposure setting.
#
# Run from anywhere:
#   python path/to/code/02_exposure_sweep_diff.py [sweep_dir]
#
# sweep_dir is a path (relative to the repo root, or absolute) to the folder
# to sweep; it is searched RECURSIVELY for exp*_gain* setting folders, so
# nesting (e.g. exposure_sweep/sweep3/exp1000_gain4.0/) is handled the same
# as a flat layout. Defaults to data/2026_07_15_lab_session/exposure_sweep.

from pathlib import Path
import sys
import csv
import numpy as np
import cv2

# ---- paths ----
HERE      = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent.parent

sys.path.insert(0, str(REPO_ROOT))
from src.image_processing.exclusion_mask import apply_exclusion
SWEEP_ARG = sys.argv[1] if len(sys.argv) > 1 else "data/2026_07_15_lab_session/exposure_sweep"
SWEEP_DIR = Path(SWEEP_ARG)
if not SWEEP_DIR.is_absolute():
    SWEEP_DIR = REPO_ROOT / SWEEP_DIR
OUT_DIR = SWEEP_DIR / "results"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---- contact sheet layout ----
COLS_PER_ROW = 5
PANEL_W      = 600    # 5 x 600 = 3000 px wide

# ---- ball-crop strip ----
CROP_SIZE = 200        # full-resolution px, centred on the detection centroid
MAX_CROPS = 8

# ---- settled detection parameters (identical to 01_frame_diff.py) ----
# Must not vary between exposure settings: the point of this sweep is to
# compare exposures under one fixed detector, not to retune per setting.
DIFF_THRESHOLD = 20
OPEN_KERNEL    = 7
CLOSE_KERNEL   = 30
MIN_AREA       = 200
MAX_AREA       = 50000
MIN_CIRC       = 0.3


# ---- helpers (unchanged from 01_frame_diff.py) ----
def run_detection(diff, cam_name):
    """Threshold → morphology → contour filter → pick largest. Returns (candidates, best|None, mask)."""
    _, mask  = cv2.threshold(diff, DIFF_THRESHOLD, 255, cv2.THRESH_BINARY)
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


# ---- exposure-sweep-specific helpers ----
def discover_settings(sweep_dir):
    """Every exp*_gain* directory under sweep_dir, at any depth, sorted by path."""
    return sorted((p for p in sweep_dir.rglob("exp*_gain*") if p.is_dir()), key=str)


def setting_label(setting_dir, sweep_dir):
    """Unique, filesystem-safe label for a setting dir, preserving any nesting
    (e.g. sweep3/exp1000_gain4.0 -> 'sweep3_exp1000_gain4.0') so outputs from
    differently-nested setting folders of the same name never collide."""
    return "_".join(setting_dir.relative_to(sweep_dir).parts)


def discover_cams(setting_dir):
    """Every cam* subdirectory of a setting, sorted by name."""
    return sorted(p for p in setting_dir.glob("cam*") if p.is_dir())


def crop_centered(img_bgr, cx, cy, size):
    """size x size crop centred on (cx, cy) at full resolution, clamped to stay inside the image."""
    h, w = img_bgr.shape[:2]
    half = size // 2
    x0 = max(0, min(int(round(cx)) - half, w - size))
    y0 = max(0, min(int(round(cy)) - half, h - size))
    return img_bgr[y0:y0 + size, x0:x0 + size]


# ---- discover and process every (setting, camera) ----
settings = discover_settings(SWEEP_DIR)
if not settings:
    raise SystemExit(f"No exp*_gain* folders found under {SWEEP_DIR}")

summary_rows = []

for setting_dir in settings:
    setting_name = setting_label(setting_dir, SWEEP_DIR)
    for cam_dir in discover_cams(setting_dir):
        cam_name = cam_dir.name
        frame_paths = sorted(
            list(cam_dir.glob("*.jpg")) + list(cam_dir.glob("*.png"))
        )

        if not frame_paths:
            print(f"{setting_name}/{cam_name}: no images found, skipping.\n")
            continue

        print(f"{setting_name}/{cam_name}: {len(frame_paths)} frames "
              f"({len(frame_paths) - 1} processable)")

        diff_panels  = []
        mask_panels  = []
        det_panels   = []
        detections   = []   # (raw_frame_bgr, u, v, name) for frames with a detection
        areas        = []
        circs        = []
        n_detections = 0

        intensity_hist = np.zeros(256, dtype=np.int64)  # over every raw frame, not diffs

        prev_img = None
        for path in frame_paths:
            img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            intensity_hist += np.bincount(img.ravel(), minlength=256)

            if prev_img is None:
                prev_img = img
                continue           # frame 0: no predecessor, skip output

            name     = path.stem
            diff     = cv2.absdiff(img, prev_img)
            prev_img = img          # slide window forward
            img_bgr  = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

            candidates, best, mask = run_detection(diff, cam_name)

            # --- diff panel: raw absdiff, grayscale -> BGR ---
            diff_bgr = cv2.cvtColor(diff, cv2.COLOR_GRAY2BGR)
            dp_raw = scale_to_width(diff_bgr, PANEL_W)
            put_text(dp_raw, name, y=18, color=(255, 255, 255))
            diff_panels.append(dp_raw)

            # --- mask panel ---
            mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
            mp = scale_to_width(mask_bgr, PANEL_W)
            put_text(mp, name, y=18, color=(255, 255, 255))
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
                n_detections += 1
                areas.append(area)
                circs.append(circ)
                detections.append((img_bgr, u, v, name))
            else:
                put_text(dp, "NO DETECTION", y=36, color=(0, 0, 255))

            det_panels.append(dp)

        # ---- assemble 3-row contact sheet (diff / mask / detection) ----
        n = len(diff_panels)
        blank = np.zeros_like(diff_panels[0])
        rows = []

        for i in range(0, n, COLS_PER_ROW):
            chunk_d = diff_panels[i:i + COLS_PER_ROW]
            chunk_m = mask_panels[i:i + COLS_PER_ROW]
            chunk_v = det_panels[i:i + COLS_PER_ROW]
            if len(chunk_d) < COLS_PER_ROW:
                pad = COLS_PER_ROW - len(chunk_d)
                chunk_d += [blank] * pad
                chunk_m += [blank] * pad
                chunk_v += [blank] * pad
            rows.append(np.hstack(chunk_d))   # row 0: diff
            rows.append(np.hstack(chunk_m))   # row 1: mask
            rows.append(np.hstack(chunk_v))   # row 2: detection

        grid = np.vstack(rows)
        contact_path = OUT_DIR / f"{setting_name}_{cam_name}_contact.png"
        cv2.imwrite(str(contact_path), grid)
        print(f"  -> {contact_path.name}")

        # ---- ball-crop strip: full-res 200x200 crops from raw frames (not diffs), ----
        # ---- to judge motion smear by eye, which the diff panels can't show    ----
        if detections:
            n_pick = min(MAX_CROPS, len(detections))
            idx = sorted(set(int(round(i)) for i in np.linspace(0, len(detections) - 1, num=n_pick)))
            crops = []
            for i in idx:
                raw_bgr, u, v, name = detections[i]
                crop = crop_centered(raw_bgr, u, v, CROP_SIZE).copy()
                put_text(crop, name, y=18, color=(0, 255, 0))
                crops.append(crop)
            crop_strip = np.hstack(crops)
            crops_path = OUT_DIR / f"{setting_name}_{cam_name}_ballcrops.png"
            cv2.imwrite(str(crops_path), crop_strip)
            print(f"  -> {crops_path.name}")
        else:
            print("  -> no detections, skipping ballcrops")

        # ---- summary stats ----
        n_processable = max(1, len(frame_paths) - 1)
        detection_pct = 100.0 * n_detections / n_processable

        total_pixels   = int(intensity_hist.sum())
        levels         = np.arange(256)
        mean_intensity = float((levels * intensity_hist).sum() / total_pixels)
        cum            = np.cumsum(intensity_hist)
        p99_intensity  = float(np.searchsorted(cum, 0.99 * total_pixels))

        summary_rows.append({
            "setting":        setting_name,
            "cam":            cam_name,
            "n_frames":       len(frame_paths),
            "n_detections":   n_detections,
            "detection_pct":  round(detection_pct, 2),
            "mean_area":      round(float(np.mean(areas)), 1) if areas else None,
            "median_area":    round(float(np.median(areas)), 1) if areas else None,
            "mean_circ":      round(float(np.mean(circs)), 3) if circs else None,
            "median_circ":    round(float(np.median(circs)), 3) if circs else None,
            "mean_intensity": round(mean_intensity, 1),
            "p99_intensity":  round(p99_intensity, 1),
        })

        print()

# ---- write + print summary ----
csv_path = OUT_DIR / "exposure_summary.csv"
fieldnames = ["setting", "cam", "n_frames", "n_detections", "detection_pct",
              "mean_area", "median_area", "mean_circ", "median_circ",
              "mean_intensity", "p99_intensity"]
with open(csv_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(summary_rows)
print(f"-> {csv_path}\n")

print("NOTE: most frames contain no ball (it crosses in ~0.5s of a 3-6s burst),")
print("so detection_pct over all frames is expected to be low -- it is a")
print("diagnostic number, not a pass/fail metric for a given exposure setting.\n")

setting_w = max(7, max(len(r["setting"]) for r in summary_rows)) + 1
header = (f"{'setting':<{setting_w}}{'cam':<6}{'n_frames':>9}{'n_det':>7}{'det%':>8}"
          f"{'mean_area':>11}{'med_area':>10}{'mean_circ':>11}{'med_circ':>10}"
          f"{'mean_int':>10}{'p99_int':>9}")
print(header)
print("-" * len(header))
def fmt(v, width, prec):
    return f"{v:{width}.{prec}f}" if v is not None else "n/a".rjust(width)

for r in summary_rows:
    print(
        f"{r['setting']:<{setting_w}}{r['cam']:<6}{r['n_frames']:>9}{r['n_detections']:>7}"
        f"{r['detection_pct']:>8.2f}"
        f"{fmt(r['mean_area'], 11, 1)}"
        f"{fmt(r['median_area'], 10, 1)}"
        f"{fmt(r['mean_circ'], 11, 3)}"
        f"{fmt(r['median_circ'], 10, 3)}"
        f"{r['mean_intensity']:>10.1f}"
        f"{r['p99_intensity']:>9.1f}"
    )

print(f"\nDone. Outputs in:\n  {OUT_DIR}")
