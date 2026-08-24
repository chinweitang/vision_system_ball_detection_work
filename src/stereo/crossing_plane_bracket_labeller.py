# crossing_plane_bracket_labeller.py
#
# claude/prompts (see worklog for the driving prompt text). Manual
# crossing-bracket labelling for the 20 v2 candidate flights
# (results/prediction/02_candidate_reselection/ranked_candidates_v2.csv):
# for each flight, per camera, serve N_BRACKET=6 frames at STRIDE=2,
# symmetric about the plane-crossing frame (3 before, crossing, 2 after),
# for manual 2-click centroid labelling. These labels are INDEPENDENT
# ground truth (position + local-fit velocity, computed in a LATER task) to
# validate the Model-C arc fit -- so the labels themselves must be pure
# manual clicks, never fit-derived.
#
# Click/zoom/pan/save mechanics ADAPTED (not imported) from
# src/image_processing/03_manual_centroid_labelling/03_label_final_points.py,
# which itself documents this as the established pattern for this project's
# labelling tools (that script's own header: "not imported -- that script's
# GUI logic lives entirely in closures inside main(), not structured as
# importable functions"). Same 2-click -> centroid+diameter methodology,
# same queue-driven navigation idea, generalized from "1 target per
# (session,flight,cam)" to "6 targets per (session,flight,cam)".
#
# IMPORTANT DEVIATION FLAGGED FOR REVIEW: the driving prompt assumed
# "existing per-flight crossing info" (from 01_crossing_plane_setup) already
# includes a crossing TIME/FRAME. It doesn't -- crossing_classification.csv
# only stored crossing_Y/Z/speed/velocity, not t_cross or a frame index.
# classify_flight() in crossing_plane_classification.py DOES compute
# t_cross internally and already returns it (just wasn't persisted to CSV).
# Per the prompt's own explicit fallback ("if only the arc-fit crossing
# time exists, map it to the nearest real observed frame"), this script
# reuses classify_flight() (same frozen fit, same seed, same pooled_k -- not
# a new/different fit) for JUST these 20 flights, purely to recover t_cross
# and locate the nearest real observed frame pair. This is bookkeeping to
# pick WHICH frames to serve, not part of the label data itself -- the
# u_px/v_px written to crossing_labels.csv are always fresh manual clicks,
# never derived from the fit. Does not touch 01_'s CSV or re-run its
# 163-flight batch. Logged here and in the worklog for visibility.

import csv
import math
import sys
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.stereo.all_flights_common import load_session_calib, find_flight_dir, SESSIONS  # noqa: E402
from src.stereo.pixel_velocity_correction import build_corrected_pairs  # noqa: E402
from src.stereo.crossing_plane_classification import (  # noqa: E402
    build_geometry, load_pooled_k, classify_flight, TAPE_REGISTRATIONS,
)

CANDIDATES_CSV = REPO_ROOT / "results" / "prediction" / "02_candidate_reselection" / "ranked_candidates_v2.csv"
OUT_DIR = REPO_ROOT / "results" / "prediction" / "03_crossing_labels"
OUT_CSV = OUT_DIR / "crossing_labels.csv"
MANIFEST_CSV = OUT_DIR / "labelling_manifest.csv"
LOG_PATH = REPO_ROOT / "claude" / "claude_logs" / "2026-08-04_1347_crossing_plane_setup_worklog.md"

N_BRACKET = 6
STRIDE = 2
N_BEFORE = 3  # -> 3 before, crossing, 2 after (closest to centred for an even count)
N_AFTER = N_BRACKET - N_BEFORE - 1

CSV_FIELDS = ["registration", "flight_id", "camera", "frame_index", "frame_timestamp_ms",
              "is_crossing_frame", "u_px", "v_px", "stride", "bracket_span_ms"]
MANIFEST_FIELDS = ["flight_id", "n_points_labelled", "bracket_symmetric", "flagged_for_review"]

MAX_DISPLAY_H = 900
ZOOM_STEP = 1.25
ZOOM_MAX = 10.0

KEY_LEFT_WIN, KEY_RIGHT_WIN = 2424832, 2555904
KEY_LEFT_LIN, KEY_RIGHT_LIN = 65361, 65363
KEY_DEL_WIN, KEY_DEL_ASCII = 3014656, 127


def log_append(msg: str) -> None:
    with open(LOG_PATH, "a") as f:
        f.write(f"{msg}\n")


# ---- bracket resolution ------------------------------------------------------

def load_candidates() -> list:
    with open(CANDIDATES_CSV, newline="") as f:
        return list(csv.DictReader(f))


def resolve_pairs(session: str, flight_id: str, K0, D0, K1, D1) -> list:
    """Same frozen build_corrected_pairs() call build_corrected_track() makes
    internally, but kept as full pair dicts (cam0_frame AND cam1_frame) --
    build_corrected_track only exposes cam0_frame via frame_labels."""
    flight_dir = find_flight_dir(session, flight_id)
    ts_csv = flight_dir / "timestamps.csv"
    cfg = SESSIONS[session]
    cam0_csv = cfg["detections_dir"] / f"{flight_id}_cam0_detections.csv"
    cam1_csv = cfg["detections_dir"] / f"{flight_id}_cam1_detections.csv"
    pairs = build_corrected_pairs(cam0_csv, cam1_csv, ts_csv)
    pairs = sorted(pairs, key=lambda p: (p["t0_ns"] + p["t1_ns"]) / 2.0)
    return pairs, flight_dir


def build_bracket_indices(idx_cross: int, n_pairs: int):
    """Returns (indices, symmetric: bool). Tries the full [-N_BEFORE, N_AFTER]
    span at STRIDE; if that runs off either end, shrinks to the widest
    symmetric-as-possible span that fits and reports symmetric=False."""
    offsets = list(range(-N_BEFORE, N_AFTER + 1))
    idxs = [idx_cross + o * STRIDE for o in offsets]
    if all(0 <= i < n_pairs for i in idxs):
        return idxs, True

    max_before = idx_cross // STRIDE
    max_after = (n_pairs - 1 - idx_cross) // STRIDE
    lo = min(N_BEFORE, max_before)
    hi = min(N_AFTER, max_after)
    offsets = list(range(-lo, hi + 1))
    idxs = [idx_cross + o * STRIDE for o in offsets]
    return idxs, False


def frame_path(flight_dir: Path, cam: str, frame_no: int) -> Path:
    """The per-flight cam dir itself is a SPARSE subset (context frames
    across the whole capture) -- the actual flight-duration frames (what
    detection/triangulation runs against) live in the ball_in_frame/
    subfolder, same convention 03_label_final_points.py already uses.
    Check that first, fall back to the bare cam dir."""
    for base in (flight_dir / cam / "ball_in_frame", flight_dir / cam):
        p = base / f"frame_{frame_no:03d}.png"
        if p.is_file():
            return p
        matches = list(base.glob(f"frame_*{frame_no}.png"))
        if matches:
            return matches[0]
    raise FileNotFoundError(f"No frame image for {cam} frame {frame_no} under {flight_dir / cam} "
                            f"(checked ball_in_frame/ and bare cam dir)")


def build_flight_bracket(row: dict, geometries: dict, pooled_k: float) -> dict:
    session, flight_id, reg_key = row["session"], row["flight_id"], row["registration"]
    geo = geometries[reg_key]
    K0, D0, K1, D1, P0, P1 = load_session_calib(session)

    result = classify_flight(session, flight_id, geo, K0, D0, K1, D1, P0, P1, pooled_k)
    if result["status"] != "ok" or "t_cross" not in result:
        return dict(status="skipped", reason=f"re-fit did not yield a crossing: {result.get('reason', result)}")
    t_cross = result["t_cross"]

    pairs, flight_dir = resolve_pairs(session, flight_id, K0, D0, K1, D1)
    t_avg = np.array([(p["t0_ns"] + p["t1_ns"]) / 2.0 for p in pairs])
    t_sec = (t_avg - t_avg[0]) / 1e9
    idx_cross = int(np.argmin(np.abs(t_sec - t_cross)))

    idxs, symmetric = build_bracket_indices(idx_cross, len(pairs))
    bracket_pairs = [pairs[i] for i in idxs]
    span_ms = (t_sec[idxs[-1]] - t_sec[idxs[0]]) * 1000.0

    return dict(status="ok", flight_dir=flight_dir, t_cross=t_cross, idx_cross=idx_cross,
                idxs=idxs, bracket_pairs=bracket_pairs, t_sec=t_sec, symmetric=symmetric,
                span_ms=span_ms)


# ---- GUI (adapted from 03_label_final_points.py) -----------------------------

def build_targets(candidates: list, geometries: dict, pooled_k: float) -> tuple:
    targets = []
    flagged = []
    for row in candidates:
        session, flight_id, reg_key = row["session"], row["flight_id"], row["registration"]
        b = build_flight_bracket(row, geometries, pooled_k)
        if b["status"] != "ok":
            log_append(f"- [{ts()}] SKIP {flight_id}: {b['reason']}")
            flagged.append((flight_id, "resolution failed"))
            continue

        if not b["symmetric"]:
            flagged.append((flight_id, f"asymmetric bracket ({len(b['idxs'])} frames, not full {N_BRACKET})"))

        log_append(f"- [{ts()}] {flight_id} ({reg_key}): t_cross={b['t_cross']:.4f}s, "
                   f"idx_cross={b['idx_cross']}/{len(b['idxs']) and len(b['bracket_pairs'])}, "
                   f"bracket_pair_indices={b['idxs']}, symmetric={b['symmetric']}, "
                   f"span={b['span_ms']:.1f}ms")

        for cam, frame_key in (("cam0", "cam0_frame"), ("cam1", "cam1_frame")):
            t_key = "t0_ns" if cam == "cam0" else "t1_ns"
            frame_nos = [p[frame_key] for p in b["bracket_pairs"]]
            ts_ms = [b["t_sec"][i] * 1000.0 for i in b["idxs"]]
            log_append(f"    {cam}: frames={frame_nos}  timestamps_ms={[f'{t:.1f}' for t in ts_ms]}")

            for pos, (idx, p) in enumerate(zip(b["idxs"], b["bracket_pairs"])):
                fn = p[frame_key]
                try:
                    img_path = frame_path(b["flight_dir"], cam, fn)
                except FileNotFoundError as e:
                    log_append(f"    *** {cam} frame {fn}: {e} -- skipped ***")
                    continue
                targets.append(dict(
                    registration=reg_key, flight_id=flight_id, camera=cam,
                    frame_index=fn, frame_timestamp_ms=b["t_sec"][idx] * 1000.0,
                    is_crossing_frame=(idx == b["idx_cross"]), img_path=img_path,
                    stride=STRIDE, bracket_span_ms=b["span_ms"],
                ))

    return targets, flagged


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def load_labels(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, newline="") as f:
        out = {}
        for r in csv.DictReader(f):
            key = (r["registration"], r["flight_id"], r["camera"], r["frame_index"])
            out[key] = r
        return out


def save_labels(path: Path, labels: dict, targets: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    order = [(t["registration"], t["flight_id"], t["camera"], str(t["frame_index"])) for t in targets]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for key in order:
            if key in labels:
                w.writerow(labels[key])


def target_key(t):
    return (t["registration"], t["flight_id"], t["camera"], str(t["frame_index"]))


def make_row(t, c1, c2) -> dict:
    cx = (c1[0] + c2[0]) / 2.0
    cy = (c1[1] + c2[1]) / 2.0
    return {
        "registration": t["registration"], "flight_id": t["flight_id"], "camera": t["camera"],
        "frame_index": t["frame_index"], "frame_timestamp_ms": f"{t['frame_timestamp_ms']:.2f}",
        "is_crossing_frame": t["is_crossing_frame"], "u_px": f"{cx:.2f}", "v_px": f"{cy:.2f}",
        "stride": t["stride"], "bracket_span_ms": f"{t['bracket_span_ms']:.1f}",
    }


def write_manifest(targets: list, labels: dict, flagged: list) -> None:
    flagged_ids = {fid for fid, _ in flagged}
    by_flight = {}
    for t in targets:
        by_flight.setdefault(t["flight_id"], []).append(t)

    rows = []
    for flight_id, flight_targets in by_flight.items():
        n_labelled = sum(1 for t in flight_targets if target_key(t) in labels)
        rows.append(dict(
            flight_id=flight_id, n_points_labelled=n_labelled,
            bracket_symmetric=flight_id not in {f for f, r in flagged if "asymmetric" in r},
            flagged_for_review=flight_id in flagged_ids,
        ))
    with open(MANIFEST_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        w.writeheader()
        w.writerows(rows)


def _to_pad(x, y, pad):
    return int(round(x)) + pad, int(round(y)) + pad


def _crosshair(canvas, cx, cy, color, size=8):
    cv2.line(canvas, (cx - size, cy), (cx + size, cy), color, 1)
    cv2.line(canvas, (cx, cy - size), (cx, cy + size), color, 1)


def draw_stored_overlay(canvas, row, pad, raw_clicks=None):
    if not row.get("u_px"):
        return
    cx, cy = _to_pad(float(row["u_px"]), float(row["v_px"]), pad)
    if raw_clicks is not None:
        # crossing_labels.csv only stores the centroid (per the requested
        # schema), not the 2 raw clicks/diameter -- so the ball-outline
        # circle can only be redrawn for points saved THIS session (kept
        # in-memory, not persisted). A resumed session shows crosshair-only
        # for points saved in an earlier run.
        c1, c2 = raw_clicks
        p1, p2 = _to_pad(*c1, pad), _to_pad(*c2, pad)
        r = max(1, int(math.hypot(c2[0] - c1[0], c2[1] - c1[1]) / 2))
        cv2.circle(canvas, p1, 4, (255, 255, 255), -1)
        cv2.circle(canvas, p2, 4, (255, 255, 255), -1)
        cv2.circle(canvas, (cx, cy), r, (0, 255, 0), 1)
    _crosshair(canvas, cx, cy, (0, 255, 255))


def draw_live_clicks(canvas, clicks, pad):
    for x, y in clicks:
        cv2.circle(canvas, _to_pad(x, y, pad), 4, (255, 255, 255), -1)
    if len(clicks) == 2:
        c1, c2 = clicks
        cx, cy = (c1[0] + c2[0]) / 2.0, (c1[1] + c2[1]) / 2.0
        r = max(1, int(math.hypot(c2[0] - c1[0], c2[1] - c1[1]) / 2))
        pcx, pcy = _to_pad(cx, cy, pad)
        _crosshair(canvas, pcx, pcy, (0, 255, 255))
        cv2.circle(canvas, (pcx, pcy), r, (0, 255, 0), 1)


def build_canvas(img_gray, pad, clicks, stored_row, redo_mode, raw_clicks=None):
    padded = cv2.copyMakeBorder(img_gray, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    canvas = cv2.cvtColor(padded, cv2.COLOR_GRAY2BGR)
    if stored_row is not None and not clicks and not redo_mode:
        draw_stored_overlay(canvas, stored_row, pad, raw_clicks)
    if clicks:
        draw_live_clicks(canvas, clicks, pad)
    return canvas


def run_gui(targets: list, labels: dict) -> None:
    pos = [0]
    clicks = []
    redo_flag = [False]
    raw_clicks_cache = {}  # target_key -> (c1, c2), this-session-only (not persisted)
    img_cache = [None]
    scale = [1.0]
    fit_dims = [None]
    zoom = [1.0]
    pan_x = [0.0]
    pan_y = [0.0]
    is_panning = [False]
    drag_start = [None]

    start = next((i for i, t in enumerate(targets) if target_key(t) not in labels), 0)
    pos[0] = start

    WIN = "Crossing-Bracket Labeller"
    cv2.namedWindow(WIN, cv2.WINDOW_AUTOSIZE)

    def clamp_pan():
        fw, fh = fit_dims[0]
        pan_x[0] = max(0.0, min(pan_x[0], fw - fw / zoom[0]))
        pan_y[0] = max(0.0, min(pan_y[0], fh - fh / zoom[0]))

    def refresh():
        t = targets[pos[0]]
        stored_row = labels.get(target_key(t))
        raw_clicks = raw_clicks_cache.get(target_key(t))
        canvas = build_canvas(img_cache[0], 50, clicks, stored_row, redo_flag[0], raw_clicks)
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
        key = target_key(t)
        status = "LABELLED" if key in labels else "unlabelled"
        cross = " *CROSSING*" if t["is_crossing_frame"] else ""
        cv2.setWindowTitle(
            WIN,
            f"[{pos[0] + 1}/{len(targets)}] {t['flight_id']} {t['camera']} "
            f"frame_{t['frame_index']}{cross}  {status}  {zoom[0]:.1f}x | "
            "[s/Enter]=save [<- ->]=prev/next [z]=reset-zoom [q/Esc]=quit",
        )

    def load_target(i: int):
        clicks.clear()
        redo_flag[0] = False
        pos[0] = i
        t = targets[i]
        img_cache[0] = cv2.imread(str(t["img_path"]), cv2.IMREAD_GRAYSCALE)
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

    _peek = cv2.imread(str(targets[start]["img_path"]), cv2.IMREAD_GRAYSCALE)
    _ph, _pw = _peek.shape[0] + 100, _peek.shape[1] + 100
    scale[0] = min(1.0, MAX_DISPLAY_H / _ph)
    fit_dims[0] = (int(round(_pw * scale[0])), int(round(_ph * scale[0])))

    load_target(pos[0])
    last_flight = targets[pos[0]]["flight_id"]

    while True:
        key = cv2.waitKeyEx(50)
        if key == -1:
            continue
        t = targets[pos[0]]

        if key in (ord("q"), 27):
            log_append(f"- [{ts()}] Quit. {len(labels)}/{len(targets)} points labelled overall.")
            break
        elif key in (KEY_LEFT_WIN, KEY_LEFT_LIN):
            if pos[0] > 0:
                load_target(pos[0] - 1)
        elif key in (KEY_RIGHT_WIN, KEY_RIGHT_LIN):
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
        elif key in (ord("s"), 13):
            if len(clicks) != 2:
                print(f"need 2 clicks before saving (have {len(clicks)})")
                continue
            c1 = (float(clicks[0][0]), float(clicks[0][1]))
            c2 = (float(clicks[1][0]), float(clicks[1][1]))
            row = make_row(t, c1, c2)
            labels[target_key(t)] = row
            raw_clicks_cache[target_key(t)] = (c1, c2)
            save_labels(OUT_CSV, labels, targets)
            print(f"{t['flight_id']}/{t['camera']}/frame_{t['frame_index']}: saved ({row['u_px']}, {row['v_px']})")

            if t["flight_id"] != last_flight:
                log_append(f"- [{ts()}] Finished flight {last_flight} (moved on to {t['flight_id']}).")
                last_flight = t["flight_id"]

            if pos[0] < len(targets) - 1:
                load_target(pos[0] + 1)
            else:
                set_title()

    cv2.destroyAllWindows()


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log_append("")
    log_append("## Crossing-bracket labelling")
    log_append(f"- [{ts()}] IMPORTANT: 01_'s crossing_classification.csv did not persist a crossing "
               f"time/frame -- reusing classify_flight() (same frozen fit, same seed/pooled_k) for "
               f"just these 20 flights to recover t_cross, per the prompt's own explicit fallback. "
               f"Not touching 01_'s CSV or re-running its 163-flight batch. Labels themselves remain "
               f"pure manual clicks.")

    candidates = load_candidates()
    log_append(f"- [{ts()}] Loaded {len(candidates)} candidate flights from ranked_candidates_v2.csv.")

    pooled_k = load_pooled_k()
    geometries = {reg_key: build_geometry(reg_key, cfg) for reg_key, cfg in TAPE_REGISTRATIONS.items()}

    targets, flagged = build_targets(candidates, geometries, pooled_k)
    log_append(f"- [{ts()}] Built {len(targets)} label targets "
               f"({len(candidates)} flights x 2 cams x up to {N_BRACKET} frames = "
               f"{len(candidates) * 2 * N_BRACKET} max).")
    if flagged:
        log_append(f"- [{ts()}] FLAGGED FOR REVIEW ({len(flagged)}): " +
                   "; ".join(f"{fid} ({reason})" for fid, reason in flagged))
    if len(flagged) > 3:
        log_append(f"- [{ts()}] *** STOP CONDITION: >3 flights flagged ({len(flagged)}) -- "
                   f"crossing-frame resolution may be off, report before continuing. ***")
        print(f"*** {len(flagged)} flights flagged for review -- STOPPING per instructions. "
              f"See log for details. ***")
        for fid, reason in flagged:
            print(f"  {fid}: {reason}")
        return

    labels = load_labels(OUT_CSV)
    print(f"{len(targets)} targets queued, {len(labels)} already labelled. Launching GUI...")
    run_gui(targets, labels)

    write_manifest(targets, labels, flagged)
    n_total_labelled = sum(1 for t in targets if target_key(t) in labels)
    log_append(f"- [{ts()}] Session end: {n_total_labelled}/{len(targets)} points labelled. "
               f"Manifest written to {MANIFEST_CSV}")
    print(f"Manifest written to {MANIFEST_CSV}")
    print(f"Labels written to {OUT_CSV} ({n_total_labelled}/{len(targets)})")


if __name__ == "__main__":
    main()
