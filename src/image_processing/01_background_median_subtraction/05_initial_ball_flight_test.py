# 04_flight_strip.py
# Test settled detection parameters on real ball flights.
# Produces a 2-row strip (mask + detection) per flight in tuning/09_flight_strip/.
#
# Run from anywhere:
#   python path/to/code/04_flight_strip.py

from pathlib import Path
import numpy as np
import cv2

# ---- paths ----
HERE    = Path(__file__).resolve().parent
SESSION = HERE.parent / "2026-05-27_staircase_bringup"
BG_DIR  = SESSION / "background"
ST_DIR  = SESSION / "static"
MOV_DIR = SESSION / "moving"
OUT_DIR = SESSION / "tuning" / "09_flight_strip"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---- settled detection parameters ----
DIFF_THRESHOLD = 20
OPEN_KERNEL    = 7
CLOSE_KERNEL   = 30
MIN_AREA       = 200
MAX_AREA       = 50000
MIN_CIRC       = 0.3
PANEL_W        = 300   # 20 frames × 300 px = 6000 px wide

# ---- 1. Build median background ONCE ----
print("Building median background ...")
ref_paths  = sorted(list(BG_DIR.glob("*.jpg")) + list(ST_DIR.glob("*.jpg")))
stack      = np.stack([cv2.imread(str(p), cv2.IMREAD_GRAYSCALE) for p in ref_paths])
background = np.median(stack, axis=0).astype(np.uint8)
print(f"  {len(ref_paths)} reference images used.\n")

# ---- helpers ----
def run_detection(diff):
    """Fixed parameters throughout. Returns (candidates, best|None, mask)."""
    _, mask  = cv2.threshold(diff, DIFF_THRESHOLD, 255, cv2.THRESH_BINARY)
    open_k   = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (OPEN_KERNEL,  OPEN_KERNEL))
    close_k  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (CLOSE_KERNEL, CLOSE_KERNEL))
    mask     = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  open_k)
    mask     = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_k)
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
    cv2.putText(panel, text, (5, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3)
    cv2.putText(panel, text, (5, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)


# ---- 2. Process each flight ----
flight_dirs = sorted(d for d in MOV_DIR.iterdir() if d.is_dir())
print(f"Found {len(flight_dirs)} flights.\n")

for flight_dir in flight_dirs:
    frame_paths = sorted(list(flight_dir.glob("*.jpg")) + list(flight_dir.glob("*.png")))
    if not frame_paths:
        print(f"  {flight_dir.name}: no images found, skipping.\n")
        continue

    print(f"{flight_dir.name}  ({len(frame_paths)} frames)")
    mask_panels = []
    det_panels  = []

    for path in frame_paths:
        name    = path.stem
        img     = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        diff    = cv2.absdiff(img, background)
        img_bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

        candidates, best, mask = run_detection(diff)

        # --- mask panel ---
        mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
        mp = scale_to_width(mask_bgr, PANEL_W)
        put_text(mp, name, y=20, color=(255, 255, 255))
        mask_panels.append(mp)

        # --- detection panel: annotate at full res, scale, then add text ---
        vis = img_bgr.copy()
        if candidates:
            for d in candidates:
                color = (0, 255, 0) if d is best else (0, 255, 255)
                cv2.drawContours(vis, [d["contour"]], -1, color, 2)
            u, v, area, circ = best["u"], best["v"], best["area"], best["circ"]
            cv2.circle(vis, (int(u), int(v)), 6, (0, 255, 0), -1)

        dp = scale_to_width(vis, PANEL_W)
        put_text(dp, name, y=20, color=(255, 255, 255))

        if candidates:
            stats = f"u={u:.0f} v={v:.0f} a={int(area)} c={circ:.2f} n={len(candidates)}"
            put_text(dp, stats, y=42, color=(0, 255, 0))
            print(f"  {name}:  u={u:.1f} v={v:.1f} a={int(area)} c={circ:.2f} n={len(candidates)}")
        else:
            put_text(dp, "NO DETECTION", y=42, color=(0, 0, 255))
            print(f"  {name}:  NO DETECTION")

        det_panels.append(dp)

    grid = np.vstack([np.hstack(mask_panels), np.hstack(det_panels)])
    out_path = OUT_DIR / f"{flight_dir.name}_strip.png"
    cv2.imwrite(str(out_path), grid)
    print(f"  → {out_path.name}\n")

print(f"Done. All strips in:\n  {OUT_DIR}")
