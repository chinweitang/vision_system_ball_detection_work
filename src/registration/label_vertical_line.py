# label_vertical_line.py
# Manual 2-point vertical-line labelling: click the top and bottom of a single
# physical vertical edge (a plumb / vertical wall edge) visible in both
# cameras, for use as an "up" reference in world-frame precision analysis.
# Zoom/pan/coordinate-inversion mechanics reused verbatim from
# label_registration_points.py (see that file's header for the source of the
# fit-canvas math).
#
# The SAME physical top point must be clicked in cam0 and cam1 (and likewise
# for bottom) - along-the-edge position is free, but cross-camera
# correspondence must be tight. Put the two points as far apart vertically as
# the visible edge allows, to best constrain the "up" direction.
#
# Usage:
#   python label_vertical_line.py --cam cam0 --image <path to cam0 frame showing the edge>
#   python label_vertical_line.py --cam cam1 --image <path to cam1 frame showing the edge>
#   (run once per camera - same session as the img36 board, cameras must not
#   have moved between the board and vertical-line captures)
#
# Keys:
#   s / Enter        accept current point's click, advance to next point
#   r / Delete       clear current point's click (or hide its stored marker
#                    to re-click it)
#   <- ->            navigate freely between V_top / V_bottom
#   z                reset zoom to fit-screen
#   q / Esc          quit (prints a labelling summary)
# Mouse:
#   left-click       place (or replace) the click for the current point
#   scroll wheel     zoom in / out, centred on cursor
#   right-click drag pan

import argparse
import csv
from pathlib import Path

import cv2

# ---- paths --------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "data/2026_07_12_session/validation/results/world_frame"

POINT_IDS = ["V_top", "V_bottom"]

MAX_DISPLAY_H = 900   # cap display height (px); clicks are inverse-scaled back to original coords
ZOOM_STEP     = 1.25  # zoom in/out multiplier per scroll tick
ZOOM_MAX      = 20.0  # maximum zoom level - raised so individual markers can be zoomed onto precisely
ZOOM_MIN      = 0.8   # minimum zoom level - lets you zoom out slightly past fit-screen
LETTERBOX_COLOR = (40, 40, 40)  # fill for the margin shown when zoomed out below fit-screen

# ---- extended key codes for cv2.waitKeyEx --------------------------------
KEY_LEFT_WIN  = 2424832   # VK_LEFT  (0x25) << 16
KEY_RIGHT_WIN = 2555904   # VK_RIGHT (0x27) << 16
KEY_LEFT_LIN  = 65361
KEY_RIGHT_LIN = 65363
KEY_DEL_WIN   = 3014656   # VK_DELETE (0x2E) << 16
KEY_DEL_ASCII = 127       # ASCII DEL (Linux terminals)

CSV_FIELDS = ["point_id", "u", "v"]

STORED_COLOR = (0, 200, 0)     # green: already-accepted point
LIVE_COLOR   = (0, 140, 255)   # orange: pending click on the current point, not yet accepted


# ---- CSV I/O --------------------------------------------------------------

def load_csv(path: Path) -> dict:
    """Return {point_id: (u, v)} from an existing CSV, or empty dict."""
    if not path.exists():
        return {}
    with open(path, newline="") as f:
        return {r["point_id"]: (float(r["u"]), float(r["v"])) for r in csv.DictReader(f)}


def save_csv(path: Path, points: dict, point_ids: list) -> None:
    """Rewrite entire CSV in point order (crash-safe: always complete)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for pid in point_ids:
            if pid in points:
                u, v = points[pid]
                w.writerow({"point_id": pid, "u": f"{u:.1f}", "v": f"{v:.1f}"})


# ---- drawing ----------------------------------------------------------------

def draw_marker(canvas, x: float, y: float, pid: str, color) -> None:
    cx, cy = int(round(x)), int(round(y))
    size = 2  # half-length in px -> 5px-long cross arms, no outline
    cv2.line(canvas, (cx - size, cy), (cx + size, cy), color, 1, cv2.LINE_AA)
    cv2.line(canvas, (cx, cy - size), (cx, cy + size), color, 1, cv2.LINE_AA)
    cv2.putText(canvas, pid, (cx + 10, cy - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(canvas, pid, (cx + 10, cy - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)


def build_canvas(img, points: dict, point_ids: list, cur_idx: int,
                  live_click, redo_flag) -> "cv2.Mat":
    """Draw all stored markers plus the current point's live/stored marker."""
    canvas = img.copy()
    for i, pid in enumerate(point_ids):
        if i == cur_idx:
            if live_click[0] is not None:
                x, y = live_click[0]
                draw_marker(canvas, x, y, pid, LIVE_COLOR)
            elif not redo_flag[0] and pid in points:
                x, y = points[pid]
                draw_marker(canvas, x, y, pid, STORED_COLOR)
        elif pid in points:
            x, y = points[pid]
            draw_marker(canvas, x, y, pid, STORED_COLOR)
    return canvas


def draw_banner(canvas, text: str) -> None:
    """Fixed on-screen status bar (drawn after zoom/pan, so it never scales)."""
    h, w = canvas.shape[:2]
    bar_h = 26
    overlay = canvas.copy()
    cv2.rectangle(overlay, (0, 0), (w, bar_h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, canvas, 0.4, 0, canvas)
    cv2.putText(canvas, text, (8, bar_h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)


def banner_text(cam: str, idx: int, point_ids: list, zoom_val: float) -> str:
    pid = point_ids[idx]
    return (f"{cam}  |  now clicking {pid} / {len(point_ids)}  |  {zoom_val:.1f}x  |  "
            "[click]=place  [r/Del]=redo  [s/Enter]=accept  "
            "[<- ->]=nav points  [z]=reset zoom  [q]=quit")


def set_title(win: str, cam: str, idx: int, point_ids: list, points: dict, zoom_val: float) -> None:
    pid = point_ids[idx]
    status = "placed" if pid in points else "empty"
    labelled = sum(1 for p in point_ids if p in points)
    cv2.setWindowTitle(
        win,
        f"{cam}  [{idx + 1}/{len(point_ids)}] {pid} ({status})  "
        f"{labelled}/{len(point_ids)} labelled  {zoom_val:.1f}x",
    )


def print_summary(points: dict, point_ids: list) -> None:
    missing = [pid for pid in point_ids if pid not in points]
    print(f"\n{len(points)}/{len(point_ids)} points labelled.")
    if missing:
        print(f"Missing: {', '.join(missing)}")
    else:
        print("All points labelled.")


# ---- main -------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Manual vertical-line (V_top/V_bottom) labelling tool for world-frame precision analysis.")
    ap.add_argument("--cam", choices=["cam0", "cam1"], required=True,
                    help="Camera to label. Run once per camera.")
    ap.add_argument("--image", required=True,
                    help="Path to this camera's frame showing the vertical edge (same session, "
                         "cameras must not have moved since the img36 board capture).")
    args = ap.parse_args()

    cam = args.cam
    img_path = Path(args.image)
    csv_path = OUTPUT_DIR / f"vertical_{cam}.csv"

    if not img_path.is_file():
        print(f"Image not found: {img_path}")
        return
    img = cv2.imread(str(img_path))
    if img is None:
        print(f"Could not read image: {img_path}")
        return

    point_ids = POINT_IDS
    points = load_csv(csv_path)
    print(f"CSV: {csv_path}  ({len(points)}/{len(point_ids)} points already labelled)")

    # Resume from first unlabelled point
    start = next((i for i, pid in enumerate(point_ids) if pid not in points), 0)

    # ---- shared mutable state (lists so closures can mutate) ----
    idx        = [start]
    live_click = [None]   # (orig_x, orig_y) or None - pending click for the current point
    redo_flag  = [False]  # True = suppress stored marker for current point (re-click pending)
    scale      = [1.0]    # display-only downscale to fit MAX_DISPLAY_H; <=1.0
    fit_dims   = [None]   # (fit_w, fit_h), fixed for this image
    zoom       = [1.0]    # additional zoom factor; 1.0 = fit-screen
    pan_x      = [0.0]    # viewport top-left x in fit-canvas coords
    pan_y      = [0.0]    # viewport top-left y in fit-canvas coords
    is_panning = [False]
    drag_start = [None]   # (mx, my, pan_x0, pan_y0) captured on right-button down

    WIN = f"Vertical Line Labeller - {cam}"
    cv2.namedWindow(WIN, cv2.WINDOW_AUTOSIZE)

    def clamp_pan():
        """Keep viewport within fit-canvas bounds."""
        fw, fh = fit_dims[0]
        pan_x[0] = max(0.0, min(pan_x[0], fw - fw / zoom[0]))
        pan_y[0] = max(0.0, min(pan_y[0], fh - fh / zoom[0]))

    def refresh():
        canvas = build_canvas(img, points, point_ids, idx[0], live_click, redo_flag)

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
        elif zoom[0] < 1.0:
            # Nothing to crop when zoomed out past fit-screen - shrink the whole
            # canvas instead and letterbox it into the top-left of the window
            # (top-left, not centred, so the existing x/zoom + pan_x inversion
            # in on_mouse stays valid unchanged - pan is clamped to 0 here anyway).
            small_w = int(round(fw * zoom[0]))
            small_h = int(round(fh * zoom[0]))
            small = cv2.resize(fit, (small_w, small_h), interpolation=cv2.INTER_AREA)
            disp = cv2.copyMakeBorder(
                small, 0, fh - small_h, 0, fw - small_w,
                cv2.BORDER_CONSTANT, value=LETTERBOX_COLOR)
        else:
            disp = fit.copy()

        draw_banner(disp, banner_text(cam, idx[0], point_ids, zoom[0]))
        cv2.imshow(WIN, disp)

    def load_point(i: int):
        """Move to point i: clear pending click, render, update title."""
        idx[0]       = i
        live_click[0] = None
        redo_flag[0] = False
        refresh()
        set_title(WIN, cam, idx[0], point_ids, points, zoom[0])

    def on_mouse(event, x, y, flags, param):
        """Handle left-click (place), scroll wheel (zoom), right-drag (pan)."""

        if event == cv2.EVENT_LBUTTONDOWN:
            # Convert window -> fit canvas -> original image coords (no padding)
            fit_x  = x / zoom[0] + pan_x[0]
            fit_y  = y / zoom[0] + pan_y[0]
            orig_x = int(round(fit_x / scale[0]))
            orig_y = int(round(fit_y / scale[0]))
            live_click[0] = (float(orig_x), float(orig_y))
            redo_flag[0] = False
            refresh()

        elif event == cv2.EVENT_MOUSEWHEEL:
            factor = ZOOM_STEP if flags > 0 else 1.0 / ZOOM_STEP
            new_z  = max(ZOOM_MIN, min(zoom[0] * factor, ZOOM_MAX))
            # keep the pixel under the cursor fixed in fit-canvas space
            cx = x / zoom[0] + pan_x[0]
            cy = y / zoom[0] + pan_y[0]
            zoom[0]  = new_z
            pan_x[0] = cx - x / zoom[0]
            pan_y[0] = cy - y / zoom[0]
            clamp_pan()
            refresh()
            set_title(WIN, cam, idx[0], point_ids, points, zoom[0])

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

    # Compute display scale and fit canvas size once (single static image)
    _ph, _pw = img.shape[0], img.shape[1]
    scale[0]    = min(1.0, MAX_DISPLAY_H / _ph)
    fit_dims[0] = (int(round(_pw * scale[0])), int(round(_ph * scale[0])))  # (w, h)

    load_point(idx[0])

    while True:
        key = cv2.waitKeyEx(50)
        if key == -1:
            continue

        cur_pid = point_ids[idx[0]]

        if key in (ord("q"), 27):                        # ---- quit
            break

        elif key in (KEY_LEFT_WIN, KEY_LEFT_LIN):        # ---- navigate to previous point
            if idx[0] > 0:
                load_point(idx[0] - 1)

        elif key in (KEY_RIGHT_WIN, KEY_RIGHT_LIN):      # ---- navigate to next point
            if idx[0] < len(point_ids) - 1:
                load_point(idx[0] + 1)

        elif key == ord("z"):                             # ---- reset zoom
            zoom[0]  = 1.0
            pan_x[0] = 0.0
            pan_y[0] = 0.0
            refresh()
            set_title(WIN, cam, idx[0], point_ids, points, zoom[0])

        elif key in (KEY_DEL_WIN, KEY_DEL_ASCII, ord("r")):  # ---- redo / clear
            if live_click[0] is not None:
                live_click[0] = None
                redo_flag[0] = False
            elif cur_pid in points:
                redo_flag[0] = True
            refresh()
            set_title(WIN, cam, idx[0], point_ids, points, zoom[0])

        elif key in (ord("s"), 13):                       # ---- accept  (s or Enter)
            if live_click[0] is None:
                print(f"{cur_pid}: click a point before accepting")
                continue
            points[cur_pid] = live_click[0]
            save_csv(csv_path, points, point_ids)
            u, v = points[cur_pid]
            print(f"{cur_pid}: saved (u={u:.1f}, v={v:.1f})")

            if idx[0] < len(point_ids) - 1:
                load_point(idx[0] + 1)
            else:
                live_click[0] = None
                redo_flag[0] = False
                refresh()
                set_title(WIN, cam, idx[0], point_ids, points, zoom[0])

    cv2.destroyAllWindows()
    print_summary(points, point_ids)


if __name__ == "__main__":
    main()
