# world_frame_validate_2026_07_15.py
#
# Validate world-frame registration for the 2026_07_15_gym session, for
# extending flight_velocity_angle_binner.py to this session too. Unlike
# 2026_07_21_gym (which had two registrations mid-session), this session has
# ONE registration with 4 candidate checkerboard image pairs
# (img_0026/0028/0029/0030) in
# data/2026_07_15_gym/world_registration&rebounder_registration/{cam0,cam1}/.
#
# Same method as world_frame_validate_2026_07_21.py (see
# claude/claude_logs/2026-07-25_flight_velocity_angle_binner_worklog.md for
# why): up_vec from src/stereo/world_registration.py's solve_world_frame()
# (checkerboard-pose solve, no manual click), guardrail checks (baseline-
# perpendicular-to-up angle, weak-axis-must-be-width, Umeyama corner-residual
# precision) reused unmodified from world_frame_precision_single.py.
#
# Usage:
#   python src/registration/world_frame_validate_2026_07_15.py

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.stereo.triangulate import triangulate_points
from src.stereo.world_registration import solve_world_frame
from src.calibration.extrinsic.solve_extrinsic import (
    OBJP, detect_corners, load_intrinsics,
)
from src.registration.world_frame_precision_single import (
    umeyama_alignment, apply_similarity, normalize,
)

INTRINSICS_DIR = ROOT / "calibration_outputs"
EXTRINSICS_PATH = ROOT / "calibration_outputs/2026_07_15/stereo_extrinsic.npz"
WORLD_REG_DIR = ROOT / "data/2026_07_15_gym/world_registration&rebounder_registration"
OUT_DIR = ROOT / "data/2026_07_15_gym/flight_binning/world_frame_validation"

BASELINE_UP_ANGLE_TOL_DEG = 10.0
BASELINE_EXPECT_MM = 850.0
BASELINE_TOL_PCT = 10.0

CANDIDATES = ["img_0026", "img_0028", "img_0029", "img_0030"]


def validate_candidate(img_stem, K0, D0, K1, D1, R, T, baseline_dir, emit):
    cam0_path = WORLD_REG_DIR / "cam0" / f"{img_stem}.png"
    cam1_path = WORLD_REG_DIR / "cam1" / f"{img_stem}.png"

    emit(f"--- {img_stem} ---")

    g0 = cv2.imread(str(cam0_path), cv2.IMREAD_GRAYSCALE)
    g1 = cv2.imread(str(cam1_path), cv2.IMREAD_GRAYSCALE)
    if g0 is None or g1 is None:
        emit(f"  FAIL: could not read image(s) ({cam0_path}, {cam1_path})")
        emit("")
        return None

    found0, c0 = detect_corners(g0)
    found1, c1 = detect_corners(g1)
    if not (found0 and found1):
        missing = [n for n, f in (("cam0", found0), ("cam1", found1)) if not f]
        emit(f"  FAIL: checkerboard not detected in {', '.join(missing)}")
        emit("")
        return None

    try:
        R_wc, T_wc = solve_world_frame(cam0_path, K0, D0)
    except Exception as e:
        emit(f"  FAIL: solve_world_frame raised: {e}")
        emit("")
        return None

    up_vec = -R_wc[:, 1]
    up_vec = up_vec / np.linalg.norm(up_vec)

    baseline_up_angle = float(np.degrees(np.arccos(np.clip(np.dot(baseline_dir, up_vec), -1.0, 1.0))))
    emit(f"  angle(baseline_dir, up_vec) = {baseline_up_angle:.2f} deg "
         f"(expect ~90, tol {BASELINE_UP_ANGLE_TOL_DEG})")
    guardrail_a_pass = abs(baseline_up_angle - 90.0) <= BASELINE_UP_ANGLE_TOL_DEG
    if not guardrail_a_pass:
        emit(f"    *** GUARDRAIL (a) FAIL: baseline/up not ~perpendicular ***")

    Z_world = up_vec
    X_world = normalize(baseline_dir - np.dot(baseline_dir, Z_world) * Z_world)
    Y_world = np.cross(Z_world, X_world)

    tri = triangulate_points(c0, c1, K0, D0, K1, D1, R, T)
    mean_z_mm = float(tri[:, 2].mean())

    R_sim, t_sim, s_sim = umeyama_alignment(OBJP, tri, with_scale=True)
    pred = apply_similarity(OBJP, R_sim, t_sim, s_sim)
    resid = tri - pred
    overall_rms_mm = float(np.sqrt(np.mean(np.sum(resid ** 2, axis=1))))

    proj_x = resid @ X_world
    proj_y = resid @ Y_world
    proj_z = resid @ Z_world
    rms_x = float(np.sqrt(np.mean(proj_x ** 2)))
    rms_y = float(np.sqrt(np.mean(proj_y ** 2)))
    rms_z = float(np.sqrt(np.mean(proj_z ** 2)))

    emit(f"  board mean depth (cam0 Z) = {mean_z_mm:.0f} mm")
    emit(f"  similarity scale = {s_sim:.4f}")
    emit(f"  overall 3D RMS residual = {overall_rms_mm:.2f} mm")
    emit(f"    rms_X (baseline-parallel horiz, STRONG) = {rms_x:.2f} mm")
    emit(f"    rms_Y (baseline-perp horiz / weak axis)  = {rms_y:.2f} mm")
    emit(f"    rms_Z (vertical, STRONG)                 = {rms_z:.2f} mm")

    axis_rms = {"X_world": rms_x, "Y_world": rms_y, "Z_world": rms_z}
    weakest = max(axis_rms, key=axis_rms.get)
    guardrail_b_pass = weakest == "Y_world"
    emit(f"  largest-spread axis = {weakest} (expect Y_world -- rig's weak/depth axis)")
    if not guardrail_b_pass:
        emit(f"    *** GUARDRAIL (b) FAIL: weakest axis is not Y_world ***")

    overall_pass = guardrail_a_pass and guardrail_b_pass
    emit(f"  RESULT: {'PASS' if overall_pass else 'FAIL'}")
    emit("")

    return dict(img_stem=img_stem, R_wc=R_wc, T_wc=T_wc, up_vec=up_vec,
                X_world=X_world, Y_world=Y_world, Z_world=Z_world,
                baseline_up_angle=baseline_up_angle, overall_rms_mm=overall_rms_mm,
                rms_x=rms_x, rms_y=rms_y, rms_z=rms_z,
                guardrail_a_pass=guardrail_a_pass, guardrail_b_pass=guardrail_b_pass,
                overall_pass=overall_pass)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = []

    def emit(line: str = "") -> None:
        print(line)
        report.append(line)

    emit("=" * 78)
    emit("WORLD-FRAME REGISTRATION VALIDATION -- 2026_07_15_gym")
    emit("up_vec source: solve_world_frame() (checkerboard-pose solve), same")
    emit("method as the 2026_07_21_gym validation (no manual vertical-line click)")
    emit("=" * 78)
    emit("")

    K0, D0 = load_intrinsics(INTRINSICS_DIR / "cam0_intrinsics_fisheye.npz", "cam0")
    K1, D1 = load_intrinsics(INTRINSICS_DIR / "cam1_intrinsics_fisheye.npz", "cam1")

    if not EXTRINSICS_PATH.is_file():
        emit(f"*** UNEXPECTED FAILURE: extrinsics file not found: {EXTRINSICS_PATH} ***")
        sys.exit(1)
    ext = np.load(EXTRINSICS_PATH)
    R, T = ext["R"].astype(np.float64), ext["T"].astype(np.float64)
    baseline_mm = float(np.linalg.norm(T))
    baseline_dir = normalize(T)
    emit(f"Extrinsics: {EXTRINSICS_PATH}")
    emit(f"  baseline |T| = {baseline_mm:.2f} mm (expect ~{BASELINE_EXPECT_MM:.0f} mm)")
    baseline_pct_diff = 100.0 * abs(baseline_mm - BASELINE_EXPECT_MM) / BASELINE_EXPECT_MM
    if baseline_pct_diff > BASELINE_TOL_PCT:
        emit(f"*** UNEXPECTED FAILURE: baseline {baseline_pct_diff:.1f}% off nominal -- "
             f"extrinsics file looks wrong, stopping. ***")
        report_path = OUT_DIR / "world_frame_validation_report.txt"
        report_path.write_text("\n".join(report) + "\n")
        sys.exit(1)
    emit("")

    candidates = []
    for stem in CANDIDATES:
        r = validate_candidate(stem, K0, D0, K1, D1, R, T, baseline_dir, emit)
        if r is not None:
            candidates.append(r)

    passing = [c for c in candidates if c["overall_pass"]]
    if not passing:
        emit("*** ALL candidates FAILED guardrails (or failed to load/detect) -- "
             "STOPPING per task instructions, not silently proceeding. ***")
        report_path = OUT_DIR / "world_frame_validation_report.txt"
        report_path.write_text("\n".join(report) + "\n")
        sys.exit(1)

    best = min(passing, key=lambda c: c["overall_rms_mm"])
    emit(f"WINNER = {best['img_stem']} (overall_rms={best['overall_rms_mm']:.2f} mm, "
         f"baseline_up_angle={best['baseline_up_angle']:.2f} deg)")
    emit("")

    report_path = OUT_DIR / "world_frame_validation_report.txt"
    report_path.write_text("\n".join(report) + "\n")
    print(f"\n-> {report_path}")

    out_npz = OUT_DIR / "registration_world_transform.npz"
    np.savez(out_npz, R_wc=best["R_wc"], T_wc=best["T_wc"], up_vec=best["up_vec"],
             X_world=best["X_world"], Y_world=best["Y_world"], Z_world=best["Z_world"],
             img_stem=best["img_stem"])
    print(f"-> {out_npz}")


if __name__ == "__main__":
    main()
