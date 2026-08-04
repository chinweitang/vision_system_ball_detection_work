#!/usr/bin/env python3
"""compare_pi_vs_laptop_output.py -- RUNS ON THE LAPTOP (Stage 2).

Correctness check: does the Pi (OpenCV 4.10.0) produce the same detection and
triangulated-3D output as the laptop (OpenCV 4.13.0) on identical frames? All
of the project's validated accuracy numbers were computed on the laptop build,
so a divergence here would be a real finding, not just benchmarking trivia.

Reuses the Pi's already-saved raw per-frame 2D detections (Stage 1's results
JSON, raw_detections_cam0/cam1) rather than re-running anything on the Pi.
Runs the identical detector_core.run_detection locally to get the laptop's own
2D detections, diffs frame-by-frame, then triangulates BOTH streams locally
(deterministic linear algebra -- cv2.fisheye.undistortPoints +
cv2.triangulatePoints -- so running both through the same local triangulate()
isolates whether DETECTION differs, without needing the Pi's own triangulated
output at all) and diffs the resulting 3D points too.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
DETECTOR_DIR = REPO_ROOT / "src" / "image_processing" / "02_adjacent_frame_differencing"
STEREO_DIR = REPO_ROOT / "src" / "stereo"
for _p in (str(DETECTOR_DIR), str(STEREO_DIR), str(REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import detector_core as dc  # noqa: E402
from pixel_velocity_correction import build_corrected_pairs  # noqa: E402
from label_vs_detection import triangulate as lvd_triangulate  # noqa: E402
from all_flights_common import load_session_calib  # noqa: E402

CONFIG_PATH = REPO_ROOT / "data" / "detector_tuning" / "candidate_config.json"
TMP_DIR = REPO_ROOT / "results" / "tmp_stage2_detections"


def write_detections3_csv(path: Path, detections: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame_number", "u", "v"])
        for fn in sorted(detections):
            u, v = detections[fn]
            w.writerow([fn, u, v])


def triangulate_stream(det0, det1, ts_csv, cfg, tag, K0, D0, K1, D1, P0, P1):
    c0 = TMP_DIR / f"{tag}_cam0.csv"
    c1 = TMP_DIR / f"{tag}_cam1.csv"
    write_detections3_csv(c0, det0)
    write_detections3_csv(c1, det1)
    pairs = build_corrected_pairs(c0, c1, ts_csv,
                                   max_speed_px_per_frame=cfg["max_speed_px_per_frame"],
                                   min_run_length=cfg["min_run_length"])
    if not pairs:
        return {}
    uv0 = np.array([(p["u0_corr"], p["v0_corr"]) for p in pairs])
    uv1 = np.array([(p["u1_corr"], p["v1_corr"]) for p in pairs])
    xyz = lvd_triangulate(uv0, uv1, K0, D0, K1, D1, P0, P1)
    return {p["cam0_frame"]: xyz[i] for i, p in enumerate(pairs)}


def compare_flight(session, flight, pi_det0, pi_det1, cfg):
    flight_dir = REPO_ROOT / "data" / session / "ball_flights" / flight
    cam0_dir = flight_dir / "cam0" / "ball_in_frame"
    cam1_dir = flight_dir / "cam1" / "ball_in_frame"
    ts_csv = flight_dir / "timestamps.csv"

    laptop_det0 = dc.run_detection(cam0_dir, "cam0", cfg["stride"], cfg["diff_threshold"],
                                    cfg["open_kernel"], cfg["close_kernel"],
                                    cfg["min_area"], cfg["max_area"], cfg["min_circ"])
    laptop_det1 = dc.run_detection(cam1_dir, "cam1", cfg["stride"], cfg["diff_threshold"],
                                    cfg["open_kernel"], cfg["close_kernel"],
                                    cfg["min_area"], cfg["max_area"], cfg["min_circ"])

    result = {"session": session, "flight": flight}
    for cam, pi_det, laptop_det in (("cam0", pi_det0, laptop_det0), ("cam1", pi_det1, laptop_det1)):
        pi_frames = {int(k) for k in pi_det}
        laptop_frames = set(laptop_det)
        common = pi_frames & laptop_frames
        deltas = [float(np.hypot(pi_det[str(f)][0] - laptop_det[f][0],
                                  pi_det[str(f)][1] - laptop_det[f][1])) for f in common]
        result[cam] = {
            "n_pi": len(pi_frames), "n_laptop": len(laptop_frames),
            "only_pi": sorted(pi_frames - laptop_frames),
            "only_laptop": sorted(laptop_frames - pi_frames),
            "n_common": len(common),
            "centroid_delta_px": {
                "max": max(deltas) if deltas else 0.0,
                "mean": float(np.mean(deltas)) if deltas else 0.0,
            },
        }

    K0, D0, K1, D1, P0, P1 = load_session_calib(session)
    pi_det0_int = {int(k): tuple(v) for k, v in pi_det0.items()}
    pi_det1_int = {int(k): tuple(v) for k, v in pi_det1.items()}
    pi_xyz = triangulate_stream(pi_det0_int, pi_det1_int, ts_csv, cfg, "pi", K0, D0, K1, D1, P0, P1)
    laptop_xyz = triangulate_stream(laptop_det0, laptop_det1, ts_csv, cfg, "laptop", K0, D0, K1, D1, P0, P1)
    common3d = set(pi_xyz) & set(laptop_xyz)
    xyz_deltas = [float(np.linalg.norm(pi_xyz[f] - laptop_xyz[f])) for f in common3d]
    result["triangulated_3d"] = {
        "n_pi_pairs": len(pi_xyz), "n_laptop_pairs": len(laptop_xyz),
        "n_common": len(common3d),
        "delta_mm": {
            "max": max(xyz_deltas) if xyz_deltas else 0.0,
            "mean": float(np.mean(xyz_deltas)) if xyz_deltas else 0.0,
        },
    }
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage1", required=True, help="path to Stage 1 results JSON")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    stage1 = json.loads(Path(args.stage1).read_text())
    cfg = stage1["config"]

    results = []
    for f in stage1["flights"]:
        print(f"=== {f['session']}/{f['flight']} ===", flush=True)
        r = compare_flight(f["session"], f["flight"],
                            f["raw_detections_cam0"], f["raw_detections_cam1"], cfg)
        results.append(r)
        c0, c1, t3 = r["cam0"], r["cam1"], r["triangulated_3d"]
        print(f"  cam0: {c0['n_common']} common, only_pi={len(c0['only_pi'])}, "
              f"only_laptop={len(c0['only_laptop'])}, max_delta={c0['centroid_delta_px']['max']:.4f}px")
        print(f"  cam1: {c1['n_common']} common, only_pi={len(c1['only_pi'])}, "
              f"only_laptop={len(c1['only_laptop'])}, max_delta={c1['centroid_delta_px']['max']:.4f}px")
        print(f"  3D:   {t3['n_common']} common, max_delta={t3['delta_mm']['max']:.4f}mm")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump({"laptop_cv2_version": __import__("cv2").__version__,
                   "pi_cv2_version": stage1["machine_info"]["cv2_version"],
                   "flights": results}, f, indent=2)
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
