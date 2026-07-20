# 01_label_frames.py
# Manual ball centroid labelling: click two points on opposite edges of the ball
# per frame. Saves click coords, centroid, diameter, and inter-frame displacement
# to a CSV. Coordinates are in original-image pixel space (OpenCV convention:
# origin top-left, x right, y down — same as 02_frame_diff_stride.py).
#
# Usage:
#   python 01_label_frames.py [--folder FOLDER] [--output CSV] [--pad N]
#
# Keys:
#   s / Enter        save and advance to next frame
#   Delete           if clicks placed → clear them (re-shows stored overlay if labelled)
#                    if no clicks and frame is labelled → clear the stored overlay to re-label
#   n                mark as no-ball (saves empty row) and advance
#   ← →              navigate frames freely
#   z / 0            reset zoom to fit-screen
#   q / Esc          quit
# Mouse:
#   left-click       place click point (2 needed per label)
#   scroll wheel     zoom in / out, centred on cursor
#   right-click drag pan

import argparse
import csv
import math
import re
from pathlib import Path

import cv2
import numpy as np

# ---- default paths (relative to this script's location) ----
HERE        = Path(__file__).resolve().parent
SESSION     = HERE.parent / "data" / "2026-06-01_Dyson_library_test"
DEFAULT_IN  = SESSION / "moving" / "flight_01" / "flight_01_towards_leg"
DEFAULT_OUT = SESSION / "tuning" / "02_moving"

MAX_DISPLAY_H = 900   # cap display height (px); clicks are inverse-scaled back to original coords
ZOOM_STEP     = 1.25  # zoom in/out multiplier per scroll tick
ZOOM_MAX      = 10.0  # maximum zoom level

# ---- extended key codes for cv2.waitKeyEx ----
# Arrow keys and Delete are not standard ASCII; codes differ by platform.
KEY_LEFT_WIN  = 2424832   # VK_LEFT  (0x25) << 16
KEY_RIGHT_WIN = 2555904   # VK_RIGHT (0x27) << 16
KEY_LEFT_LIN  = 65361
KEY_RIGHT_LIN = 65363
KEY_DEL_WIN   = 3014656   # VK_DELETE (0x2E) << 16
KEY_DEL_ASCII = 127       # ASCII DEL (Linux terminals)

CSV_FIELDS = [
    "frame_number",
    "click1_x", "click1_y",
    "click2_x", "click2_y",
    "centroid_x", "centroid_y",
    "diameter_px",
    "displacement_px", "displacement_norm",
]


# ---- utility ----------------------------------------------------------------

def frame_num(path: Path) -> int:
    """Extract the integer from a filename like 'frame_096.png' → 96."""
    m = re.search(r"(\d+)", path.stem)
    return int(m.group(1)) if m else 0


def load_csv(path: Path) -> dict:
    """Return {frame_number(int): row_dict} from existing CSV, or empty dict."""
    if not path.exists():
        return {}
    with open(path, newline="") as f:
        return {int(r["frame_number"]): r for r in csv.DictReader(f)}


def save_csv(path: Path, labels: dict) -> None:
    """Rewrite entire CSV sorted by frame_number (crash-safe: always complete)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for fn in sorted(labels):
            w.writerow(labels[fn])


def make_no_ball_row(fn: int) -> dict:
    row = {f: "" for f in CSV_FIELDS}
    row["frame_number"] = fn
    return row


def make_row(fn: int, c1: tuple, c2: tuple, labels: dict) -> dict:
    """Compute all derived CSV fields from two click points."""
    cx   = (c1[0] + c2[0]) / 2.0
    cy   = (c1[1] + c2[1]) / 2.0
    diam = math.hypot(c2[0] - c1[0], c2[1] - c1[1])

    # Search backwards for the nearest previous frame with a ball centroid
    disp_px = disp_norm = ""
    for pfn in sorted(labels, reverse=True):
        if pfn >= fn:
            continue
        prev = labels[pfn]
        if prev.get("centroid_x"):
            d = math.hypot(cx - float(prev["centroid_x"]),
                           cy - float(prev["centroid_y"]))
            disp_px   = f"{d:.4f}"
            disp_norm = f"{d / diam:.4f}" if diam else ""
            break

    return {
        "frame_number":    fn,
        "click1_x":        f"{c1[0]:.1f}", "click1_y": f"{c1[1]:.1f}",
        "click2_x":        f"{c2[0]:.1f}", "click2_y": f"{c2[1]:.1f}",
        "centroid_x":      f"{cx:.4f}",    "centroid_y": f"{cy:.4f}",
        "diameter_px":     f"{diam:.4f}",
        "displacement_px": disp_px,        "displacement_norm": disp_norm,
    }


# ---- drawing ----------------------------------------------------------------

def _to_pad(x, y, pad: int):
    """Convert original-image coords to padded-canvas coords."""
    return int(round(x)) + pad, int(round(y)) + pad


def _crosshair(canvas, cx, cy, color, size=8):
    cv2.line(canvas, (cx - size, cy), (cx + size, cy), color, 1)
    cv2.line(canvas, (cx, cy - size), (cx, cy + size), color, 1)


def draw_stored_overlay(canvas: np.ndarray, row: dict, pad: int) -> None:
    """Draw click1, click2, centroid crosshair, and diameter circle from a saved row."""
    if not row.get("click1_x"):
        return  # no-ball row — nothing to draw
    c1x, c1y = _to_pad(float(row["click1_x"]), float(row["click1_y"]), pad)
    c2x, c2y = _to_pad(float(row["click2_x"]), float(row["click2_y"]), pad)
    cx,  cy  = _to_pad(float(row["centroid_x"]), float(row["centroid_y"]), pad)
    r = max(1, int(float(row["diameter_px"]) / 2))
    cv2.circle(canvas, (c1x, c1y), 4, (255, 255, 255), -1)  # click1: white dot
    cv2.circle(canvas, (c2x, c2y), 4, (255, 255, 255), -1)  # click2: white dot
    _crosshair(canvas, cx, cy, (0, 255, 255))                # centroid: yellow cross
    cv2.circle(canvas, (cx, cy), r, (0, 255, 0), 1)         # diameter: green circle


def draw_live_clicks(canvas: np.ndarray, clicks: list, pad: int) -> None:
    """Draw the current-session clicks, and full annotation once 2 are placed."""
    for x, y in clicks:
        cv2.circle(canvas, _to_pad(x, y, pad), 4, (255, 255, 255), -1)

    if len(clicks) == 2:
        c1, c2 = clicks
        cx  = (c1[0] + c2[0]) / 2.0
        cy  = (c1[1] + c2[1]) / 2.0
        r   = max(1, int(math.hypot(c2[0] - c1[0], c2[1] - c1[1]) / 2))
        pcx, pcy = _to_pad(cx, cy, pad)
        _crosshair(canvas, pcx, pcy, (0, 255, 255))
        cv2.circle(canvas, (pcx, pcy), r, (0, 255, 0), 1)


def build_canvas(img_gray: np.ndarray, pad: int,
                 clicks: list, labels: dict, fn: int, redo_mode: bool) -> np.ndarray:
    """Build the full padded BGR display canvas."""
    padded = cv2.copyMakeBorder(
        img_gray, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    canvas = cv2.cvtColor(padded, cv2.COLOR_GRAY2BGR)

    # Show stored annotation when there are no live clicks and redo not requested
    if fn in labels and not clicks and not redo_mode:
        draw_stored_overlay(canvas, labels[fn], pad)

    # Live clicks override (stored overlay not shown while clicking)
    if clicks:
        draw_live_clicks(canvas, clicks, pad)

    return canvas


def set_title(win: str, idx: int, total: int, fn: int, labels: dict,
              zoom_val: float = 1.0) -> None:
    status = "LABELLED" if fn in labels else "unlabelled"
    cv2.setWindowTitle(
        win,
        f"[{idx + 1}/{total}] frame_{fn:03d}  {status}  {zoom_val:.1f}x | "
        "[s/Enter]=save  [Del]=redo  [n]=no-ball  [← →]=nav  [z]=reset-zoom  [q/Esc]=quit",
    )


# ---- main -------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Manual ball centroid labelling tool.")
    ap.add_argument("--folder", type=Path, default=DEFAULT_IN,
                    help="Folder of PNG frames to label.")
    ap.add_argument("--output", type=Path, default=None,
                    help="Output CSV path (default: <out_dir>/<folder_name>_labels.csv).")
    ap.add_argument("--pad", type=int, default=50,
                    help="Border padding added around the image in pixels (default: 50).")
    args = ap.parse_args()

    folder   = args.folder.resolve()
    pad      = args.pad
    csv_path = (args.output.resolve() if args.output
                else DEFAULT_OUT / f"{folder.name}_labels.csv")

    frames = sorted(folder.glob("frame_*.png"), key=frame_num)
    if not frames:
        print(f"No PNG files found in {folder}")
        return
    print(f"Loaded {len(frames)} frames from {folder}")

    labels = load_csv(csv_path)
    print(f"CSV: {csv_path}  ({len(labels)} frames already labelled)")

    # Resume from first unlabelled frame
    start = next(
        (i for i, fp in enumerate(frames) if frame_num(fp) not in labels),
        len(frames) - 1,
    )

    # ---- shared mutable state (lists so closures can mutate) ----
    idx        = [start]
    clicks     = []       # list of (orig_x, orig_y), max 2
    redo_flag  = [False]  # True = suppress stored overlay for current frame
    img_cache  = [None]   # current frame's grayscale array
    scale      = [1.0]   # display-only downscale to fit MAX_DISPLAY_H; ≤1.0
    fit_dims   = [None]   # (fit_w, fit_h) fixed after first frame load
    zoom       = [1.0]   # additional zoom factor; 1.0 = fit-screen
    pan_x      = [0.0]   # viewport top-left x in fit-canvas coords
    pan_y      = [0.0]   # viewport top-left y in fit-canvas coords
    is_panning = [False]
    drag_start = [None]  # (mx, my, pan_x0, pan_y0) captured on right-button down

    WIN = "Ball Labeller"
    cv2.namedWindow(WIN, cv2.WINDOW_AUTOSIZE)

    def clamp_pan():
        """Keep viewport within fit-canvas bounds."""
        fw, fh = fit_dims[0]
        pan_x[0] = max(0.0, min(pan_x[0], fw - fw / zoom[0]))
        pan_y[0] = max(0.0, min(pan_y[0], fh - fh / zoom[0]))

    def refresh():
        fn     = frame_num(frames[idx[0]])
        canvas = build_canvas(img_cache[0], pad, clicks, labels, fn, redo_flag[0])

        # Step 1: fit-to-screen downscale
        if scale[0] < 1.0:
            fit = cv2.resize(canvas, None, fx=scale[0], fy=scale[0],
                             interpolation=cv2.INTER_AREA)
        else:
            fit = canvas

        # Step 2: zoom viewport crop + upscale (window always stays fit_dims sized)
        fw, fh = fit_dims[0]
        if zoom[0] > 1.0:
            vw = fw / zoom[0]
            vh = fh / zoom[0]
            x0 = int(round(max(0.0, min(pan_x[0], fw - vw))))
            y0 = int(round(max(0.0, min(pan_y[0], fh - vh))))
            x1 = min(x0 + int(round(vw)), fw)
            y1 = min(y0 + int(round(vh)), fh)
            disp = cv2.resize(fit[y0:y1, x0:x1], (fw, fh),
                              interpolation=cv2.INTER_NEAREST)
        else:
            disp = fit

        cv2.imshow(WIN, disp)

    def load_frame(i: int):
        """Load frame i: clear click state, render, update title."""
        clicks.clear()
        redo_flag[0] = False
        idx[0]       = i
        fp           = frames[i]
        fn           = frame_num(fp)
        img_cache[0] = cv2.imread(str(fp), cv2.IMREAD_GRAYSCALE)
        refresh()
        set_title(WIN, i, len(frames), fn, labels, zoom[0])

    def on_mouse(event, x, y, flags, param):
        """Handle left-click (label), scroll wheel (zoom), right-drag (pan)."""

        if event == cv2.EVENT_LBUTTONDOWN and len(clicks) < 2:
            # Convert window → fit canvas → padded canvas → original image coords
            fit_x  = x / zoom[0] + pan_x[0]
            fit_y  = y / zoom[0] + pan_y[0]
            orig_x = int(round(fit_x / scale[0])) - pad
            orig_y = int(round(fit_y / scale[0])) - pad
            clicks.append((orig_x, orig_y))   # may be negative for off-edge balls
            refresh()

        elif event == cv2.EVENT_MOUSEWHEEL:
            factor = ZOOM_STEP if flags > 0 else 1.0 / ZOOM_STEP
            new_z  = max(1.0, min(zoom[0] * factor, ZOOM_MAX))
            # keep the pixel under the cursor fixed in fit-canvas space
            cx = x / zoom[0] + pan_x[0]
            cy = y / zoom[0] + pan_y[0]
            zoom[0]  = new_z
            pan_x[0] = cx - x / zoom[0]
            pan_y[0] = cy - y / zoom[0]
            clamp_pan()
            refresh()
            fn_cur = frame_num(frames[idx[0]])
            set_title(WIN, idx[0], len(frames), fn_cur, labels, zoom[0])

        elif event == cv2.EVENT_RBUTTONDOWN:
            is_panning[0] = True
            drag_start[0] = (x, y, pan_x[0], pan_y[0])

        elif event == cv2.EVENT_MOUSEMOVE and is_panning[0]:
            sx, sy, px0, py0 = drag_start[0]
            pan_x[0] = px0 - (x - sx) / zoom[0]
            pan_y[0] = py0 - (y - sy) / zoom[0]
            clamp_pan()
            refresh()

        elif event == cv2.EVENT_RBUTTONUP:
            is_panning[0] = False

    cv2.setMouseCallback(WIN, on_mouse)

    # Compute display scale and fit canvas size from first frame (all frames same resolution)
    _peek = cv2.imread(str(frames[idx[0]]), cv2.IMREAD_GRAYSCALE)
    _ph, _pw = _peek.shape[0] + 2 * pad, _peek.shape[1] + 2 * pad
    scale[0]    = min(1.0, MAX_DISPLAY_H / _ph)
    fit_dims[0] = (int(round(_pw * scale[0])), int(round(_ph * scale[0])))  # (w, h)

    load_frame(idx[0])

    while True:
        key = cv2.waitKeyEx(50)
        if key == -1:
            continue

        fn = frame_num(frames[idx[0]])

        if key in (ord("q"), 27):                       # ---- quit
            print("Quit.")
            break

        elif key in (KEY_LEFT_WIN, KEY_LEFT_LIN):       # ---- navigate left
            if idx[0] > 0:
                load_frame(idx[0] - 1)

        elif key in (KEY_RIGHT_WIN, KEY_RIGHT_LIN):     # ---- navigate right
            if idx[0] < len(frames) - 1:
                load_frame(idx[0] + 1)

        elif key in (ord("z"), ord("0")):               # ---- reset zoom
            zoom[0]  = 1.0
            pan_x[0] = 0.0
            pan_y[0] = 0.0
            refresh()
            set_title(WIN, idx[0], len(frames), fn, labels, zoom[0])

        elif key in (KEY_DEL_WIN, KEY_DEL_ASCII):       # ---- redo / delete
            if clicks:
                # Clear live clicks; stored overlay re-appears (redo_flag stays False)
                clicks.clear()
                redo_flag[0] = False
            elif fn in labels:
                # No live clicks but frame is labelled: suppress stored overlay
                redo_flag[0] = True
            refresh()

        elif key == ord("n"):                           # ---- no-ball
            labels[fn] = make_no_ball_row(fn)
            save_csv(csv_path, labels)
            print(f"frame {fn:03d}: NO BALL")
            if idx[0] < len(frames) - 1:
                load_frame(idx[0] + 1)
            else:
                set_title(WIN, idx[0], len(frames), fn, labels, zoom[0])

        elif key in (ord("s"), 13):                     # ---- save  (s or Enter)
            if len(clicks) != 2:
                print(f"frame {fn:03d}: need 2 clicks before saving (have {len(clicks)})")
                continue
            c1 = (float(clicks[0][0]), float(clicks[0][1]))
            c2 = (float(clicks[1][0]), float(clicks[1][1]))
            row = make_row(fn, c1, c2, labels)
            labels[fn] = row
            save_csv(csv_path, labels)

            diam = float(row["diameter_px"])
            dn   = row["displacement_norm"]
            dn_s = f"{float(dn):.3f}" if dn else "—"
            print(f"frame {fn:03d}: diameter={diam:.1f}px  disp_norm={dn_s}")

            if idx[0] < len(frames) - 1:
                load_frame(idx[0] + 1)
            else:
                set_title(WIN, idx[0], len(frames), fn, labels, zoom[0])

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
