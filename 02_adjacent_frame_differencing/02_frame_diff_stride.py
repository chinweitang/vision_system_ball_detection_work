# 02_frame_diff_stride.py
# Stride frame differencing: diff = absdiff(frame_N, frame_{N-STRIDE}).
# Fast-moving ball produces a strong signal; slow-moving people a weak one.
# Produces a 3-row contact sheet (diff / mask / detection) per flight.
#
# Run from anywhere:
#   python path/to/code/02_frame_diff_stride.py

from collections import deque
from pathlib import Path
import numpy as np
import cv2

# ---- paths ----
HERE    = Path(__file__).resolve().parent
SESSION = HERE.parent / "data" / "2026-06-01_Dyson_library_test"
MOV_DIR = SESSION / "moving"

# ---- stride ----
STRIDE = 2   # change to 5 for 5-stride run

STRIDE_OUT_NAMES = {
    3: "02_frame_diff_3stride",
    2: "03_frame_diff_2stride",
}
OUT_DIR = SESSION / "tuning" / "02_moving" / STRIDE_OUT_NAMES[STRIDE]
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---- which flights to process ----
FLIGHT_NUMS = [1, 2, 3, 23, 24, 25]
FLIGHTS = [f"flight_{n:02d}" for n in FLIGHT_NUMS if (MOV_DIR / f"flight_{n:02d}").is_dir()]

# ---- contact sheet layout ----
COLS_PER_ROW = 10
PANEL_W      = 300    # 10 × 300 = 3000 px wide

# ---- settled detection parameters ----
DIFF_THRESHOLD = 20
OPEN_KERNEL    = 7
CLOSE_KERNEL   = 30
MIN_AREA       = 200
MAX_AREA       = 50000
MIN_CIRC       = 0.3

# ---- helpers ----
def run_detection(diff):
    """Threshold → morphology → contour filter → pick largest. Returns (candidates, best|None, mask)."""
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
    cv2.putText(panel, text, (5, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3)
    cv2.putText(panel, text, (5, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)


# ---- process each flight ----
for flight_name in FLIGHTS:
    flight_dir  = MOV_DIR / flight_name
    # Non-recursive glob: sample/ subfolder is skipped automatically
    frame_paths = sorted(
        list(flight_dir.glob("*.jpg")) + list(flight_dir.glob("*.png"))
    )

    if not frame_paths:
        print(f"{flight_name}: no images found, skipping.\n")
        continue

    print(f"{flight_name}: {len(frame_paths)} frames ({len(frame_paths) - STRIDE} processable)")

    diff_panels = []
    mask_panels = []
    det_panels  = []
    buffer      = deque(maxlen=STRIDE + 1)

    for path in frame_paths:
        img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        buffer.append(img)

        if len(buffer) < STRIDE + 1:
            continue   # not enough frames buffered yet

        name    = path.stem
        diff    = cv2.absdiff(img, buffer[0])   # current vs STRIDE frames ago
        img_bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

        candidates, best, mask = run_detection(diff)

        # --- diff panel: raw absdiff, grayscale → BGR ---
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
            print(f"  {name}:  u={u:.1f} v={v:.1f} a={int(area)} c={circ:.2f} n={len(candidates)}")
        else:
            put_text(dp, "NO DETECTION", y=36, color=(0, 0, 255))
            print(f"  {name}:  NO DETECTION")

        det_panels.append(dp)

    # ---- assemble contact sheet ----
    n = len(diff_panels)
    blank = np.zeros_like(diff_panels[0])
    rows  = []

    for i in range(0, n, COLS_PER_ROW):
        chunk_d = diff_panels[i : i + COLS_PER_ROW]
        chunk_m = mask_panels[i : i + COLS_PER_ROW]
        chunk_v = det_panels [i : i + COLS_PER_ROW]
        # pad last row-group if not full
        if len(chunk_d) < COLS_PER_ROW:
            pad = COLS_PER_ROW - len(chunk_d)
            chunk_d += [blank] * pad
            chunk_m += [blank] * pad
            chunk_v += [blank] * pad
        rows.append(np.hstack(chunk_d))   # row 0: diff
        rows.append(np.hstack(chunk_m))   # row 1: mask
        rows.append(np.hstack(chunk_v))   # row 2: detection

    grid     = np.vstack(rows)
    out_path = OUT_DIR / f"{flight_name}_contact.png"
    cv2.imwrite(str(out_path), grid)
    print(f"  -> {out_path.name}\n")

print(f"Done. Outputs in:\n  {OUT_DIR}")
