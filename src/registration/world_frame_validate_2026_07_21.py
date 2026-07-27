# world_frame_validate_2026_07_21.py
#
# Validate world-frame registration for the 2026_07_21_gym session (part of
# the flight_velocity_angle_binner task). Two registrations exist because the
# rig's world frame changed mid-session (registration1: flights 1-60,
# registration2: flights 61+), each with 2 candidate checkerboard image pairs
# (cam0/cam1) to choose between.
#
# world_frame_precision_single.py's guardrail pipeline derives "up" from a
# manually-clicked vertical-line CSV -- that data does not exist for this
# session and would require an interactive GUI click that cannot be produced
# non-interactively (see claude/claude_logs/2026-07-25_flight_velocity_angle_
# binner_worklog.md for the full finding). Per explicit user decision, this
# script instead derives up_vec from src/stereo/world_registration.py's
# solve_world_frame() (pure checkerboard-pose solve via solvePnP, no manual
# click needed -- already used elsewhere in this codebase, e.g.
# predict_sweep.py), then re-runs world_frame_precision_single.py's REUSABLE
# guardrail checks (baseline-perpendicular-to-up angle, weak-axis-must-be-
# width, Umeyama corner-residual precision per world axis) against that
# up_vec. Those functions are imported, not re-derived or modified.
#
# Usage:
#   python src/registration/world_frame_validate_2026_07_21.py

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
EXTRINSICS_PATH = ROOT / "calibration_outputs/2026_07_21/test2/stereo_extrinsic.npz"
WORLD_REG_DIR = ROOT / "data/2026_07_21_gym/world_registration"
OUT_DIR = ROOT / "data/2026_07_21_gym/flight_binning/world_frame_validation"

BASELINE_UP_ANGLE_TOL_DEG = 10.0   # from world_frame_precision_single.py
BASELINE_EXPECT_MM = 850.0
BASELINE_TOL_PCT = 10.0            # loose gate: catches a badly wrong extrinsics file, not a QA number

REGISTRATIONS = {
    "registration1": ["img_0031", "img_0032"],
    "registration2": ["img_0033", "img_0034"],
}


def validate_candidate(reg_name, img_stem, K0, D0, K1, D1, R, T, baseline_dir, emit):
    cam0_path = WORLD_REG_DIR / "cam0" / reg_name / f"{img_stem}.png"
    cam1_path = WORLD_REG_DIR / "cam1" / reg_name / f"{img_stem}.png"

    emit(f"--- {reg_name} / {img_stem} ---")

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

    # up_vec derivation: see worklog for the d(world_y)/d(cam) derivation --
    # matches predict_sweep.py's own world_up_in_cam = -R_wc[:, 1].
    up_vec = -R_wc[:, 1]
    up_vec = up_vec / np.linalg.norm(up_vec)

    baseline_up_angle = float(np.degrees(np.arccos(np.clip(np.dot(baseline_dir, up_vec), -1.0, 1.0))))
    emit(f"  angle(baseline_dir, up_vec) = {baseline_up_angle:.2f} deg "
         f"(expect ~90, tol {BASELINE_UP_ANGLE_TOL_DEG})")
    guardrail_a_pass = abs(baseline_up_angle - 90.0) <= BASELINE_UP_ANGLE_TOL_DEG
    if not guardrail_a_pass:
        emit(f"    *** GUARDRAIL (a) FAIL: baseline/up not ~perpendicular -- "
             f"rig appears yawed or up_vec is wrong ***")

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
        emit(f"    *** GUARDRAIL (b) FAIL: weakest axis is not Y_world -- axis "
             f"identity likely wrong, don't trust up_vec/X_world/Y_world/Z_world above ***")

    overall_pass = guardrail_a_pass and guardrail_b_pass
    emit(f"  RESULT: {'PASS' if overall_pass else 'FAIL'}")
    emit("")

    return dict(reg_name=reg_name, img_stem=img_stem, R_wc=R_wc, T_wc=T_wc,
                up_vec=up_vec, X_world=X_world, Y_world=Y_world, Z_world=Z_world,
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
    emit("WORLD-FRAME REGISTRATION VALIDATION -- 2026_07_21_gym")
    emit("up_vec source: solve_world_frame() (checkerboard-pose solve), NOT a")
    emit("manually-clicked vertical line (unavailable for this session -- see worklog)")
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

    results = {}
    any_failed = False
    for reg_name, stems in REGISTRATIONS.items():
        emit(f"=== {reg_name} ===")
        candidates = []
        for stem in stems:
            r = validate_candidate(reg_name, stem, K0, D0, K1, D1, R, T, baseline_dir, emit)
            if r is not None:
                candidates.append(r)

        passing = [c for c in candidates if c["overall_pass"]]
        if not passing:
            emit(f"*** {reg_name}: BOTH candidates FAILED guardrails (or failed to load/detect) "
                 f"-- STOPPING per task instructions, not silently proceeding. ***")
            results[reg_name] = None
            any_failed = True
            continue

        best = min(passing, key=lambda c: c["overall_rms_mm"])
        emit(f"{reg_name}: WINNER = {best['img_stem']} "
             f"(overall_rms={best['overall_rms_mm']:.2f} mm, "
             f"baseline_up_angle={best['baseline_up_angle']:.2f} deg)")
        emit("")
        results[reg_name] = best

    report_path = OUT_DIR / "world_frame_validation_report.txt"
    report_path.write_text("\n".join(report) + "\n")
    print(f"\n-> {report_path}")

    for reg_name, best in results.items():
        if best is None:
            continue
        out_npz = OUT_DIR / f"{reg_name}_world_transform.npz"
        np.savez(out_npz, R_wc=best["R_wc"], T_wc=best["T_wc"], up_vec=best["up_vec"],
                 X_world=best["X_world"], Y_world=best["Y_world"], Z_world=best["Z_world"],
                 img_stem=best["img_stem"])
        print(f"-> {out_npz}")

    if any_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
