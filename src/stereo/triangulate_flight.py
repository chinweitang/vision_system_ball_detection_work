#!/usr/bin/env python3
"""triangulate_flight.py

Minimal ball-flight triangulation. No script in the repo triangulates an
actual ball flight yet (every existing triangulate_points() caller works on
static calibration/checkerboard images) - this is the first, built
specifically to validate pixel_velocity_correction.py via 3D arc-fit
residual (not just a visual check).

Runs one flight in 3 modes for comparison:
  (a) naive        - same-index pairing, RAW detections, no timestamp
                      awareness at all (today's implicit baseline - what
                      you'd get from treating cam0 frame N and cam1 frame N
                      as simultaneous).
  (b) paired_only  - per-camera trajectory-filtered detections, paired by
                      nearest real timestamp, no sub-frame correction.
  (c) corrected    - (b) plus the sub-frame pixel-velocity correction
                      (pixel_velocity_correction.build_corrected_pairs).

For each mode: triangulate, fit a degree-2 polynomial per 3D axis vs time,
report per-axis + overall RMS residual (mm). Camera/stereo frame is used
throughout (no world-frame registration) - a rigid transform doesn't change
residual-from-fit distances, so it isn't needed to validate the correction.
"""
from pathlib import Path
import sys
import bisect
import numpy as np

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
DETECTOR_DIR = REPO_ROOT / "src" / "image_processing" / "02_adjacent_frame_differencing"
for p in (str(DETECTOR_DIR), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)
import detector_core as dc  # noqa: E402
from triangulate import triangulate_points  # noqa: E402
from stereo_flight_sync_table import load_timestamps  # noqa: E402
from pixel_velocity_correction import (  # noqa: E402
    load_detections3, build_corrected_pairs, DEFAULT_MAX_PAIR_GAP_MS)
sys.path.insert(0, str(REPO_ROOT))
from src.stereo.trajectory_fit import fit_constant_accel, predict_at  # noqa: E402

DEFAULT_EXTRINSIC_2026_07_21 = REPO_ROOT / "calibration_outputs" / "2026_07_21" / "test2" / "stereo_extrinsic.npz"
INTRINSICS_CAM0 = REPO_ROOT / "calibration_outputs" / "cam0_intrinsics_fisheye.npz"
INTRINSICS_CAM1 = REPO_ROOT / "calibration_outputs" / "cam1_intrinsics_fisheye.npz"

# Final-tuned-detector output (MIN_AREA=30, exclusion-mask v4, trajectory
# filter, full-163-flight production run - see
# claude/claude_logs/2026-07-23_ball_detection_rate_tuning_worklog.md) - NOT
# each flight's own analysis_3/*_detections3.csv, which is stale pre-tuning
# detector output (confirmed: flight_5_cam0 has 19 rows there vs 37 here).
TUNED_DETECTIONS_DIR = (REPO_ROOT / "results" / "detector_tuning" / "detections" /
                         "03_stride1_thresh16_openk3_area30_circ0.3" / "2026_07_21_gym")


def tuned_detections_paths(flight_name):
    """(cam0_csv, cam1_csv) for one flight's tuned-detector output, or None
    if this flight has no output at this path (126 of 149 flights in this
    session do)."""
    cam0 = TUNED_DETECTIONS_DIR / f"{flight_name}_cam0_detections.csv"
    cam1 = TUNED_DETECTIONS_DIR / f"{flight_name}_cam1_detections.csv"
    if cam0.is_file() and cam1.is_file():
        return cam0, cam1
    return None


def load_calibration(extrinsic_path):
    k0 = np.load(INTRINSICS_CAM0)
    k1 = np.load(INTRINSICS_CAM1)
    ext = np.load(extrinsic_path)
    baseline_mm = float(np.linalg.norm(ext["T"]))
    return k0["K"], k0["D"], k1["K"], k1["D"], ext["R"], ext["T"], baseline_mm


def naive_pairs(cam0_dets, cam1_dets):
    """Mode (a): same-index pairing, RAW (unfiltered) detections."""
    common = sorted(set(cam0_dets) & set(cam1_dets))
    return [{"cam0_frame": f, "cam1_frame": f,
              "u0": cam0_dets[f][0], "v0": cam0_dets[f][1],
              "u1": cam1_dets[f][0], "v1": cam1_dets[f][1]} for f in common]


def paired_only(kept0, kept1, ts0, ts1, max_pair_gap_ms=DEFAULT_MAX_PAIR_GAP_MS):
    """Mode (b): nearest-timestamp pairing of filtered detections, no
    sub-frame correction. Pairs whose real timestamp gap exceeds
    max_pair_gap_ms are dropped (a per-camera coverage gap can otherwise
    make the "nearest" match genuinely far away in time - see
    pixel_velocity_correction.DEFAULT_MAX_PAIR_GAP_MS)."""
    frames1_sorted = sorted(kept1, key=lambda f: ts1[f])
    times1_sorted = [ts1[f] for f in frames1_sorted]
    out = []
    for f0 in sorted(kept0, key=lambda f: ts0[f]):
        t0 = ts0[f0]
        idx = bisect.bisect_left(times1_sorted, t0)
        cands = [i for i in (idx - 1, idx) if 0 <= i < len(times1_sorted)]
        if not cands:
            continue
        best_i = min(cands, key=lambda i: abs(times1_sorted[i] - t0))
        f1 = frames1_sorted[best_i]
        if abs(t0 - ts1[f1]) / 1e6 > max_pair_gap_ms:
            continue
        out.append({"cam0_frame": f0, "cam1_frame": f1,
                      "u0": kept0[f0][0], "v0": kept0[f0][1],
                      "u1": kept1[f1][0], "v1": kept1[f1][1],
                      "t0_ns": t0, "t1_ns": ts1[f1]})
    return out


def fit_quadratic_residual_rms(t_ms, xyz):
    """Degree-2 fit per axis vs time -> per-axis + overall RMS residual (mm,
    same units as the triangulation output, since T is in mm). Uses the
    shared fit_constant_accel/predict_at (Model A) from trajectory_fit.py --
    same polynomial family (p0 + v0*t + 0.5*a*t^2) as the old standalone
    np.polyfit-per-axis call this replaced, just parametrized as
    (p0, v0, a) instead of raw polyfit coefficients. Confirmed numerically
    equivalent residuals (matches to float precision on a synthetic check;
    see 2026-07-27 worklog) before this replacement -- t is centered on its
    own mean first, matching the old convention (not required for
    correctness, kept for numerical stability of the linear solve)."""
    t0 = np.asarray(t_ms, dtype=np.float64)
    t0 = t0 - t0.mean()
    p0, v0, a = fit_constant_accel(t0, xyz)
    fit = np.array([predict_at(p0, v0, a, tt) for tt in t0])
    residuals = {}
    for i, axis in enumerate("xyz"):
        residuals[axis] = float(np.sqrt(np.mean((xyz[:, i] - fit[:, i]) ** 2)))
    overall = float(np.sqrt(np.mean([r ** 2 for r in residuals.values()])))
    return residuals, overall


def triangulate_flight(flight_dir, timestamps_csv, extrinsic_path=DEFAULT_EXTRINSIC_2026_07_21,
                        max_speed_px_per_frame=80.0, min_run_length=2, min_points=5):
    """Runs modes (a)/(b)/(c) for one flight. Returns
    {mode_name: {"residuals": {...}, "overall_rms": ..., "n": n}} plus the
    raw corrected-pairs list (for the visual shift plot)."""
    flight_dir = Path(flight_dir)
    flight_name = flight_dir.name
    paths = tuned_detections_paths(flight_name)
    if paths is None:
        raise FileNotFoundError(
            f"no tuned-detections output for {flight_name} under {TUNED_DETECTIONS_DIR}")
    cam0_csv, cam1_csv = paths

    raw0 = load_detections3(cam0_csv)
    raw1 = load_detections3(cam1_csv)
    kept0 = dc.filter_trajectory_outliers(raw0, max_speed_px_per_frame, min_run_length)
    kept1 = dc.filter_trajectory_outliers(raw1, max_speed_px_per_frame, min_run_length)

    cam0_entries, cam1_entries = load_timestamps(timestamps_csv)
    ts0 = {f: t for f, t in cam0_entries}
    ts1 = {f: t for f, t in cam1_entries}

    K0, D0, K1, D1, R, T, baseline_mm = load_calibration(extrinsic_path)

    results = {}

    pa = naive_pairs(raw0, raw1)
    if len(pa) >= min_points:
        pts0 = [(p["u0"], p["v0"]) for p in pa]
        pts1 = [(p["u1"], p["v1"]) for p in pa]
        xyz = triangulate_points(pts0, pts1, K0, D0, K1, D1, R, T)
        t_ms = [ts0[p["cam0_frame"]] / 1e6 for p in pa]
        res, overall = fit_quadratic_residual_rms(t_ms, xyz)
        results["naive"] = {"residuals": res, "overall_rms": overall, "n": len(pa)}

    pb = paired_only(kept0, kept1, ts0, ts1)
    if len(pb) >= min_points:
        pts0 = [(p["u0"], p["v0"]) for p in pb]
        pts1 = [(p["u1"], p["v1"]) for p in pb]
        xyz = triangulate_points(pts0, pts1, K0, D0, K1, D1, R, T)
        t_ms = [(p["t0_ns"] + p["t1_ns"]) / 2 / 1e6 for p in pb]
        res, overall = fit_quadratic_residual_rms(t_ms, xyz)
        results["paired_only"] = {"residuals": res, "overall_rms": overall, "n": len(pb)}

    pc = build_corrected_pairs(cam0_csv, cam1_csv, timestamps_csv,
                                max_speed_px_per_frame, min_run_length)
    if len(pc) >= min_points:
        pts0 = [(p["u0_corr"], p["v0_corr"]) for p in pc]
        pts1 = [(p["u1_corr"], p["v1_corr"]) for p in pc]
        xyz = triangulate_points(pts0, pts1, K0, D0, K1, D1, R, T)
        t_ms = [max(p["t0_ns"], p["t1_ns"]) / 1e6 for p in pc]
        res, overall = fit_quadratic_residual_rms(t_ms, xyz)
        results["corrected"] = {"residuals": res, "overall_rms": overall, "n": len(pc)}

    return results, pc, baseline_mm


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: python3 triangulate_flight.py <flight_dir> <timestamps.csv> [extrinsic_npz]")
        sys.exit(1)
    ext = Path(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_EXTRINSIC_2026_07_21
    results, pc, baseline_mm = triangulate_flight(sys.argv[1], sys.argv[2], ext)
    print(f"baseline: {baseline_mm:.2f} mm")
    for mode, r in results.items():
        print(f"{mode:12s} n={r['n']:4d}  overall_rms={r['overall_rms']:.2f} mm  "
              f"x={r['residuals']['x']:.2f} y={r['residuals']['y']:.2f} z={r['residuals']['z']:.2f}")
