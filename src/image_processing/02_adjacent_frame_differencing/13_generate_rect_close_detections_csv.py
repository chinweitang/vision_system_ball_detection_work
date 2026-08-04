# 13_generate_rect_close_detections_csv.py
#
# Regenerates the rect-close-kernel detections as persisted per-frame CSVs
# (frame_number, u, v), matching 11_generate_detections_csv.py's exact
# format/convention. The earlier accuracy validation run
# (12_run_full_dataset_rect_close_kernel.py, decision 64) computed these same
# detections in memory to get combined_rate + contact sheets, but never wrote
# them to CSV -- this regenerates them (cheap, deterministic, same
# monkey-patch) so they can feed the rect-vs-ellipse Model C prediction
# comparison, which needs per-frame detection CSVs in the same shape
# build_corrected_pairs()/build_corrected_track() already consume for the
# ellipse baseline.
#
# Output is RAW detector output (dc.run_detection() only, NOT
# filter_trajectory_outliers()) -- matching 11_generate_detections_csv.py's
# convention exactly, since the pairing/triangulation pipeline
# (pixel_velocity_correction.build_corrected_pairs) applies trajectory
# filtering itself downstream.
#
# Does NOT modify detector_core.py -- monkey-patches dc.compute_mask via the
# shared compute_mask_rect_close_variant module (see that file's docstring).
#
# Output: data/detector_tuning/detections/12_rect_close_kernel/<session>/
# <flight_id>_<cam>_detections.csv
#
# Run from anywhere:
#   python path/to/code/13_generate_rect_close_detections_csv.py

from pathlib import Path
import sys
import csv
from concurrent.futures import ProcessPoolExecutor, as_completed

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO_ROOT))
import detector_core as dc  # noqa: E402
from compute_mask_rect_close_variant import compute_mask_rect_close  # noqa: E402
import json  # noqa: E402

dc.compute_mask = compute_mask_rect_close  # monkey-patch -- see compute_mask_rect_close_variant.py

STAGE = "12_rect_close_kernel"  # matches 12_run_full_dataset_rect_close_kernel.py's contact-sheet STAGE naming

DETECTOR_TUNING_DIR = REPO_ROOT / "data" / "detector_tuning"
CONFIG_PATH = DETECTOR_TUNING_DIR / "candidate_config.json"
DETECTIONS_ROOT = DETECTOR_TUNING_DIR / "detections" / STAGE

CAMS = ["cam0", "cam1"]
SESSIONS = ["2026_07_21_gym", "2026_07_15_gym"]


def load_config(path=CONFIG_PATH):
    with open(path) as f:
        return json.load(f)


CFG = load_config()
STRIDE, DIFF_THRESHOLD, OPEN_KERNEL, CLOSE_KERNEL = (
    CFG["stride"], CFG["diff_threshold"], CFG["open_kernel"], CFG["close_kernel"])
MIN_AREA, MAX_AREA, MIN_CIRC = CFG["min_area"], CFG["max_area"], CFG["min_circ"]


def find_flight_dirs(base: Path):
    """Same enumeration/collision-safety as 11_generate_detections_csv.py."""
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
            raise RuntimeError(f"basename collision within session {base}: {flight_dir.name}")
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
    n_written_total = 0
    n_tasks_total = 0
    for session in SESSIONS:
        session_dir = REPO_ROOT / "data" / session / "ball_flights"
        out_dir = DETECTIONS_ROOT / session
        out_dir.mkdir(parents=True, exist_ok=True)

        flights = list(find_flight_dirs(session_dir))
        print(f"Generating RECT-close-kernel detection CSVs for {session}: {len(flights)} flights x "
              f"{len(CAMS)} cams (stride={STRIDE} thresh={DIFF_THRESHOLD} open_k={OPEN_KERNEL}(ellipse) "
              f"close_k={CLOSE_KERNEL}(RECT))")
        print(f"Output -> {out_dir}")

        tasks = [(str(fd), label, cam, str(out_dir)) for label, fd in flights for cam in CAMS]
        n_tasks_total += len(tasks)

        with ProcessPoolExecutor() as ex:
            futures = {ex.submit(process_flight_cam, t): t for t in tasks}
            done = 0
            for fut in as_completed(futures):
                flight_id, cam, n_dets, out_path = fut.result()
                if out_path is not None:
                    n_written_total += 1
                done += 1
                if done % 40 == 0 or done == len(tasks):
                    print(f"  {session}: {done}/{len(tasks)} flight/cam jobs done")

    print(f"\nWrote {n_written_total}/{n_tasks_total} CSV(s) total -> {DETECTIONS_ROOT}")


if __name__ == "__main__":
    main()
