# 14_post_light_mask_artifact_sheets.py
#
# Report-figure evidence for the INTERMEDIATE detector stage: ceiling-light
# mask applied, artifact-audit masks NOT yet applied. Runs the detector over
# 2026_07_21_gym with `apply_exclusion` cut down to the light rectangle only
# (EXCLUSION_TRIANGLES[cam][0]), so the static artifacts the 2026-07-23/24
# audit later masked out - the exit sign, the wall fixture pair, the wall
# corners - are free to be selected as the ball candidate again, which is
# exactly what the figure needs to show.
#
# Two passes, because 149 flights x 2 cams of full contact sheets is ~300 huge
# PNGs of which most show no artifact at all:
#   Pass 1 - detect over every flight/cam, score each by how many detections
#            land inside a currently-DISABLED audit box.
#   Pass 2 - build contact sheets only for the top-N scoring flight/cams.
#
# The disabled-box hit test uses cv2.pointPolygonTest against the real
# polygons rather than their bounding boxes: the boxes in exclusion_mask.py
# happen to all be rectangles today, but the structure is a polygon list and
# that module's docstring documents triangles as the original design, so
# testing the polygon keeps this correct if one is ever re-cut as a triangle.
#
# Does NOT modify detector_core.py or exclusion_mask.py. The light-only
# exclusion is installed by monkey-patching `dc.apply_exclusion` at runtime -
# same pattern and same reasoning as compute_mask_rect_close_variant.py
# (decision_log.md #63): detector_core.compute_mask resolves `apply_exclusion`
# via its own module namespace at call time, so the patch takes effect all the
# way through run_detection without any file edits.
#
# Uses the ELLIPSE close kernel (detector_core.compute_mask as shipped), not
# the rect variant - the ellipse kernel is what was in force when the artifact
# audit ran, so it is the honest "before" state for this stage of the story.
#
# Reads only ball_in_frame/*.png; writes only to
# data/detector_tuning/contact_sheets/post_light_mask_artifacts/.
#
# Run from anywhere:
#   python path/to/code/14_post_light_mask_artifact_sheets.py

from pathlib import Path
import sys
import csv
import json
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import cv2

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO_ROOT))

import detector_core as dc  # noqa: E402
from src.image_processing.exclusion_mask import EXCLUSION_TRIANGLES  # noqa: E402

SESSION = REPO_ROOT / "data" / "2026_07_21_gym" / "ball_flights"
DETECTOR_TUNING_DIR = REPO_ROOT / "results" / "detector_tuning"
CONFIG_PATH = DETECTOR_TUNING_DIR / "candidate_config.json"

STAGE = "post_light_mask_artifacts"
OUT_DIR = REPO_ROOT / "data" / "detector_tuning" / "contact_sheets" / STAGE

CAMS = ["cam0", "cam1"]
TOP_N = 15  # flight/cam contact sheets to actually render

# Index 0 of each camera's list is the ceiling-light rectangle (see
# exclusion_mask.py's header comment). Everything after it is a static-artifact
# box: cam0[1] from the 2026-07 param sweep, the rest from the artifact audit.
# The scope for this figure is "light mask only", so index 0 stays on and every
# later index is disabled -- including cam0[1], which predates the audit but is
# still an artifact mask rather than a light mask.
LIGHT_POLYS = {cam: polys[:1] for cam, polys in EXCLUSION_TRIANGLES.items()}
DISABLED_POLYS = {cam: polys[1:] for cam, polys in EXCLUSION_TRIANGLES.items()}

_light_mask_cache = {}


def apply_light_only_exclusion(mask, cam_name):
    """Drop-in replacement for exclusion_mask.apply_exclusion that zeroes ONLY
    the ceiling-light rectangle, leaving every artifact-audit box open."""
    polys = LIGHT_POLYS.get(cam_name)
    if not polys:
        return mask
    key = (cam_name, mask.shape)
    if key not in _light_mask_cache:
        keep = np.full(mask.shape, 255, dtype=np.uint8)
        cv2.fillPoly(keep, [np.array(p, dtype=np.int32) for p in polys], 0)
        _light_mask_cache[key] = keep
    return cv2.bitwise_and(mask, _light_mask_cache[key])


dc.apply_exclusion = apply_light_only_exclusion  # monkey-patch -- see module docstring


def load_config(path=CONFIG_PATH):
    with open(path) as f:
        return json.load(f)


CFG = load_config()
STRIDE, DIFF_THRESHOLD, OPEN_KERNEL, CLOSE_KERNEL = (
    CFG["stride"], CFG["diff_threshold"], CFG["open_kernel"], CFG["close_kernel"])
MIN_AREA, MAX_AREA, MIN_CIRC = CFG["min_area"], CFG["max_area"], CFG["min_circ"]
MAX_SPEED_PX_PER_FRAME, MIN_RUN_LENGTH = CFG["max_speed_px_per_frame"], CFG["min_run_length"]

COLS_PER_ROW = 5
PANEL_W = 600


def disabled_box_hit(cam_name, u, v):
    """Index of the first disabled artifact box containing (u,v), else None.
    The returned index is into EXCLUSION_TRIANGLES[cam], not into
    DISABLED_POLYS, so it can be quoted directly against exclusion_mask.py."""
    for i, poly in enumerate(DISABLED_POLYS.get(cam_name, [])):
        contour = np.array(poly, dtype=np.int32)
        if cv2.pointPolygonTest(contour, (float(u), float(v)), False) >= 0:
            return i + 1
    return None


def find_flight_dirs(base):
    seen = set()
    for bif in sorted(base.rglob("ball_in_frame")):
        if not any(bif.glob("frame_*.png")):
            continue
        flight_dir = bif.parent.parent
        if flight_dir in seen:
            continue
        seen.add(flight_dir)
        yield flight_dir


def score_flight_cam(args):
    """Pass 1 worker: detect light-mask-only, count detections landing inside
    boxes the artifact audit would later have masked."""
    flight_dir_str, cam = args
    flight_dir = Path(flight_dir_str)
    cam_dir = flight_dir / cam / "ball_in_frame"
    raw = dc.run_detection(cam_dir, cam, STRIDE, DIFF_THRESHOLD, OPEN_KERNEL, CLOSE_KERNEL,
                           MIN_AREA, MAX_AREA, MIN_CIRC)
    kept = dc.filter_trajectory_outliers(raw, max_speed_px_per_frame=MAX_SPEED_PX_PER_FRAME,
                                         min_run_length=MIN_RUN_LENGTH)
    hits, hits_kept, boxes = [], 0, set()
    for fn, (u, v) in raw.items():
        idx = disabled_box_hit(cam, u, v)
        if idx is None:
            continue
        hits.append((fn, u, v, idx))
        boxes.add(idx)
        if fn in kept:
            hits_kept += 1
    return {
        "flight": flight_dir.name, "flight_dir": flight_dir_str, "cam": cam,
        "n_frames_detected": len(raw), "n_hits": len(hits),
        "n_hits_kept": hits_kept, "n_boxes": len(boxes),
        "boxes": sorted(boxes), "hits": sorted(hits),
    }


def scale_to_width(img_bgr, w):
    h0, w0 = img_bgr.shape[:2]
    h1 = max(1, int(h0 * w / w0))
    return cv2.resize(img_bgr, (w, h1), interpolation=cv2.INTER_AREA)


def put_text(panel, text, y, color):
    cv2.putText(panel, text, (5, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3)
    cv2.putText(panel, text, (5, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)


def build_contact_sheet(cam_dir, cam_name):
    """4 rows per chunk (back / fwd / AND+morph / detection) -- layout copied
    from 08_generate_contact_sheets.py rather than imported, per the pipeline's
    "numbered scripts are one-shot" convention (see 12_'s docstring)."""
    frame_paths = sorted(cam_dir.glob("frame_*.png"))
    if len(frame_paths) <= 2 * STRIDE:
        return None, 0, 0

    imgs = [cv2.imread(str(p), cv2.IMREAD_GRAYSCALE) for p in frame_paths]
    raw = dc.run_detection(cam_dir, cam_name, STRIDE, DIFF_THRESHOLD, OPEN_KERNEL, CLOSE_KERNEL,
                           MIN_AREA, MAX_AREA, MIN_CIRC)
    kept = dc.filter_trajectory_outliers(raw, max_speed_px_per_frame=MAX_SPEED_PX_PER_FRAME,
                                         min_run_length=MIN_RUN_LENGTH)

    back_panels, fwd_panels, mask_panels, det_panels = [], [], [], []
    n_kept = n_rejected = 0

    for i in range(STRIDE, len(frame_paths) - STRIDE):
        img_prev, img_curr, img_next = imgs[i - STRIDE], imgs[i], imgs[i + STRIDE]
        frame_num = int(dc.FRAME_STEM_RE.search(frame_paths[i].stem).group(1))
        name = frame_paths[i].stem

        back = cv2.absdiff(img_curr, img_prev)
        fwd = cv2.absdiff(img_next, img_curr)
        mask = dc.compute_mask(back, fwd, cam_name, DIFF_THRESHOLD, OPEN_KERNEL, CLOSE_KERNEL)
        candidates = dc.extract_candidates(mask, MIN_AREA, MAX_AREA, MIN_CIRC)

        bp = scale_to_width(cv2.cvtColor(back, cv2.COLOR_GRAY2BGR), PANEL_W)
        put_text(bp, name + " back", y=18, color=(255, 255, 255))
        back_panels.append(bp)

        fp = scale_to_width(cv2.cvtColor(fwd, cv2.COLOR_GRAY2BGR), PANEL_W)
        put_text(fp, name + " fwd", y=18, color=(255, 255, 255))
        fwd_panels.append(fp)

        mp = scale_to_width(cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR), PANEL_W)
        put_text(mp, name + " AND+morph (light mask only)", y=18, color=(255, 255, 255))
        mask_panels.append(mp)

        vis = cv2.cvtColor(img_curr, cv2.COLOR_GRAY2BGR)
        is_kept = frame_num in kept
        best_candidate = max(candidates, key=lambda d: d["area"]) if candidates else None

        for d in candidates:
            if d is not best_candidate:
                cv2.drawContours(vis, [d["contour"]], -1, (0, 255, 255), 1)  # other candidates: yellow

        status_text, status_color = "NO DETECTION", (0, 0, 255)
        if best_candidate is not None:
            u, v = best_candidate["u"], best_candidate["v"]
            status_color = (0, 255, 0) if is_kept else (0, 165, 255)  # green kept, orange rejected
            cv2.drawContours(vis, [best_candidate["contour"]], -1, status_color, 2)
            cv2.circle(vis, (int(u), int(v)), 6, status_color, -1)
            status_text = "KEPT" if is_kept else "REJECTED (artifact)"
            box_idx = disabled_box_hit(cam_name, u, v)
            if box_idx is not None:
                status_text += " [IN AUDIT BOX {}]".format(box_idx)
            status_text += " u={:.0f} v={:.0f}".format(u, v)
            if is_kept:
                n_kept += 1
            else:
                n_rejected += 1

        # Both text lines go on the SCALED panel. 08_generate_contact_sheets.py
        # draws the status on the full-res image and the frame name on the
        # scaled one, so the status shrinks by 600/1456 and collides with the
        # name -- unreadable, and these panels are going into a report figure.
        dp = scale_to_width(vis, PANEL_W)
        put_text(dp, name, y=18, color=(255, 255, 255))
        put_text(dp, status_text, y=38, color=status_color)
        det_panels.append(dp)

    blank = np.zeros_like(back_panels[0])
    rows = []
    for i in range(0, len(back_panels), COLS_PER_ROW):
        chunks = [back_panels[i:i + COLS_PER_ROW], fwd_panels[i:i + COLS_PER_ROW],
                  mask_panels[i:i + COLS_PER_ROW], det_panels[i:i + COLS_PER_ROW]]
        pad = COLS_PER_ROW - len(chunks[0])
        for c in chunks:
            rows.append(np.hstack(c + [blank] * pad))

    return np.vstack(rows), n_kept, n_rejected


def render_sheet(args):
    """Pass 2 worker."""
    flight_dir_str, cam, flight_label, suffix = args
    cam_dir = Path(flight_dir_str) / cam / "ball_in_frame"
    grid, n_kept, n_rejected = build_contact_sheet(cam_dir, cam)
    if grid is None:
        return flight_label, cam, None, 0, 0
    out_path = OUT_DIR / "{}_{}{}.png".format(flight_label, cam, suffix)
    cv2.imwrite(str(out_path), grid)
    return flight_label, cam, out_path, n_kept, n_rejected


def run_scoring_pass():
    """Pass 1: score every flight/cam, write the scores CSV, return the ranking."""
    flights = list(find_flight_dirs(SESSION))
    tasks = [(str(f), cam) for f in flights for cam in CAMS]
    print("Pass 1: scoring {} flights x {} cams, LIGHT MASK ONLY (config: stride={} "
          "thresh={} open_k={} close_k={} ellipse, area={} circ={})...".format(
              len(flights), len(CAMS), STRIDE, DIFF_THRESHOLD, OPEN_KERNEL,
              CLOSE_KERNEL, MIN_AREA, MIN_CIRC))

    results = []
    with ProcessPoolExecutor() as ex:
        futures = [ex.submit(score_flight_cam, t) for t in tasks]
        done = 0
        for fut in as_completed(futures):
            results.append(fut.result())
            done += 1
            if done % 40 == 0 or done == len(tasks):
                print("  {}/{} flight/cam jobs done".format(done, len(tasks)))

    hit_rows = [r for r in results if r["n_hits"] > 0]
    total_hits = sum(r["n_hits"] for r in hit_rows)
    total_kept = sum(r["n_hits_kept"] for r in hit_rows)
    print("\n{}/{} flight/cams have >=1 detection inside a disabled audit box; "
          "{} such detections total, {} of them SURVIVED the trajectory filter.".format(
              len(hit_rows), len(results), total_hits, total_kept))

    # Rank: distinct boxes first (a sheet showing two artifact types is a better
    # figure than one showing the same box ten times), then artifacts that beat
    # the trajectory filter, then raw hit count.
    ranked = sorted(hit_rows, key=lambda r: (r["n_boxes"], r["n_hits_kept"], r["n_hits"]),
                    reverse=True)

    scores_csv = OUT_DIR / "artifact_hit_scores.csv"
    with open(scores_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["flight", "cam", "n_frames_detected", "n_hits", "n_hits_kept",
                    "n_distinct_boxes", "boxes", "hit_frames"])
        for r in ranked:
            w.writerow([r["flight"], r["cam"], r["n_frames_detected"], r["n_hits"],
                        r["n_hits_kept"], r["n_boxes"],
                        " ".join(str(b) for b in r["boxes"]),
                        " ".join("{}@({:.0f},{:.0f})|box{}".format(fn, u, v, i)
                                 for fn, u, v, i in r["hits"])])
    print("Wrote per-flight/cam scores -> {}".format(scores_csv))
    return ranked


def ranking_from_csv():
    """Re-read a previous pass-1 ranking instead of recomputing it. Lets the
    sheets be re-rendered after a rendering-only change without spending 2 min
    re-detecting, and without rewriting artifact_hit_scores.csv."""
    scores_csv = OUT_DIR / "artifact_hit_scores.csv"
    if not scores_csv.is_file():
        raise SystemExit("--from-csv given but {} does not exist - run without it "
                         "first.".format(scores_csv))
    by_name = {f.name: str(f) for f in find_flight_dirs(SESSION)}
    ranked = []
    with open(scores_csv, newline="") as f:
        for row in csv.DictReader(f):  # already written in rank order
            flight_dir = by_name.get(row["flight"])
            if flight_dir is None:
                continue
            ranked.append({
                "flight": row["flight"], "flight_dir": flight_dir, "cam": row["cam"],
                "n_hits": int(row["n_hits"]), "n_hits_kept": int(row["n_hits_kept"]),
                "boxes": [int(b) for b in row["boxes"].split()],
            })
    print("Read {} scored flight/cams from {}".format(len(ranked), scores_csv))
    return ranked


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from-csv", action="store_true",
                    help="skip pass 1, reuse the existing artifact_hit_scores.csv")
    ap.add_argument("--suffix", default="_contact",
                    help="output filename suffix, e.g. _contact_v2 to write "
                         "alongside an existing set instead of overwriting it")
    opts = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ranked = ranking_from_csv() if opts.from_csv else run_scoring_pass()

    selected = ranked[:TOP_N]
    print("\nPass 2: rendering contact sheets for the top {} flight/cams...".format(len(selected)))
    for r in selected:
        print("  {}/{}: hits={} kept={} boxes={}".format(
            r["flight"], r["cam"], r["n_hits"], r["n_hits_kept"], r["boxes"]))

    sheet_tasks = [(r["flight_dir"], r["cam"], r["flight"], opts.suffix) for r in selected]
    with ProcessPoolExecutor() as ex:
        futures = [ex.submit(render_sheet, t) for t in sheet_tasks]
        for fut in as_completed(futures):
            flight_label, cam, out_path, n_kept, n_rejected = fut.result()
            if out_path is None:
                print("  {}/{}: no images found, skipped.".format(flight_label, cam))
            else:
                print("  {}/{}: kept={} rejected={} -> {}".format(
                    flight_label, cam, n_kept, n_rejected, out_path.name))

    print("\nDone. Sheets in {}".format(OUT_DIR))


if __name__ == "__main__":
    main()
