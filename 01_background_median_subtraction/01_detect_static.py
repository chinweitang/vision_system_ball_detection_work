# detect_static.py
# Ball detection on static photos using median-background subtraction.
#
# Run from anywhere:
#   python path/to/code/detect_static.py

from pathlib import Path
import numpy as np
import cv2

# ---- paths (anchored to this script's location, works from any CWD) ----
HERE    = Path(__file__).resolve().parent          # .../detection_work/code/
SESSION = HERE.parent / "2026-05-27_staircase_bringup"
BG_DIR  = SESSION / "background"
ST_DIR  = SESSION / "static"
OUT_DIR = HERE.parent / "static_detection_out"    # .../detection_work/static_detection_out/
OUT_DIR.mkdir(exist_ok=True)

# ---- detection parameters (tune these) ----
DIFF_THRESHOLD = 25     # pixel-value threshold after background subtraction
MIN_AREA       = 200    # smallest candidate blob (pixels). Volleyball at this
                        # resolution/range will be hundreds to thousands of px.
MAX_AREA       = 50000  # largest candidate blob
MIN_CIRC       = 0.3    # circularity = 4*pi*area / perimeter^2 (1.0 = perfect circle)
MORPH_KERNEL   = 7      # size of morphological kernel for open/close
# -------------------------------------------

# ---- 1. Build the median background reference from bg_*.jpg + static_*.jpg ----
print("Building median background reference ...")
ref_paths = sorted(list(BG_DIR.glob("*.jpg")) + list(ST_DIR.glob("*.jpg")))
print(f"  Using {len(ref_paths)} images for the median.")

# Load all as grayscale, stack into a 3D array, take the per-pixel median.
stack = np.stack([cv2.imread(str(p), cv2.IMREAD_GRAYSCALE) for p in ref_paths])
background = np.median(stack, axis=0).astype(np.uint8)
cv2.imwrite(str(OUT_DIR / "_median_background.png"), background)
print(f"  Saved median background to {OUT_DIR / '_median_background.png'}")

# ---- 2. Run detection on each static image ----
static_paths = sorted(ST_DIR.glob("*.jpg"))
print(f"\nProcessing {len(static_paths)} static images ...")

for path in static_paths:
    name = path.stem
    img  = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)

    # 2a. Subtract background, get a "what changed" image
    diff = cv2.absdiff(img, background)
    cv2.imwrite(str(OUT_DIR / f"{name}_01_diff.png"), diff)

    # 2b. Threshold the difference
    _, mask = cv2.threshold(diff, DIFF_THRESHOLD, 255, cv2.THRESH_BINARY)

    # 2c. Morphology: open (remove specks), then close (fill holes inside blob)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (MORPH_KERNEL, MORPH_KERNEL))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    cv2.imwrite(str(OUT_DIR / f"{name}_02_mask.png"), mask)

    # 2d. Find contours
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # 2e. Filter by area + circularity, collect candidates
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

    # 2f. Pick the largest candidate (simple strategy; refine later if needed)
    vis = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if candidates:
        best = max(candidates, key=lambda d: d["area"])
        u, v, area, circ = best["u"], best["v"], best["area"], best["circ"]
        # Draw all candidates in yellow, best in green
        for d in candidates:
            color = (0, 255, 0) if d is best else (0, 255, 255)
            cv2.drawContours(vis, [d["contour"]], -1, color, 2)
        cv2.circle(vis, (int(u), int(v)), 8, (0, 255, 0), -1)
        cv2.putText(vis, f"u={u:.1f} v={v:.1f} a={int(area)} c={circ:.2f} n={len(candidates)}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        print(f"  {name}: detected at ({u:.1f}, {v:.1f}), area={int(area)}, circ={circ:.2f}, candidates={len(candidates)}")
    else:
        cv2.putText(vis, "NO DETECTION", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        print(f"  {name}: NO DETECTION")

    cv2.imwrite(str(OUT_DIR / f"{name}_03_detection.png"), vis)

print(f"\nDone. Outputs in {OUT_DIR}/")