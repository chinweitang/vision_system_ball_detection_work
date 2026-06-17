# 03_three_frame_diff.py
# Three-frame differencing: AND of backward and forward diffs eliminates ghost
# blobs so the detected centroid corresponds to the ball in the target frame.
#
#   back_diff = absdiff(frame_N,     frame_{N-S})
#   fwd_diff  = absdiff(frame_{N+S}, frame_N)
#   combined  = threshold(min(back_diff, fwd_diff))   [softer min-diff intersection]
#
# Requires S future frames → S frames of latency (negligible at video rates).
# Loses S frames at BOTH ends of the sequence (not just the start).
#
# Run from anywhere:
#   python path/to/code/03_three_frame_diff.py

from pathlib import Path
import numpy as np
import cv2

# ---- paths ----
HERE    = Path(__file__).resolve().parent
SESSION = HERE.parent / "data" / "2026-06-01_Dyson_library_test"
MOV_DIR = SESSION / "moving" / "flight_01"

# ---- stride ----
STRIDE = 3   # change to 1 or 3 to re-run

STRIDE_OUT_NAMES = {1: "04_3f_stride1", 2: "05_3f_stride2", 3: "06_3f_stride3"}
OUT_DIR = SESSION / "tuning" / "02_moving" / STRIDE_OUT_NAMES[STRIDE]
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---- which flights to process ----
FLIGHTS = ["flight_01_towards_leg"]

# ---- contact sheet layout ----
COLS_PER_ROW = 8
PANEL_W      = 600    # 8 × 600 = 4800 px wide

# ---- detection parameters ----
DIFF_THRESHOLD = 15
OPEN_KERNEL    = 7
CLOSE_KERNEL   = 50
MIN_AREA       = 200
MAX_AREA       = 50000
MIN_CIRC       = 0.3

# ---- helpers ----
def run_morph_and_contours(mask):
    """Morphology + contour filter on a pre-built binary mask.
    Returns (candidates, best|None, morphed_mask)."""
    open_k  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (OPEN_KERNEL,  OPEN_KERNEL))
    close_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (CLOSE_KERNEL, CLOSE_KERNEL))
    morphed = cv2.morphologyEx(mask,    cv2.MORPH_OPEN,  open_k)
    morphed = cv2.morphologyEx(morphed, cv2.MORPH_CLOSE, close_k)
    contours, _ = cv2.findContours(morphed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
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
    return candidates, best, morphed


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
    frame_paths = sorted(
        list(flight_dir.glob("*.jpg")) + list(flight_dir.glob("*.png"))
    )

    if not frame_paths:
        print(f"{flight_name}: no images found, skipping.\n")
        continue

    n_processable = len(frame_paths) - 2 * STRIDE
    print(f"{flight_name}: {len(frame_paths)} frames ({n_processable} processable)")

    back_panels = []
    fwd_panels  = []
    comb_panels = []
    det_panels  = []

    for i in range(STRIDE, len(frame_paths) - STRIDE):
        img_prev = cv2.imread(str(frame_paths[i - STRIDE]), cv2.IMREAD_GRAYSCALE)
        img_curr = cv2.imread(str(frame_paths[i]),           cv2.IMREAD_GRAYSCALE)
        img_next = cv2.imread(str(frame_paths[i + STRIDE]),  cv2.IMREAD_GRAYSCALE)
        name = frame_paths[i].stem

        back_diff = cv2.absdiff(img_curr, img_prev)
        fwd_diff  = cv2.absdiff(img_next, img_curr)

        min_diff = cv2.min(back_diff, fwd_diff)
        _, combined = cv2.threshold(min_diff, DIFF_THRESHOLD, 255, cv2.THRESH_BINARY)

        candidates, best, morphed = run_morph_and_contours(combined)

        img_bgr = cv2.cvtColor(img_curr, cv2.COLOR_GRAY2BGR)

        # --- back diff panel ---
        bp = scale_to_width(cv2.cvtColor(back_diff, cv2.COLOR_GRAY2BGR), PANEL_W)
        put_text(bp, f"{name} back", y=18, color=(255, 255, 255))
        back_panels.append(bp)

        # --- fwd diff panel ---
        fp = scale_to_width(cv2.cvtColor(fwd_diff, cv2.COLOR_GRAY2BGR), PANEL_W)
        put_text(fp, f"{name} fwd", y=18, color=(255, 255, 255))
        fwd_panels.append(fp)

        # --- combined AND mask panel (after morphology) ---
        cp = scale_to_width(cv2.cvtColor(morphed, cv2.COLOR_GRAY2BGR), PANEL_W)
        put_text(cp, f"{name} AND+morph", y=18, color=(255, 255, 255))
        comb_panels.append(cp)

        # --- detection panel ---
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
    n = len(det_panels)
    blank = np.zeros_like(back_panels[0])
    rows  = []

    for i in range(0, n, COLS_PER_ROW):
        chunk_b = back_panels[i : i + COLS_PER_ROW]
        chunk_f = fwd_panels [i : i + COLS_PER_ROW]
        chunk_c = comb_panels[i : i + COLS_PER_ROW]
        chunk_v = det_panels [i : i + COLS_PER_ROW]
        if len(chunk_b) < COLS_PER_ROW:
            pad     = COLS_PER_ROW - len(chunk_b)
            chunk_b += [blank] * pad
            chunk_f += [blank] * pad
            chunk_c += [blank] * pad
            chunk_v += [blank] * pad
        rows.append(np.hstack(chunk_b))   # row 0: back diff
        rows.append(np.hstack(chunk_f))   # row 1: fwd diff
        rows.append(np.hstack(chunk_c))   # row 2: AND mask (morphed)
        rows.append(np.hstack(chunk_v))   # row 3: detection

    grid     = np.vstack(rows)
    out_path = OUT_DIR / f"{flight_name}_3f_ck{CLOSE_KERNEL}_th{DIFF_THRESHOLD}_min_diff_contact.png"
    cv2.imwrite(str(out_path), grid)
    print(f"  -> {out_path.name}\n")

print(f"Done. Outputs in:\n  {OUT_DIR}")
