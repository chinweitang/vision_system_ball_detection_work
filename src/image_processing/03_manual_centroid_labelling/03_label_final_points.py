# 03_label_final_points.py
#
# Manual "final point" labelling: click ONE true ball centroid per
# (session, flight, cam), at the last frame within the detector's valid
# stride-margin range (or a nearby frame the user picks instead if that
# default frame is ambiguous). These held-out labelled points support an
# upcoming gravity-only vs gravity+drag trajectory model comparison
# (context.md SS5): fit each model on early detector points, predict
# forward, score against this label -- a genuine prediction target, never a
# point used in any fit.
#
# Target queue: reuses (does not re-derive) two already-verified pieces of
# logic -- flight_velocity_angle_binner.py's SESSIONS/find_flight_ids
# (flight eligibility = has a tuned-detections CSV under
# data/detector_tuning/detections/<stage>/<session>/) and
# 11_generate_detections_csv.py's find_flight_dirs (raw ball_in_frame
# folder resolution -- handles 2026_07_15_gym's nested subfolders, e.g.
# "2 ball contacts ground before plane/flight_01", and the cross-session
# flight-number collision, e.g. both sessions have a flight_60). Both
# source files are digit-prefixed filenames and can't be `import`ed by
# name -- find_flight_dirs is loaded via importlib.util (genuine reuse of
# the real function, not a copy); flight_velocity_angle_binner.py imports
# normally.
#
# Click/zoom/pan/save/no-ball mechanics are ADAPTED from 01_label_frames.py
# (not imported -- that script's GUI logic lives entirely in closures
# inside main(), not structured as importable functions). Queue-driven
# navigation (visit an ordered list of specific targets, not every frame in
# a folder) is adapted from 02_label_frames_human_error.py's repeat-queue
# pattern. Neither existing script is modified.
#
# Output: data/final_point_labels/final_point_labels.csv (session, flight,
# cam, frame_number, click1_x, click1_y, click2_x, click2_y, centroid_x,
# centroid_y, diameter_px). Full-rewrite-per-save, same "crash-safe by
# always being a complete file" technique as 01_label_frames.py -- resumes
# from the first unlabelled target in queue order on restart.
#
# Usage:
#   python 03_label_final_points.py
#
# Keys:
#   s / Enter    save current 2 clicks for this target, advance to next
#   n            no ball visible at this frame -- save empty row, advance
#   <- ->        move the CANDIDATE FRAME a few steps within this target's
#                clamped valid window (does NOT change queue position --
#                still labelling the same (session,flight,cam) target, just
#                trying a different nearby frame if the default is
#                ambiguous to click confidently)
#   [ / ]        move to the PREVIOUS / NEXT target in the queue (review or
#                redo an earlier one, or preview/skip ahead) -- does not
#                save anything by itself
#   z / 0        reset zoom to fit-screen
#   q / Esc      quit (progress already saved after each label; resumes
#                from the first unlabelled target next run)
# Mouse:
#   left-click     place click point (2 needed per label)
#   scroll wheel   zoom in / out, centred on cursor
#   right-click drag pan

import csv
import importlib.util
import math
import re
import sys
import json
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

from src.stereo.flight_velocity_angle_binner import SESSIONS, find_flight_ids, flight_sort_key  # noqa: E402
from src.stereo.stereo_flight_sync_table import load_timestamps, nearest_index  # noqa: E402
from src.stereo.pixel_velocity_correction import DEFAULT_MAX_PAIR_GAP_MS  # noqa: E402

DETECTOR_DIR = ROOT / "src" / "image_processing" / "02_adjacent_frame_differencing"
_spec = importlib.util.spec_from_file_location(
    "gen_detections_csv", DETECTOR_DIR / "11_generate_detections_csv.py")
_gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gen)
find_flight_dirs = _gen.find_flight_dirs

CONFIG_PATH = ROOT / "data/detector_tuning/candidate_config.json"
RAW_SESSION_DIRS = {
    "2026_07_21_gym": ROOT / "data/2026_07_21_gym/ball_flights",
    "2026_07_15_gym": ROOT / "data/2026_07_15_gym/ball_flights",
}
CAMS = ["cam0", "cam1"]

OUT_DIR = ROOT / "data/final_point_labels"
OUT_CSV = OUT_DIR / "final_point_labels.csv"

MAX_DISPLAY_H = 900
ZOOM_STEP = 1.25
ZOOM_MAX = 10.0
NAV_MARGIN = 8  # "a handful of frames" either side of the default target index

KEY_LEFT_WIN, KEY_RIGHT_WIN = 2424832, 2555904
KEY_LEFT_LIN, KEY_RIGHT_LIN = 65361, 65363
KEY_DEL_WIN, KEY_DEL_ASCII = 3014656, 127

CSV_FIELDS = ["session", "flight", "cam", "frame_number",
              "click1_x", "click1_y", "click2_x", "click2_y",
              "centroid_x", "centroid_y", "diameter_px"]


# ---- target queue -----------------------------------------------------------

def frame_num(path: Path) -> int:
    m = re.search(r"(\d+)", path.stem)
    return int(m.group(1)) if m else 0


def select_paired_target(frame_paths0, valid_lo0, valid_hi0, ts0,
                          fn1_by_time, times1_sorted):
    """Find the LATEST cam0 valid-range frame that has a cam1 partner (from
    cam1's OWN valid range) within DEFAULT_MAX_PAIR_GAP_MS of real time.
    Starts at cam0's own last valid frame (idx=valid_hi0) and steps
    backward through cam0's valid range until tolerance is met.

    Returns (idx0, cam0_fn, cam1_fn, dt_ms, steps_back) or None if no cam0
    frame in the whole valid range has a partner within tolerance."""
    for steps_back, idx0 in enumerate(range(valid_hi0, valid_lo0 - 1, -1)):
        cam0_fn = frame_num(frame_paths0[idx0])
        if cam0_fn not in ts0:
            continue  # frame has no timestamps.csv entry -- shouldn't happen, skip defensively
        t0 = ts0[cam0_fn]
        nearest_i = nearest_index(times1_sorted, t0)
        cam1_fn = fn1_by_time[nearest_i]
        t1 = times1_sorted[nearest_i]
        dt_ms = (t0 - t1) / 1e6
        if abs(dt_ms) <= DEFAULT_MAX_PAIR_GAP_MS:
            return idx0, cam0_fn, cam1_fn, dt_ms, steps_back
    return None


def build_target_queue() -> list:
    """One target per (session, flight, cam) with a tuned-detections CSV.
    cam0's and cam1's target frame are NOT chosen independently -- they're
    a real-time-paired (cam0_fn, cam1_fn) selected together via
    select_paired_target() so the "final point" labelled in each camera
    actually corresponds to (within DEFAULT_MAX_PAIR_GAP_MS) the same real
    instant, not just the same coincidental frame_number. Each target still
    carries its own camera's full candidate-frame list and valid
    stride-margin index range, so nav (<- ->) can be clamped correctly."""
    config = json.load(open(CONFIG_PATH))
    stride = config["stride"]

    targets = []
    pairing_stats = {"steps_back": [], "unpaired_flights": []}

    for session, cfg in SESSIONS.items():
        eligible_ids = set(find_flight_ids(cfg["detections_dir"]))
        raw_dirs = dict(find_flight_dirs(RAW_SESSION_DIRS[session]))

        missing_raw = eligible_ids - set(raw_dirs)
        if missing_raw:
            print(f"WARNING [{session}]: {len(missing_raw)} flight(s) have a tuned-detections "
                  f"CSV but no raw ball_in_frame dir: {sorted(missing_raw, key=flight_sort_key)}")

        for flight_id in sorted(eligible_ids, key=flight_sort_key):
            flight_dir = raw_dirs.get(flight_id)
            if flight_dir is None:
                continue

            cam_paths = {}
            cam_valid = {}
            ok = True
            for cam in CAMS:
                cam_dir = flight_dir / cam / "ball_in_frame"
                frame_paths = sorted(cam_dir.glob("frame_*.png"), key=frame_num)
                if len(frame_paths) <= 2 * stride:
                    print(f"WARNING [{session}/{flight_id}/{cam}]: only {len(frame_paths)} raw "
                          f"frames, not enough for stride={stride} margin -- SKIPPED")
                    ok = False
                    continue
                cam_paths[cam] = frame_paths
                cam_valid[cam] = (stride, len(frame_paths) - stride - 1)
            if not ok or len(cam_paths) < 2:
                continue

            timestamps_csv = flight_dir / "timestamps.csv"
            if not timestamps_csv.is_file():
                print(f"WARNING [{session}/{flight_id}]: no timestamps.csv -- SKIPPED (both cams)")
                continue
            cam0_entries, cam1_entries = load_timestamps(timestamps_csv)
            ts0 = {f: t for f, t in cam0_entries}
            ts1 = {f: t for f, t in cam1_entries}

            # cam1 candidates restricted to cam1's OWN valid range, sorted by time (for nearest_index)
            lo1, hi1 = cam_valid["cam1"]
            valid1_fns = [frame_num(cam_paths["cam1"][i]) for i in range(lo1, hi1 + 1)]
            valid1_pairs = sorted(((ts1[fn], fn) for fn in valid1_fns if fn in ts1))
            if not valid1_pairs:
                print(f"WARNING [{session}/{flight_id}]: no cam1 valid-range frame has a "
                      f"timestamps.csv entry -- SKIPPED (both cams)")
                continue
            times1_sorted = [t for t, fn in valid1_pairs]
            fn1_by_time = [fn for t, fn in valid1_pairs]

            lo0, hi0 = cam_valid["cam0"]
            result = select_paired_target(cam_paths["cam0"], lo0, hi0, ts0,
                                           fn1_by_time, times1_sorted)
            if result is None:
                print(f"*** UNEXPECTED: [{session}/{flight_id}] no cam0 frame in the entire "
                      f"valid range [{lo0},{hi0}] has a cam1 partner within "
                      f"{DEFAULT_MAX_PAIR_GAP_MS} ms -- SKIPPED, needs investigation ***")
                pairing_stats["unpaired_flights"].append((session, flight_id))
                continue

            idx0, cam0_fn, cam1_fn, dt_ms, steps_back = result
            pairing_stats["steps_back"].append((session, flight_id, steps_back, dt_ms))

            idx1_by_fn = {frame_num(p): i for i, p in enumerate(cam_paths["cam1"])}
            idx1 = idx1_by_fn[cam1_fn]

            targets.append(dict(session=session, flight=flight_id, cam="cam0",
                                 frame_paths=cam_paths["cam0"], valid_lo=lo0, valid_hi=hi0,
                                 default_idx=idx0))
            targets.append(dict(session=session, flight=flight_id, cam="cam1",
                                 frame_paths=cam_paths["cam1"], valid_lo=lo1, valid_hi=hi1,
                                 default_idx=idx1))

    build_target_queue.last_pairing_stats = pairing_stats
    return targets


# ---- CSV I/O ----------------------------------------------------------------

def load_labels(path: Path) -> dict:
    """{(session, flight, cam): row_dict}"""
    if not path.exists():
        return {}
    with open(path, newline="") as f:
        return {(r["session"], r["flight"], r["cam"]): r for r in csv.DictReader(f)}


def save_labels(path: Path, labels: dict, targets: list) -> None:
    """Full rewrite in queue order -- crash-safe (always a complete file),
    same technique as 01_label_frames.py's save_csv."""
    path.parent.mkdir(parents=True, exist_ok=True)
    order = [(t["session"], t["flight"], t["cam"]) for t in targets]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for key in order:
            if key in labels:
                w.writerow(labels[key])


def make_no_ball_row(session, flight, cam, fn) -> dict:
    row = {c: "" for c in CSV_FIELDS}
    row.update(session=session, flight=flight, cam=cam, frame_number=fn)
    return row


def make_row(session, flight, cam, fn, c1, c2) -> dict:
    cx = (c1[0] + c2[0]) / 2.0
    cy = (c1[1] + c2[1]) / 2.0
    diam = math.hypot(c2[0] - c1[0], c2[1] - c1[1])
    return {
        "session": session, "flight": flight, "cam": cam, "frame_number": fn,
        "click1_x": f"{c1[0]:.1f}", "click1_y": f"{c1[1]:.1f}",
        "click2_x": f"{c2[0]:.1f}", "click2_y": f"{c2[1]:.1f}",
        "centroid_x": f"{cx:.4f}", "centroid_y": f"{cy:.4f}",
        "diameter_px": f"{diam:.4f}",
    }


# ---- drawing (adapted from 01_label_frames.py) -------------------------------

def _to_pad(x, y, pad):
    return int(round(x)) + pad, int(round(y)) + pad


def _crosshair(canvas, cx, cy, color, size=8):
    cv2.line(canvas, (cx - size, cy), (cx + size, cy), color, 1)
    cv2.line(canvas, (cx, cy - size), (cx, cy + size), color, 1)


def draw_stored_overlay(canvas, row, pad):
    if not row.get("click1_x"):
        return
    c1x, c1y = _to_pad(float(row["click1_x"]), float(row["click1_y"]), pad)
    c2x, c2y = _to_pad(float(row["click2_x"]), float(row["click2_y"]), pad)
    cx, cy = _to_pad(float(row["centroid_x"]), float(row["centroid_y"]), pad)
    r = max(1, int(float(row["diameter_px"]) / 2))
    cv2.circle(canvas, (c1x, c1y), 4, (255, 255, 255), -1)
    cv2.circle(canvas, (c2x, c2y), 4, (255, 255, 255), -1)
    _crosshair(canvas, cx, cy, (0, 255, 255))
    cv2.circle(canvas, (cx, cy), r, (0, 255, 0), 1)


def draw_live_clicks(canvas, clicks, pad):
    for x, y in clicks:
        cv2.circle(canvas, _to_pad(x, y, pad), 4, (255, 255, 255), -1)
    if len(clicks) == 2:
        c1, c2 = clicks
        cx = (c1[0] + c2[0]) / 2.0
        cy = (c1[1] + c2[1]) / 2.0
        r = max(1, int(math.hypot(c2[0] - c1[0], c2[1] - c1[1]) / 2))
        pcx, pcy = _to_pad(cx, cy, pad)
        _crosshair(canvas, pcx, pcy, (0, 255, 255))
        cv2.circle(canvas, (pcx, pcy), r, (0, 255, 0), 1)


def build_canvas(img_gray, pad, clicks, stored_row, redo_mode):
    padded = cv2.copyMakeBorder(img_gray, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    canvas = cv2.cvtColor(padded, cv2.COLOR_GRAY2BGR)
    if stored_row is not None and not clicks and not redo_mode:
        draw_stored_overlay(canvas, stored_row, pad)
    if clicks:
        draw_live_clicks(canvas, clicks, pad)
    return canvas


# ---- main ---------------------------------------------------------------

def main():
    targets = build_target_queue()
    n21 = sum(1 for t in targets if t["session"] == "2026_07_21_gym")
    n15 = sum(1 for t in targets if t["session"] == "2026_07_15_gym")
    print(f"Target queue: {len(targets)} total ({n21} for 2026_07_21_gym, {n15} for 2026_07_15_gym)")

    labels = load_labels(OUT_CSV)
    print(f"Output CSV: {OUT_CSV}  ({len(labels)} target(s) already labelled)")

    def target_key(t):
        return (t["session"], t["flight"], t["cam"])

    start = next((i for i, t in enumerate(targets) if target_key(t) not in labels),
                 len(targets) - 1)

    pos = [start]
    frame_idx = [targets[start]["default_idx"]]
    clicks = []
    redo_flag = [False]
    img_cache = [None]
    scale = [1.0]
    fit_dims = [None]
    zoom = [1.0]
    pan_x = [0.0]
    pan_y = [0.0]
    is_panning = [False]
    drag_start = [None]

    WIN = "Final Point Labeller"
    cv2.namedWindow(WIN, cv2.WINDOW_AUTOSIZE)

    def clamp_pan():
        fw, fh = fit_dims[0]
        pan_x[0] = max(0.0, min(pan_x[0], fw - fw / zoom[0]))
        pan_y[0] = max(0.0, min(pan_y[0], fh - fh / zoom[0]))

    def refresh():
        t = targets[pos[0]]
        fn = frame_num(t["frame_paths"][frame_idx[0]])
        stored_row = labels.get(target_key(t))
        canvas = build_canvas(img_cache[0], 50, clicks, stored_row, redo_flag[0])

        if scale[0] < 1.0:
            fit = cv2.resize(canvas, None, fx=scale[0], fy=scale[0], interpolation=cv2.INTER_AREA)
        else:
            fit = canvas

        fw, fh = fit_dims[0]
        if zoom[0] > 1.0:
            vw, vh = fw / zoom[0], fh / zoom[0]
            x0 = int(round(max(0.0, min(pan_x[0], fw - vw))))
            y0 = int(round(max(0.0, min(pan_y[0], fh - vh))))
            x1, y1 = min(x0 + int(round(vw)), fw), min(y0 + int(round(vh)), fh)
            disp = cv2.resize(fit[y0:y1, x0:x1], (fw, fh), interpolation=cv2.INTER_NEAREST)
        else:
            disp = fit
        cv2.imshow(WIN, disp)

    def set_title():
        t = targets[pos[0]]
        fn = frame_num(t["frame_paths"][frame_idx[0]])
        key = target_key(t)
        status = "LABELLED" if key in labels else "unlabelled"
        cv2.setWindowTitle(
            WIN,
            f"[{pos[0] + 1}/{len(targets)}] {t['session']} {t['flight']} {t['cam']} "
            f"frame_{fn:03d}  {status}  {zoom[0]:.1f}x | "
            "[s/Enter]=save [n]=no-ball [<- ->]=try nearby frame [[ ]]=prev/next target "
            "[z]=reset-zoom [q/Esc]=quit",
        )

    def load_target(i: int, keep_frame_idx=False):
        clicks.clear()
        redo_flag[0] = False
        pos[0] = i
        t = targets[i]
        if not keep_frame_idx:
            frame_idx[0] = t["default_idx"]
        img_cache[0] = cv2.imread(str(t["frame_paths"][frame_idx[0]]), cv2.IMREAD_GRAYSCALE)
        refresh()
        set_title()

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(clicks) < 2:
            fit_x = x / zoom[0] + pan_x[0]
            fit_y = y / zoom[0] + pan_y[0]
            orig_x = int(round(fit_x / scale[0])) - 50
            orig_y = int(round(fit_y / scale[0])) - 50
            clicks.append((orig_x, orig_y))
            refresh()

        elif event == cv2.EVENT_MOUSEWHEEL:
            factor = ZOOM_STEP if flags > 0 else 1.0 / ZOOM_STEP
            new_z = max(1.0, min(zoom[0] * factor, ZOOM_MAX))
            cx = x / zoom[0] + pan_x[0]
            cy = y / zoom[0] + pan_y[0]
            zoom[0] = new_z
            pan_x[0] = cx - x / zoom[0]
            pan_y[0] = cy - y / zoom[0]
            clamp_pan()
            refresh()
            set_title()

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

    _peek = cv2.imread(str(targets[start]["frame_paths"][targets[start]["default_idx"]]),
                        cv2.IMREAD_GRAYSCALE)
    _ph, _pw = _peek.shape[0] + 100, _peek.shape[1] + 100
    scale[0] = min(1.0, MAX_DISPLAY_H / _ph)
    fit_dims[0] = (int(round(_pw * scale[0])), int(round(_ph * scale[0])))

    load_target(pos[0])

    while True:
        key = cv2.waitKeyEx(50)
        if key == -1:
            continue

        t = targets[pos[0]]
        fn = frame_num(t["frame_paths"][frame_idx[0]])

        if key in (ord("q"), 27):
            print("Quit.")
            break

        elif key in (KEY_LEFT_WIN, KEY_LEFT_LIN):
            nav_lo = max(t["valid_lo"], t["default_idx"] - NAV_MARGIN)
            if frame_idx[0] > nav_lo:
                frame_idx[0] -= 1
                load_target(pos[0], keep_frame_idx=True)

        elif key in (KEY_RIGHT_WIN, KEY_RIGHT_LIN):
            nav_hi = min(t["valid_hi"], t["default_idx"] + NAV_MARGIN)
            if frame_idx[0] < nav_hi:
                frame_idx[0] += 1
                load_target(pos[0], keep_frame_idx=True)

        elif key == ord("["):
            if pos[0] > 0:
                load_target(pos[0] - 1)

        elif key == ord("]"):
            if pos[0] < len(targets) - 1:
                load_target(pos[0] + 1)

        elif key in (ord("z"), ord("0")):
            zoom[0], pan_x[0], pan_y[0] = 1.0, 0.0, 0.0
            refresh()
            set_title()

        elif key in (KEY_DEL_WIN, KEY_DEL_ASCII):
            if clicks:
                clicks.clear()
                redo_flag[0] = False
            elif target_key(t) in labels:
                redo_flag[0] = True
            refresh()

        elif key == ord("n"):
            labels[target_key(t)] = make_no_ball_row(t["session"], t["flight"], t["cam"], fn)
            save_labels(OUT_CSV, labels, targets)
            print(f"{t['session']}/{t['flight']}/{t['cam']} frame_{fn:03d}: NO BALL")
            if pos[0] < len(targets) - 1:
                load_target(pos[0] + 1)
            else:
                set_title()

        elif key in (ord("s"), 13):
            if len(clicks) != 2:
                print(f"need 2 clicks before saving (have {len(clicks)})")
                continue
            c1 = (float(clicks[0][0]), float(clicks[0][1]))
            c2 = (float(clicks[1][0]), float(clicks[1][1]))
            row = make_row(t["session"], t["flight"], t["cam"], fn, c1, c2)
            labels[target_key(t)] = row
            save_labels(OUT_CSV, labels, targets)
            print(f"{t['session']}/{t['flight']}/{t['cam']} frame_{fn:03d}: "
                  f"diameter={float(row['diameter_px']):.1f}px")
            if pos[0] < len(targets) - 1:
                load_target(pos[0] + 1)
            else:
                set_title()

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
