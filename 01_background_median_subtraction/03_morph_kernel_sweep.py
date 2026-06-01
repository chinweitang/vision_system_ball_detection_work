# morph_kernel_sweep.py
# Visualise ball detection across multiple MORPH_KERNEL values at a fixed threshold.
# Produces one 2×7 grid image per static frame in tuning/04_morph_kernel_sweep/.
#
# Run from anywhere:
#   python path/to/code/morph_kernel_sweep.py

from pathlib import Path
import numpy as np
import cv2

# ---- paths ----
HERE    = Path(__file__).resolve().parent
SESSION = HERE.parent / "2026-05-27_staircase_bringup"
BG_DIR  = SESSION / "background"
ST_DIR  = SESSION / "static"
OUT_DIR = SESSION / "tuning" / "04_morph_kernel_sweep"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---- sweep parameters ----
KERNELS = [5, 7, 9, 11, 13, 15]
PANEL_W = 400   # px per panel → (1 ref + N kernels) × 400 px wide

# ---- fixed detection parameters ----
DIFF_THRESHOLD = 15
MIN_AREA       = 200
MAX_AREA       = 50000
MIN_CIRC       = 0.3

# ---- 1. Build median background ONCE ----
print("Building median background ...")
ref_paths  = sorted(list(BG_DIR.glob("*.jpg")) + list(ST_DIR.glob("*.jpg")))
stack      = np.stack([cv2.imread(str(p), cv2.IMREAD_GRAYSCALE) for p in ref_paths])
background = np.median(stack, axis=0).astype(np.uint8)
print(f"  {len(ref_paths)} reference images used.\n")

# ---- helpers ----
def run_detection(diff, kernel_size):
    """Fixed threshold → morphology with given kernel → contour filter → pick largest."""
    _, mask = cv2.threshold(diff, DIFF_THRESHOLD, 255, cv2.THRESH_BINARY)
    kernel  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    mask    = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel)
    mask    = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
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
    cv2.putText(panel, text, (5, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 3)
    cv2.putText(panel, text, (5, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)


# ---- 2. Process each static image ----
static_paths = sorted(ST_DIR.glob("*.jpg"))
print(f"Processing {len(static_paths)} images × {len(KERNELS)} kernel sizes ...\n")

for path in static_paths:
    name    = path.stem
    img     = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    diff    = cv2.absdiff(img, background)          # computed once, reused per kernel
    img_bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

    # Column 0: original image for both rows
    ref_panel = scale_to_width(img_bgr, PANEL_W)
    put_text(ref_panel, "original", y=25, color=(255, 255, 255))

    mask_panels = [ref_panel.copy()]
    det_panels  = [ref_panel.copy()]

    for kernel in KERNELS:
        candidates, best, mask = run_detection(diff, kernel)
        label = f"kernel={kernel}"

        # --- mask panel: scale first, then label ---
        mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
        mp = scale_to_width(mask_bgr, PANEL_W)
        put_text(mp, label, y=25, color=(255, 255, 255))
        mask_panels.append(mp)

        # --- detection panel: annotate at full res, scale, then add text ---
        vis = img_bgr.copy()
        if candidates:
            for d in candidates:
                color = (0, 255, 0) if d is best else (0, 255, 255)
                cv2.drawContours(vis, [d["contour"]], -1, color, 2)
            u, v, area, circ = best["u"], best["v"], best["area"], best["circ"]
            cv2.circle(vis, (int(u), int(v)), 8, (0, 255, 0), -1)

        dp = scale_to_width(vis, PANEL_W)
        put_text(dp, label, y=25, color=(255, 255, 255))

        if candidates:
            stats = f"u={u:.0f} v={v:.0f} a={int(area)} c={circ:.2f} n={len(candidates)}"
            put_text(dp, stats, y=50, color=(0, 255, 0))
            print(f"  {name}  kernel={kernel:2d}:  u={u:.1f} v={v:.1f} "
                  f"a={int(area)} c={circ:.2f} n={len(candidates)}")
        else:
            put_text(dp, "NO DETECTION", y=50, color=(0, 0, 255))
            print(f"  {name}  kernel={kernel:2d}:  NO DETECTION")

        det_panels.append(dp)

    grid = np.vstack([np.hstack(mask_panels), np.hstack(det_panels)])
    out_path = OUT_DIR / f"{name}_sweep.png"
    cv2.imwrite(str(out_path), grid)
    print(f"  → {out_path.name}\n")

print(f"Done. All grids in:\n  {OUT_DIR}")
