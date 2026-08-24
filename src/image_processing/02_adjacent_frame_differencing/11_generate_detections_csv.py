# 11_generate_detections_csv.py
#
# Generate raw (pre-trajectory-filter) per-flight, per-camera detection CSVs
# at the CURRENT tuned config (results/detector_tuning/candidate_config.json,
# stride=1 thresh=16 open_k=3 min_area=30 min_circ=0.3 + exclusion_mask.py
# v4), for data/<SESSION>/ball_flights (--session 2026_07_21_gym or
# 2026_07_15_gym -- flight_velocity_angle_binner.py consumes both).
#
# Why this is needed: the existing per-flight analysis_N/*_detections*.csv
# files were generated under the OLD/untuned default config (thresh=20,
# open_k=7, min_area=200, no exclusion mask v4) - see
# claude/claude_logs/2026-07-23_ball_detection_rate_tuning_worklog.md. The
# full-dataset production run (10_run_full_dataset.py) already validated the
# current config's combined_rate/recall across both sessions, but only wrote
# AGGREGATE stats + contact-sheet visualizations - it never wrote out the
# per-frame (frame_number, u, v) CSVs themselves, which
# flight_velocity_angle_binner.py needs as input.
#
# Output is RAW detector output (run_detection() only, NOT
# filter_trajectory_outliers()) - matching analysis_3's own raw convention,
# since flight_velocity_angle_binner.py already applies
# filter_trajectory_outliers() itself as an independent step.
#
# Output location: centralized under
# results/detector_tuning/detections/<STAGE>/<SESSION>/, NOT scattered as
# per-flight analysis_4 folders - matching the same centralization decision
# already made (and reasoned through) for 10_run_full_dataset.py's contact
# sheets / validated-results CSV, using the SAME stage folder name so sibling
# artifacts for this config stay discoverable together. Session-subfoldered
# (added when extending to 2026_07_15_gym) so both sessions' CSVs can live
# side by side without a flight-number collision risk (2026_07_15_gym and
# 2026_07_21_gym both have e.g. a "flight_22").
#
# flight_id for 2026_07_15_gym uses flight_dir.name only (drops nested
# subfolder prefixes like "2 ball contacts ground before plane/") - same fix
# 10_run_full_dataset.py already applied for this exact session (avoids a
# Windows MAX_PATH failure on the one deeply-nested flight; confirmed no
# basename collision within this session before relying on it).
#
# Run from anywhere:
#   python path/to/code/11_generate_detections_csv.py --session 2026_07_21_gym
#   python path/to/code/11_generate_detections_csv.py --session 2026_07_15_gym

from pathlib import Path
import sys
import csv
import json
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO_ROOT))
import detector_core as dc  # noqa: E402

STAGE = "03_stride1_thresh16_openk3_area30_circ0.3"  # matches 10_run_full_dataset.py's STAGE

DETECTOR_TUNING_DIR = REPO_ROOT / "results" / "detector_tuning"
CONFIG_PATH = DETECTOR_TUNING_DIR / "candidate_config.json"
DETECTIONS_ROOT = DETECTOR_TUNING_DIR / "detections" / STAGE

CAMS = ["cam0", "cam1"]


def load_config(path=CONFIG_PATH):
    with open(path) as f:
        return json.load(f)


CFG = load_config()
STRIDE, DIFF_THRESHOLD, OPEN_KERNEL, CLOSE_KERNEL = (
    CFG["stride"], CFG["diff_threshold"], CFG["open_kernel"], CFG["close_kernel"])
MIN_AREA, MAX_AREA, MIN_CIRC = CFG["min_area"], CFG["max_area"], CFG["min_circ"]


def find_flight_dirs(base: Path):
    """Yield (flight_id, flight_dir) for every flight with a populated
    ball_in_frame in at least one cam. flight_id is flight_dir.name only
    (drops any nested subfolder) -- confirmed no basename collision within a
    single session before relying on this, same as 10_run_full_dataset.py."""
    seen = set()
    seen_names = set()
    for bif in sorted(base.rglob("ball_in_frame")):
        if not any(bif.glob("frame_*.png")):
            continue
        flight_dir = bif.parent.parent
        if flight_dir in seen:
            continue
        seen.add(flight_dir)
        if flight_dir.name in seen_names:
            raise RuntimeError(f"basename collision within session {base}: {flight_dir.name} "
                                f"-- flight_id-by-basename-only is unsafe here, needs a real fix")
        seen_names.add(flight_dir.name)
        yield flight_dir.name, flight_dir


def process_flight_cam(args):
    flight_dir_str, flight_id, cam, out_dir_str = args
    flight_dir = Path(flight_dir_str)
    out_dir = Path(out_dir_str)
    cam_dir = flight_dir / cam / "ball_in_frame"
    if not cam_dir.is_dir():
        return flight_id, cam, 0, None

    raw = dc.run_detection(cam_dir, cam, STRIDE, DIFF_THRESHOLD, OPEN_KERNEL, CLOSE_KERNEL,
                            MIN_AREA, MAX_AREA, MIN_CIRC)

    out_path = out_dir / f"{flight_id}_{cam}_detections.csv"
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame_number", "u", "v"])
        for fn in sorted(raw):
            u, v = raw[fn]
            w.writerow([fn, f"{u:.4f}", f"{v:.4f}"])

    return flight_id, cam, len(raw), str(out_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True, choices=["2026_07_21_gym", "2026_07_15_gym"])
    args = ap.parse_args()

    session_dir = REPO_ROOT / "data" / args.session / "ball_flights"
    out_dir = DETECTIONS_ROOT / args.session
    out_dir.mkdir(parents=True, exist_ok=True)

    flights = list(find_flight_dirs(session_dir))
    print(f"Generating raw detection CSVs for {args.session}: {len(flights)} flights x "
          f"{len(CAMS)} cams (stride={STRIDE} thresh={DIFF_THRESHOLD} open_k={OPEN_KERNEL} "
          f"min_area={MIN_AREA} min_circ={MIN_CIRC})")
    print(f"Output -> {out_dir}")

    tasks = [(str(fd), label, cam, str(out_dir)) for label, fd in flights for cam in CAMS]

    n_written = 0
    with ProcessPoolExecutor() as ex:
        futures = {ex.submit(process_flight_cam, t): t for t in tasks}
        done = 0
        for fut in as_completed(futures):
            flight_id, cam, n_dets, out_path = fut.result()
            if out_path is not None:
                n_written += 1
            done += 1
            if done % 40 == 0 or done == len(tasks):
                print(f"  {done}/{len(tasks)} flight/cam jobs done")

    print(f"\nWrote {n_written}/{len(tasks)} CSV(s) -> {out_dir}")


if __name__ == "__main__":
    main()
