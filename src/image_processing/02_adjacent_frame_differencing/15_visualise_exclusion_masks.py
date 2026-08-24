# 15_visualise_exclusion_masks.py
#
# Shows WHERE the final exclusion masks actually sit: every polygon in
# EXCLUSION_TRIANGLES drawn on the real scene, per camera, colour-coded by
# which tuning round put it there, plus a zoomed inset per box showing the
# physical object underneath it.
#
# Background image is the per-pixel MEDIAN over one flight's frames rather
# than a single frame: the masks exist to cover STATIC scene objects, so a
# median background shows exactly the thing being masked with the transient
# people/ball/hands removed. The source flight is named on the figure so the
# background is traceable.
#
# The provenance labels below are transcribed from exclusion_mask.py's own
# header comment (which round found each box and what object it is) - they are
# documentation of that file, so if a box is ever added/re-cut there, this
# table needs the matching edit. A length check at import time fails loudly if
# the two ever drift apart rather than silently mislabelling a box.
#
# Reads only ball_in_frame/*.png; writes only to
# results/detector_tuning/mask_overlays/.
#
# Run from anywhere:
#   python path/to/code/15_visualise_exclusion_masks.py

from pathlib import Path
import sys
import argparse

import numpy as np
import cv2

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO_ROOT))

from src.image_processing.exclusion_mask import EXCLUSION_TRIANGLES  # noqa: E402

SESSION = REPO_ROOT / "data" / "2026_07_21_gym" / "ball_flights"
BACKGROUND_FLIGHT = "flight_59"  # all three cam0 artifact types are active in this flight
OUT_DIR = REPO_ROOT / "results" / "detector_tuning" / "mask_overlays"

# (label, origin) per box, in EXCLUSION_TRIANGLES order. Origin drives the colour.
PROVENANCE = {
    "cam0": [
        ("ceiling light", "light"),
        ("wall corner / structural edge", "sweep"),
        ("exit sign", "audit2"),
        ("wall fixture / panel pair", "audit2"),
        ("small static cluster", "audit2"),
        # exclusion_mask.py names these two "exit sign, spillover to the right"
        # and "fixture's broader footprint". Checked the pixels under them on a
        # brightened median background before labelling: box 5 sits on the
        # pillar/corner edge just right of the sign, and box 6 on the banded
        # wall vent between the fixture and the sign - adjacent to the named
        # objects, not on them. Labelled positionally here so the figure does
        # not assert something the image does not show. The boxes themselves
        # are unchanged and still valid (they were sized from a dense
        # rejected-point sub-cluster and checked for zero real-detection
        # overlap); it is only the naming that was loose.
        ("spillover box, right of exit sign", "audit3"),
        ("spillover box, fixture-to-sign wall", "audit3"),
    ],
    "cam1": [
        ("ceiling light", "light"),
        ("wall corner / structural edge", "audit2"),
        ("wall corner - spillover", "audit3"),
        ("wall fixture / panel pair", "audit3"),
        ("exit sign", "audit3"),
    ],
}

ORIGIN_COLOR = {  # BGR
    "light": (60, 60, 255),     # red
    "sweep": (0, 165, 255),     # orange
    "audit2": (255, 220, 0),    # cyan
    "audit3": (80, 230, 80),    # green
}
ORIGIN_TEXT = {
    "light": "ceiling-light mask (pre-audit)",
    "sweep": "2026-07 param sweep (flight_126)",
    "audit2": "artifact audit round 2 (2026-07-23)",
    "audit3": "artifact audit round 3, min_area=30 (2026-07-24)",
}

for _cam, _polys in EXCLUSION_TRIANGLES.items():
    if len(PROVENANCE.get(_cam, [])) != len(_polys):
        raise SystemExit(
            "PROVENANCE for {} has {} entries but exclusion_mask.py has {} polygons - "
            "update the table in this script before running.".format(
                _cam, len(PROVENANCE.get(_cam, [])), len(_polys)))

INSET_COLS = 4
INSET_SIZE = 300
INSET_PAD_PX = 45  # context around each box in the zoomed inset
INSET_GAIN = 2.6   # brightness gain, insets only -- see draw_insets()


def median_background(cam_dir, max_frames=120):
    """Per-pixel median over the flight's frames - the static scene with
    people/ball/hands removed, which is what the masks are actually covering."""
    paths = sorted(cam_dir.glob("frame_*.png"))[:max_frames]
    if not paths:
        return None
    stack = np.stack([cv2.imread(str(p), cv2.IMREAD_GRAYSCALE) for p in paths])
    return np.median(stack, axis=0).astype(np.uint8)


def poly_bounds(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def put_text(img, text, org, color, scale=0.6, thick=2):
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thick + 3)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick)


def draw_overlay(bg_gray, cam_name):
    """Full-frame view: every mask polygon filled at 35% + outlined + numbered."""
    vis = cv2.cvtColor(bg_gray, cv2.COLOR_GRAY2BGR)
    fill = vis.copy()
    polys = EXCLUSION_TRIANGLES[cam_name]

    for i, poly in enumerate(polys):
        color = ORIGIN_COLOR[PROVENANCE[cam_name][i][1]]
        pts = np.array(poly, dtype=np.int32)
        cv2.fillPoly(fill, [pts], color)
    vis = cv2.addWeighted(fill, 0.35, vis, 0.65, 0)

    for i, poly in enumerate(polys):
        color = ORIGIN_COLOR[PROVENANCE[cam_name][i][1]]
        pts = np.array(poly, dtype=np.int32)
        cv2.polylines(vis, [pts], True, color, 2)
        x0, y0, x1, y1 = poly_bounds(poly)
        # Number tag outside the box where there is room, so it never hides the
        # object the box covers.
        tag_y = y0 - 8 if y0 > 30 else y1 + 24
        put_text(vis, str(i), (x0, tag_y), color, scale=0.9, thick=2)

    h, w = vis.shape[:2]
    total = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(total, [np.array(p, dtype=np.int32) for p in polys], 255)
    pct = 100.0 * np.count_nonzero(total) / (h * w)

    banner_h = 40 + 30 * len(ORIGIN_TEXT)
    banner = np.zeros((banner_h, w, 3), dtype=np.uint8)
    put_text(banner, "{}  -  final exclusion mask set: {} boxes, {:.2f}% of frame area"
             .format(cam_name, len(polys), pct), (12, 28), (255, 255, 255), scale=0.75)
    for j, (origin, text) in enumerate(ORIGIN_TEXT.items()):
        y = 62 + 30 * j
        cv2.rectangle(banner, (14, y - 14), (38, y + 4), ORIGIN_COLOR[origin], -1)
        put_text(banner, text, (50, y), ORIGIN_COLOR[origin], scale=0.6, thick=1)

    return np.vstack([banner, vis]), pct


def draw_insets(bg_gray, cam_name):
    """One zoomed crop per box, so each mask can be checked against the object
    it is supposed to be covering."""
    polys = EXCLUSION_TRIANGLES[cam_name]
    h, w = bg_gray.shape[:2]
    tiles = []

    for i, poly in enumerate(polys):
        label, origin = PROVENANCE[cam_name][i]
        color = ORIGIN_COLOR[origin]
        x0, y0, x1, y1 = poly_bounds(poly)
        cx0, cy0 = max(0, x0 - INSET_PAD_PX), max(0, y0 - INSET_PAD_PX)
        cx1, cy1 = min(w, x1 + INSET_PAD_PX), min(h, y1 + INSET_PAD_PX)
        crop = cv2.cvtColor(bg_gray[cy0:cy1, cx0:cx1], cv2.COLOR_GRAY2BGR)
        if crop.size == 0:
            continue
        # These regions are dark gym wall; at native brightness the object
        # under the box is not visible at all in the inset, which defeats the
        # point of the inset. Gain is cosmetic and applied ONLY to the insets -
        # the full-frame view above stays at true brightness.
        crop = cv2.convertScaleAbs(crop, alpha=INSET_GAIN, beta=0)

        shifted = np.array([(px - cx0, py - cy0) for px, py in poly], dtype=np.int32)
        cv2.polylines(crop, [shifted], True, color, 1)

        ch, cw = crop.shape[:2]
        s = min(INSET_SIZE / cw, INSET_SIZE / ch)
        crop = cv2.resize(crop, (max(1, int(cw * s)), max(1, int(ch * s))),
                          interpolation=cv2.INTER_NEAREST)

        tile = np.zeros((INSET_SIZE + 56, INSET_SIZE, 3), dtype=np.uint8)
        oy, ox = (INSET_SIZE - crop.shape[0]) // 2, (INSET_SIZE - crop.shape[1]) // 2
        tile[oy:oy + crop.shape[0], ox:ox + crop.shape[1]] = crop
        cv2.rectangle(tile, (0, 0), (INSET_SIZE - 1, INSET_SIZE - 1), color, 2)
        put_text(tile, "[{}] {}".format(i, label), (6, INSET_SIZE + 22), color,
                 scale=0.48, thick=1)
        put_text(tile, "x[{},{}] y[{},{}]".format(x0, x1, y0, y1),
                 (6, INSET_SIZE + 44), (200, 200, 200), scale=0.45, thick=1)
        tiles.append(tile)

    rows = []
    for i in range(0, len(tiles), INSET_COLS):
        chunk = list(tiles[i:i + INSET_COLS])
        while len(chunk) < INSET_COLS:
            chunk.append(np.zeros_like(tiles[0]))
        rows.append(np.hstack(chunk))
    return np.vstack(rows) if rows else None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--suffix", default="_exclusion_masks",
                    help="output filename suffix, e.g. _exclusion_masks_v2 to write "
                         "alongside an existing pair instead of overwriting it")
    opts = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for cam in EXCLUSION_TRIANGLES:
        cam_dir = SESSION / BACKGROUND_FLIGHT / cam / "ball_in_frame"
        bg = median_background(cam_dir)
        if bg is None:
            print("{}: no frames under {}, skipping.".format(cam, cam_dir))
            continue

        overlay, pct = draw_overlay(bg, cam)
        insets = draw_insets(bg, cam)
        if insets is not None:
            pad = overlay.shape[1] - insets.shape[1]
            if pad > 0:
                insets = np.hstack([insets, np.zeros((insets.shape[0], pad, 3), np.uint8)])
            elif pad < 0:
                overlay = np.hstack([overlay, np.zeros((overlay.shape[0], -pad, 3), np.uint8)])
            combined = np.vstack([overlay, insets])
        else:
            combined = overlay

        footer = np.zeros((36, combined.shape[1], 3), dtype=np.uint8)
        put_text(footer, "background: per-pixel median of 2026_07_21_gym/{}/{} "
                 "ball_in_frame   |   insets brightened {}x for legibility; "
                 "full frame is true brightness".format(BACKGROUND_FLIGHT, cam, INSET_GAIN),
                 (12, 24), (180, 180, 180), scale=0.55, thick=1)
        combined = np.vstack([combined, footer])

        out_path = OUT_DIR / "{}{}.png".format(cam, opts.suffix)
        cv2.imwrite(str(out_path), combined)
        print("{}: {} boxes, {:.2f}% of frame masked -> {}".format(
            cam, len(EXCLUSION_TRIANGLES[cam]), pct, out_path))

    print("\nDone. Overlays in {}".format(OUT_DIR))


if __name__ == "__main__":
    main()
