# 07_artifact_audit.py
#
# Systematic, largely-automated search for recurring STATIC false-positive
# artifacts (light fixtures, exit signs, wall corners - anything that only
# surfaces once DIFF_THRESHOLD/OPEN_KERNEL are loosened) across the ENTIRE
# dataset, rather than eyeballing contact sheets flight by flight.
#
# Idea: the camera rig is fixed, so a genuine static artifact recurs at
# nearly the same pixel location across MANY DIFFERENT flights. Incidental
# one-off noise doesn't - it scatters. filter_trajectory_outliers() already
# tells us, per flight/cam, exactly which candidate detections got rejected
# as physically implausible. Pool every rejected point across the whole
# dataset, bin it spatially, and rank bins by how many DISTINCT FLIGHTS
# contributed a point there (not just raw point count, since one flight with
# a long-lived artifact would otherwise dominate the count without it
# actually being a multi-flight recurring thing).
#
# Does NOT touch any real flight data or analysis_3 folders - reads only
# from ball_in_frame/*.png, writes only to results/detector_tuning/.
#
# Run from anywhere:
#   python path/to/code/07_artifact_audit.py

from pathlib import Path
import sys
import csv
import json
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed

import cv2

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO_ROOT))

import detector_core as dc  # noqa: E402

DETECTOR_TUNING_DIR = REPO_ROOT / "results" / "detector_tuning"
CONFIG_PATH = DETECTOR_TUNING_DIR / "candidate_config.json"

SESSIONS = [
    REPO_ROOT / "data" / "2026_07_15_gym" / "ball_flights",
    REPO_ROOT / "data" / "2026_07_21_gym" / "ball_flights",
]
CAMS = ["cam0", "cam1"]


def load_config(path=CONFIG_PATH):
    """Single source of truth for the "current best" detector config - see
    results/detector_tuning/candidate_config.json and the 2026-07-23 worklog."""
    with open(path) as f:
        return json.load(f)


CFG = load_config()
STRIDE, DIFF_THRESHOLD, OPEN_KERNEL, CLOSE_KERNEL = (
    CFG["stride"], CFG["diff_threshold"], CFG["open_kernel"], CFG["close_kernel"])
MIN_AREA, MAX_AREA, MIN_CIRC = CFG["min_area"], CFG["max_area"], CFG["min_circ"]
MAX_SPEED_PX_PER_FRAME, MIN_RUN_LENGTH = CFG["max_speed_px_per_frame"], CFG["min_run_length"]

# Stage subfolder auto-derived from the config in force at run time, so every
# audit's hotspots CSV + crops land together under a name that identifies
# exactly which config produced them (not a flat, ever-overwritten file) -
# e.g. results/detector_tuning/inspection_crops/area30_circ0.3/.
STAGE = f"area{MIN_AREA}_circ{MIN_CIRC}"
OUT_DIR = DETECTOR_TUNING_DIR / "inspection_crops" / STAGE
CROPS_DIR = OUT_DIR

BIN_SIZE_PX = 40  # spatial bin for clustering rejected points
MIN_DISTINCT_FLIGHTS = 3  # a hotspot must be hit by at least this many different flights


def find_flight_dirs(base: Path):
    seen = set()
    for bif in sorted(base.rglob("ball_in_frame")):
        if not any(bif.glob("frame_*.png")):
            continue
        flight_dir = bif.parent.parent
        if flight_dir in seen:
            continue
        seen.add(flight_dir)
        yield flight_dir


def process_flight_cam(args):
    flight_dir_str, cam = args
    flight_dir = Path(flight_dir_str)
    cam_dir = flight_dir / cam / "ball_in_frame"
    raw = dc.run_detection(cam_dir, cam, STRIDE, DIFF_THRESHOLD, OPEN_KERNEL, CLOSE_KERNEL,
                            MIN_AREA, MAX_AREA, MIN_CIRC)
    filtered = dc.filter_trajectory_outliers(raw, max_speed_px_per_frame=MAX_SPEED_PX_PER_FRAME,
                                              min_run_length=MIN_RUN_LENGTH)
    rejected = {f: uv for f, uv in raw.items() if f not in filtered}
    flight_label = flight_dir.name
    return cam, [(flight_label, flight_dir_str, fn, u, v) for fn, (u, v) in rejected.items()]


def main():
    flights = []
    for base in SESSIONS:
        flights.extend(find_flight_dirs(base))
    print(f"Auditing {len(flights)} flights x {len(CAMS)} cams "
          f"(config: stride={STRIDE} thresh={DIFF_THRESHOLD} open_k={OPEN_KERNEL})...")

    tasks = [(str(f), cam) for f in flights for cam in CAMS]
    rejected_by_cam = defaultdict(list)  # cam -> [(flight_label, flight_dir, frame_num, u, v)]

    with ProcessPoolExecutor() as ex:
        futures = {ex.submit(process_flight_cam, t): t for t in tasks}
        done = 0
        for fut in as_completed(futures):
            cam, points = fut.result()
            rejected_by_cam[cam].extend(points)
            done += 1
            if done % 40 == 0 or done == len(tasks):
                print(f"  {done}/{len(tasks)} flight/cam jobs done")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CROPS_DIR.mkdir(parents=True, exist_ok=True)

    all_hotspots = []
    for cam in CAMS:
        points = rejected_by_cam[cam]
        print(f"\n{cam}: {len(points)} total rejected points pooled across all flights")

        bins = defaultdict(list)  # (bin_u, bin_v) -> [(flight_label, flight_dir, frame_num, u, v)]
        for flight_label, flight_dir, fn, u, v in points:
            key = (int(u // BIN_SIZE_PX), int(v // BIN_SIZE_PX))
            bins[key].append((flight_label, flight_dir, fn, u, v))

        scored = []
        for key, pts in bins.items():
            distinct_flights = len({p[0] for p in pts})
            if distinct_flights >= MIN_DISTINCT_FLIGHTS:
                scored.append((distinct_flights, len(pts), key, pts))
        scored.sort(key=lambda x: x[0], reverse=True)

        print(f"{cam}: {len(scored)} hotspot bin(s) hit by >= {MIN_DISTINCT_FLIGHTS} distinct flights")
        for distinct_flights, n_pts, (bu, bv), pts in scored[:15]:
            cu, cv = bu * BIN_SIZE_PX + BIN_SIZE_PX // 2, bv * BIN_SIZE_PX + BIN_SIZE_PX // 2
            print(f"  bin center=({cu},{cv})  distinct_flights={distinct_flights}  total_points={n_pts}")
            all_hotspots.append({
                "cam": cam, "bin_center_u": cu, "bin_center_v": cv,
                "distinct_flights": distinct_flights, "total_points": n_pts,
                "example_flight": pts[0][0], "example_frame": pts[0][2],
                "example_u": f"{pts[0][3]:.1f}", "example_v": f"{pts[0][4]:.1f}",
            })

    hotspots_csv = OUT_DIR / "artifact_audit_hotspots.csv"
    with open(hotspots_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["cam", "bin_center_u", "bin_center_v", "distinct_flights",
                                           "total_points", "example_flight", "example_frame",
                                           "example_u", "example_v"])
        w.writeheader()
        w.writerows(sorted(all_hotspots, key=lambda r: r["distinct_flights"], reverse=True))
    print(f"\nWrote {len(all_hotspots)} hotspot(s) -> {hotspots_csv}")

    # Save one representative crop per hotspot for visual confirmation.
    print("\nSaving representative crops for each hotspot...")
    for h in sorted(all_hotspots, key=lambda r: r["distinct_flights"], reverse=True):
        flight_label = h["example_flight"]
        frame_num = h["example_frame"]
        u, v = h["bin_center_u"], h["bin_center_v"]
        # find the flight_dir string matching this label+cam from the raw task list
        match = next((fd for fd, cam in tasks if Path(fd).name == flight_label and cam == h["cam"]), None)
        if match is None:
            continue
        img_path = Path(match) / h["cam"] / "ball_in_frame" / f"frame_{frame_num:03d}.png"
        if not img_path.is_file():
            continue
        img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        r = 60
        y0, y1 = max(0, v - r), v + r
        x0, x1 = max(0, u - r), u + r
        crop = img[y0:y1, x0:x1]
        crop = cv2.resize(crop, (400, 400), interpolation=cv2.INTER_NEAREST)
        out_name = f"hotspot_{h['cam']}_u{u}_v{v}_{flight_label}_frame{frame_num:03d}.png"
        cv2.imwrite(str(CROPS_DIR / out_name), crop)
        print(f"  saved {out_name}  (distinct_flights={h['distinct_flights']})")

    print(f"\nDone. Review crops in {CROPS_DIR}")


if __name__ == "__main__":
    main()
