# 05_detection_rate_summary.py
#
# Aggregates ball-detection rate across every flight that has had
# 04_stereo_three_frame_diff.py run on it (i.e. has an analysis_3/ folder),
# for BOTH the 2026_07_15_gym and 2026_07_21_gym sessions.
#
# Does NOT re-run detection - just reads the already-written
# analysis_3/*_detections3.csv files (one row per detected frame, keyed by
# frame_number) and the ball_in_frame/*.png filenames per cam.
#
# combined_rate is NOT total-detections-across-both-cams / total-processable-
# across-both-cams: triangulation needs a detection in cam0 AND cam1 for the
# SAME frame, so it's computed as co-detected frames / co-processable frames,
# where "co-processable" = frame numbers that are processable in BOTH cams
# (the intersection), and "co-detected" = frame numbers detected in BOTH cams.
#
# Per-cam processable = frame numbers in that cam's ball_in_frame, minus the
# STRIDE frames lost at each end of the 3-frame diff (positional, matching
# what 04_stereo_three_frame_diff.py actually evaluates). STRIDE must match
# the value in that script (currently 1).
#
# Output: one row per flight, both cams' individual numbers plus the
# co-detection combined rate, followed by a final AVERAGE row (simple mean
# of combined_rate across flights, each flight weighted equally). Written to
# <ball_flights_dir>/detection_rate_summary.csv for each session, i.e.:
#   data/2026_07_15_gym/ball_flights/detection_rate_summary.csv
#   data/2026_07_21_gym/ball_flights/detection_rate_summary.csv
#
# Run from anywhere:
#   python path/to/code/05_detection_rate_summary.py

from pathlib import Path
import csv
import re

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]

STRIDE = 1  # must match 04_stereo_three_frame_diff.py

SESSIONS = [
    REPO_ROOT / "data" / "2026_07_15_gym" / "ball_flights",
    REPO_ROOT / "data" / "2026_07_21_gym" / "ball_flights",
]

CAMS = ["cam0", "cam1"]

FRAME_RE = re.compile(r"frame_(\d+)\.png$")


def processable_frame_numbers(ball_in_frame_dir: Path) -> set:
    """Frame numbers actually evaluated by the 3-frame diff: sorted
    ball_in_frame frames with STRIDE dropped from each end, by position -
    matches 04_stereo_three_frame_diff.py's `for i in range(STRIDE, len-STRIDE)`."""
    files = sorted(ball_in_frame_dir.glob("frame_*.png"))
    if len(files) <= 2 * STRIDE:
        return set()
    kept = files[STRIDE: len(files) - STRIDE]
    return {int(FRAME_RE.search(f.name).group(1)) for f in kept}


def detected_frame_numbers(detections_csv: Path) -> set:
    with open(detections_csv, newline="") as f:
        return {int(row["frame_number"]) for row in csv.DictReader(f)}


def find_flight_dirs(ball_flights_dir: Path):
    """Yield (flight_label, flight_dir) for every dir containing a populated
    cam0/ball_in_frame or cam1/ball_in_frame, at any depth (so nested session
    subfolders like "2 ball contacts ground before plane/flight_01" are
    picked up too)."""
    seen = set()
    for bif_dir in sorted(ball_flights_dir.rglob("ball_in_frame")):
        if not any(bif_dir.glob("frame_*.png")):
            continue
        flight_dir = bif_dir.parent.parent  # cam dir's parent
        if flight_dir in seen:
            continue
        seen.add(flight_dir)
        yield flight_dir.name, flight_dir


def main():
    for ball_flights_dir in SESSIONS:
        if not ball_flights_dir.is_dir():
            print(f"Skipping (not found): {ball_flights_dir}")
            continue

        rows = []
        for flight_label, flight_dir in find_flight_dirs(ball_flights_dir):
            analysis_dir = flight_dir / "analysis_3"
            row = {"flight": flight_label}

            proc = {}
            det = {}
            for cam in CAMS:
                bif_dir = flight_dir / cam / "ball_in_frame"
                proc[cam] = processable_frame_numbers(bif_dir) if bif_dir.is_dir() else set()

                det_csv = analysis_dir / f"{flight_label}_{cam}_detections3.csv"
                det[cam] = detected_frame_numbers(det_csv) if det_csv.is_file() else set()

                processable_n = len(proc[cam])
                detections_n = len(det[cam]) if det_csv.is_file() else None
                rate = (detections_n / processable_n) if (detections_n is not None and processable_n > 0) else None

                row[f"{cam}_processable"] = processable_n
                row[f"{cam}_detections"] = detections_n if detections_n is not None else ""
                row[f"{cam}_rate"] = f"{rate:.4f}" if rate is not None else ""

            co_processable = proc["cam0"] & proc["cam1"]
            co_detected = det["cam0"] & det["cam1"]
            combined_rate = (len(co_detected) / len(co_processable)) if co_processable else None

            row["combined_processable"] = len(co_processable)
            row["combined_detections"] = len(co_detected)
            row["combined_rate"] = f"{combined_rate:.4f}" if combined_rate is not None else ""
            row["_combined_rate_val"] = combined_rate  # for averaging, stripped before writing

            rows.append(row)

        if not rows:
            print(f"{ball_flights_dir}: no flights with ball_in_frame content found, skipping.")
            continue

        # Natural sort by trailing flight number so flight_2 < flight_10.
        def sort_key(r):
            digits = "".join(ch for ch in r["flight"] if ch.isdigit())
            return int(digits) if digits else 0
        rows.sort(key=sort_key)

        valid_rates = [r["_combined_rate_val"] for r in rows if r["_combined_rate_val"] is not None]
        avg_combined_rate = sum(valid_rates) / len(valid_rates) if valid_rates else None

        for r in rows:
            del r["_combined_rate_val"]

        fieldnames = ["flight", "cam0_processable", "cam0_detections", "cam0_rate",
                      "cam1_processable", "cam1_detections", "cam1_rate",
                      "combined_processable", "combined_detections", "combined_rate"]

        out_path = ball_flights_dir / "detection_rate_summary.csv"
        with open(out_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)
            avg_row = {k: "" for k in fieldnames}
            avg_row["flight"] = "AVERAGE"
            avg_row["combined_rate"] = f"{avg_combined_rate:.4f}" if avg_combined_rate is not None else ""
            w.writerow(avg_row)

        print(f"Wrote {len(rows)} flight(s) + AVERAGE row -> {out_path}")


if __name__ == "__main__":
    main()
