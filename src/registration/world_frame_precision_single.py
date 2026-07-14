"""
Report triangulation PRECISION for board img36 (~5 m), resolved along
operational world axes rather than the camera frame, using a clicked
vertical line to fix "up" and the stereo baseline to fix the horizontal
person -> rebounder axis.

World axes (camera-frame vectors, built in STEP 1 below):
    X_world = person -> rebounder (horizontal, ball left-right travel)  - STRONG
    Y_world = rebounder width / depth (camera look direction)           - WEAK
    Z_world = vertical up                                              - STRONG

Reuses (does not reimplement) from src/calibration/extrinsic/solve_extrinsic.py:
    PATTERN_SIZE, SQUARE_SIZE_MM, OBJP, detect_corners(), load_intrinsics()
and from src/stereo/triangulate.py: triangulate_points() (which fisheye-
undistorts internally via cv2.fisheye.undistortPoints - this script never
calls that directly, so the clicked vertical-line points are undistorted
exactly the same way as the board corners).

Single-board caveats (see STEP 4 / printed report):
  - One board at one depth/region: this is 5m-LOCAL precision, not a
    volume-wide or system-wide figure.
  - The clicked vertical line is assumed to be a truly vertical physical
    edge.
  - The weak (width) axis precision is somewhat optimistic because the
    board's own tilt mixes the strong axes into the weak one.

Usage:
    python src/registration/world_frame_precision_single.py
    python src/registration/world_frame_precision_single.py \
        --extrinsics calibration_outputs/2026_07_11_session/stereo_extrinsic.npz

Inputs:
    data/2026_07_12_session/validation/{cam0,cam1}/img_0036.png  (board)
    data/2026_07_12_session/validation/results/world_frame/vertical_{cam0,cam1}.csv
        (from label_vertical_line.py: point_id,u,v rows for V_top/V_bottom)
    calibration_outputs/cam0_intrinsics_fisheye.npz, cam1_intrinsics_fisheye.npz
    calibration_outputs/2026_07_12_session/stereo_extrinsic.npz  (R, T)

Outputs (data/2026_07_12_session/validation/results/world_frame/):
    world_frame_precision.txt
    world_frame_precision.csv
"""

import argparse
import csv
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.stereo.triangulate import triangulate_points
from src.calibration.extrinsic.solve_extrinsic import (
    PATTERN_SIZE, SQUARE_SIZE_MM, OBJP, detect_corners, load_intrinsics,
)

INTRINSICS_DIR = ROOT / "calibration_outputs"
VALIDATION_DIR = ROOT / "data/2026_07_12_session/validation"
WORLD_FRAME_DIR = VALIDATION_DIR / "results/world_frame"

DEFAULT_BOARD_CAM0 = VALIDATION_DIR / "cam0/img_0036.png"
DEFAULT_BOARD_CAM1 = VALIDATION_DIR / "cam1/img_0036.png"
DEFAULT_VERTICAL_CAM0_CSV = WORLD_FRAME_DIR / "vertical_cam0.csv"
DEFAULT_VERTICAL_CAM1_CSV = WORLD_FRAME_DIR / "vertical_cam1.csv"
DEFAULT_EXTRINSICS = ROOT / "calibration_outputs/2026_07_12_session/stereo_extrinsic.npz"

REPORT_TXT_NAME = "world_frame_precision.txt"
REPORT_CSV_NAME = "world_frame_precision.csv"

EXPECTED_BASELINE_XYZ = (848.0, -3.0, -16.0)  # nominal expectation, printed only, never gates logic

# Guardrail tolerances
BASELINE_UP_ANGLE_TOL_DEG = 10.0  # deviation from 90 deg between baseline_dir and up_vec

N_CORNERS = PATTERN_SIZE[0] * PATTERN_SIZE[1]


# ---- vertical-line CSV loading ---------------------------------------------------

def load_vertical_csv(path: Path) -> dict:
    """Return {point_id: (u, v)} - same 'point_id,u,v' format label_vertical_line.py writes."""
    if not path.is_file():
        raise FileNotFoundError(f"Vertical-line CSV not found: {path}")
    with open(path, newline="") as f:
        points = {r["point_id"]: (float(r["u"]), float(r["v"])) for r in csv.DictReader(f)}
    missing = [pid for pid in ("V_top", "V_bottom") if pid not in points]
    if missing:
        raise KeyError(f"{path}: missing point(s) {missing} (expected V_top and V_bottom)")
    return points


# ---- geometry (Umeyama similarity fit, numpy SVD - no new deps) -------------------

def umeyama_alignment(src, dst, with_scale):
    """
    Closed-form least-squares similarity alignment via SVD (Umeyama 1991).
    Finds R, t, (s) minimizing sum_i || s * R @ src_i + t - dst_i ||^2.
    src, dst: (N, 3). Returns (R (3,3), t (3,), s (float, 1.0 if with_scale=False)).
    """
    n = src.shape[0]
    mu_src = src.mean(axis=0)
    mu_dst = dst.mean(axis=0)
    src_c = src - mu_src
    dst_c = dst - mu_dst

    cov = (dst_c.T @ src_c) / n
    U, D, Vt = np.linalg.svd(cov)
    S = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        S[2, 2] = -1.0
    R = U @ S @ Vt

    if with_scale:
        var_src = (src_c ** 2).sum() / n
        s = float(np.trace(np.diag(D) @ S) / var_src)
    else:
        s = 1.0

    t = mu_dst - s * (R @ mu_src)
    return R, t, s


def apply_similarity(points, R, t, s):
    return s * (points @ R.T) + t


def normalize(v):
    return v / np.linalg.norm(v)


# ---- CSV output --------------------------------------------------------------------

def write_csv(path, header, row):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerow(row)
    return path


# ---- main -------------------------------------------------------------------------

def parse_args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--board-cam0", default=str(DEFAULT_BOARD_CAM0), help="cam0 (right) board image")
    ap.add_argument("--board-cam1", default=str(DEFAULT_BOARD_CAM1), help="cam1 (left) board image")
    ap.add_argument("--vertical-cam0-csv", default=str(DEFAULT_VERTICAL_CAM0_CSV),
                     help="cam0 V_top/V_bottom CSV from label_vertical_line.py")
    ap.add_argument("--vertical-cam1-csv", default=str(DEFAULT_VERTICAL_CAM1_CSV),
                     help="cam1 V_top/V_bottom CSV from label_vertical_line.py")
    ap.add_argument("--extrinsics", default=str(DEFAULT_EXTRINSICS),
                     help="stereo_extrinsic.npz to use (R, T) - only this one solve is run")
    ap.add_argument("--intrinsics-dir", default=str(INTRINSICS_DIR),
                     help="Folder containing cam0/cam1_intrinsics_fisheye.npz")
    ap.add_argument("--output-dir", default=str(WORLD_FRAME_DIR),
                     help="Folder to write world_frame_precision.txt/.csv into")
    return ap.parse_args()


def main():
    args = parse_args()
    board_cam0 = Path(args.board_cam0)
    board_cam1 = Path(args.board_cam1)
    vertical_cam0_csv = Path(args.vertical_cam0_csv)
    vertical_cam1_csv = Path(args.vertical_cam1_csv)
    extrinsics_path = Path(args.extrinsics)
    intrinsics_dir = Path(args.intrinsics_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    report = []

    def emit(line: str = "") -> None:
        print(line)
        report.append(line)

    emit("=" * 78)
    emit("WORLD-FRAME PRECISION (single board, img36 ~5m)")
    emit("=" * 78)
    emit(f"Board pair:      {board_cam0}  /  {board_cam1}")
    emit(f"Vertical CSVs:   {vertical_cam0_csv}  /  {vertical_cam1_csv}")
    emit(f"Extrinsics:      {extrinsics_path}")
    emit("")

    K0, D0 = load_intrinsics(intrinsics_dir / "cam0_intrinsics_fisheye.npz", "cam0 (right)")
    K1, D1 = load_intrinsics(intrinsics_dir / "cam1_intrinsics_fisheye.npz", "cam1 (left)")
    emit("")

    if not extrinsics_path.is_file():
        raise FileNotFoundError(f"Extrinsics file not found: {extrinsics_path}")
    ext = np.load(extrinsics_path)
    R, T = ext["R"].astype(np.float64), ext["T"].astype(np.float64)

    # ================================================================
    # STEP 1 - build the world frame
    # ================================================================
    emit("-" * 78)
    emit("STEP 1 - build the world frame")
    emit("-" * 78)

    # -- 1a: vertical line -> up_vec -----------------------------------------------
    v0 = load_vertical_csv(vertical_cam0_csv)
    v1 = load_vertical_csv(vertical_cam1_csv)

    pts0 = np.array([v0["V_top"], v0["V_bottom"]], dtype=np.float64)  # (2,2): row0=top, row1=bottom
    pts1 = np.array([v1["V_top"], v1["V_bottom"]], dtype=np.float64)
    vert_tri = triangulate_points(pts0, pts1, K0, D0, K1, D1, R, T)  # (2,3): [V_top3D, V_bottom3D]
    v_top3d, v_bottom3d = vert_tri[0], vert_tri[1]

    raw_up = v_top3d - v_bottom3d
    raw_len_mm = float(np.linalg.norm(raw_up))
    raw_up_norm = normalize(raw_up)
    # Camera-frame convention (P1=[I|0], the raw cam0/right frame): image v grows
    # downward, so "up" should have a negative Y component. Flip if the raw
    # top-bottom vector came out with positive Y instead.
    if raw_up_norm[1] > 0:
        up_vec = -raw_up_norm
        flip_note = f"raw (V_top - V_bottom) had +Y component ({raw_up[1]:+.1f} mm) -> flipped sign to point up (-Y)"
    else:
        up_vec = raw_up_norm
        flip_note = f"raw (V_top - V_bottom) already had -Y component ({raw_up[1]:+.1f} mm) -> no flip needed"

    emit(f"  V_top3D    = {v_top3d}")
    emit(f"  V_bottom3D = {v_bottom3d}")
    emit(f"  |V_top3D - V_bottom3D| = {raw_len_mm:.1f} mm (vertical baseline used to fix 'up')")
    emit(f"  up_vec (camera frame, normalized) = {up_vec}")
    emit(f"  Sign convention: {flip_note}")
    emit("")

    # -- 1b: baseline -> baseline_dir -----------------------------------------------
    baseline_mm = float(np.linalg.norm(T))
    baseline_dir = normalize(T)
    dominant_axis = int(np.argmax(np.abs(T)))
    axis_name = ["X", "Y", "Z"][dominant_axis]
    emit(f"  T (mm) = ({T[0]:.2f}, {T[1]:.2f}, {T[2]:.2f})   |T| = {baseline_mm:.2f} mm")
    emit(f"  Expected (nominal): ~{EXPECTED_BASELINE_XYZ}")
    if dominant_axis == 0:
        emit(f"  Dominant component: {axis_name} - matches a horizontal side-by-side rig. OK.")
    else:
        emit(f"  *** LOUD WARNING ***: dominant baseline component is {axis_name}, not X. The "
             f"'baseline = person->rebounder, horizontal' assumption below is NOT justified by this "
             f"extrinsics file - check rig geometry before trusting X_world/Y_world.")
    emit(f"  baseline_dir (camera frame, normalized) = {baseline_dir}")
    emit("")

    # -- 1c: orthonormal world axes --------------------------------------------------
    Z_world = up_vec
    X_world = normalize(baseline_dir - np.dot(baseline_dir, Z_world) * Z_world)
    Y_world = np.cross(Z_world, X_world)

    emit("  World axes (camera/cam0-right frame vectors):")
    emit(f"    X_world (person -> rebounder, STRONG) = {X_world}")
    emit(f"    Y_world (width/depth, WEAK)            = {Y_world}")
    emit(f"    Z_world (vertical up, STRONG)          = {Z_world}")
    emit("")

    # ================================================================
    # STEP 2 - guardrails (part 1: computable before the board fit)
    # ================================================================
    emit("-" * 78)
    emit("STEP 2 - guardrails")
    emit("-" * 78)

    # -- 2a: baseline vs up_vec should be ~90 deg -----------------------------------
    baseline_up_angle = float(np.degrees(np.arccos(np.clip(np.dot(baseline_dir, up_vec), -1.0, 1.0))))
    emit(f"  (a) angle(baseline_dir, up_vec) = {baseline_up_angle:.2f} deg (expected ~90 deg, rig square side-on)")
    if abs(baseline_up_angle - 90.0) > BASELINE_UP_ANGLE_TOL_DEG:
        emit(f"      *** LOUD WARNING ***: deviates from 90 deg by more than {BASELINE_UP_ANGLE_TOL_DEG} deg - "
             f"the rig appears YAWED, so 'baseline = person->rebounder' may not be a valid axis assumption.")
    else:
        emit(f"      within {BASELINE_UP_ANGLE_TOL_DEG} deg tolerance - OK.")
    emit("")

    # -- 2c: tilt of the vertical line off image-vertical (raw pixel space, per camera) --
    def pixel_tilt_deg(pts):
        du = abs(pts[0, 0] - pts[1, 0])
        dv = abs(pts[0, 1] - pts[1, 1])
        return float(np.degrees(np.arctan2(du, dv))) if dv > 0 else float("nan")

    tilt_cam0 = pixel_tilt_deg(pts0)
    tilt_cam1 = pixel_tilt_deg(pts1)
    emit(f"  (c) clicked vertical-line tilt off image-vertical (raw pixel space, sanity read only):")
    emit(f"      cam0: {tilt_cam0:.2f} deg     cam1: {tilt_cam1:.2f} deg")
    emit("")

    # ================================================================
    # STEP 3 - per-axis precision (board img36)
    # ================================================================
    emit("-" * 78)
    emit("STEP 3 - per-axis precision (board img36)")
    emit("-" * 78)

    g0 = cv2.imread(str(board_cam0), cv2.IMREAD_GRAYSCALE)
    g1 = cv2.imread(str(board_cam1), cv2.IMREAD_GRAYSCALE)
    if g0 is None:
        raise FileNotFoundError(f"Could not read board image: {board_cam0}")
    if g1 is None:
        raise FileNotFoundError(f"Could not read board image: {board_cam1}")

    found0, c0 = detect_corners(g0)
    found1, c1 = detect_corners(g1)
    if not (found0 and found1):
        missing = [n for n, f in (("cam0", found0), ("cam1", found1)) if not f]
        raise RuntimeError(f"Board not detected in {', '.join(missing)}")

    tri = triangulate_points(c0, c1, K0, D0, K1, D1, R, T)  # (77, 3), camera/cam0-right frame
    mean_z_mm = float(tri[:, 2].mean())

    # Similarity fit: known grid (OBJP, board frame) -> tri (camera frame), so the
    # residual comes out directly in camera-frame coordinates and can be rotated
    # into the (camera-frame) world axes above.
    R_sim, t_sim, s_sim = umeyama_alignment(OBJP, tri, with_scale=True)
    pred_cam = apply_similarity(OBJP, R_sim, t_sim, s_sim)
    resid_cam = tri - pred_cam  # (77, 3), camera frame

    overall_rms_mm = float(np.sqrt(np.mean(np.sum(resid_cam ** 2, axis=1))))

    proj_x = resid_cam @ X_world
    proj_y = resid_cam @ Y_world
    proj_z = resid_cam @ Z_world
    rms_person_rebounder_mm = float(np.sqrt(np.mean(proj_x ** 2)))
    rms_width_mm = float(np.sqrt(np.mean(proj_y ** 2)))
    rms_vertical_mm = float(np.sqrt(np.mean(proj_z ** 2)))

    emit(f"  Detected {N_CORNERS} corners in both views, triangulated, similarity-fit to the known "
         f"{PATTERN_SIZE[0]}x{PATTERN_SIZE[1]} grid (square = {SQUARE_SIZE_MM} mm).")
    emit(f"  Board mean depth (camera-frame Z) = {mean_z_mm:.0f} mm")
    emit(f"  Fitted similarity scale s = {s_sim:.4f} (single-board -> noisy local estimate, do not over-read)")
    emit(f"  Overall 3D RMS residual = {overall_rms_mm:.2f} mm")
    emit("")
    emit(f"    rms_person_rebounder_mm (X_world, STRONG) = {rms_person_rebounder_mm:.2f} mm")
    emit(f"    rms_width_mm            (Y_world, WEAK)   = {rms_width_mm:.2f} mm")
    emit(f"    rms_vertical_mm         (Z_world, STRONG) = {rms_vertical_mm:.2f} mm")
    emit("")

    # -- 2b: weak axis must be Y_world (largest-spread axis check) ------------------
    axis_rms = {"X_world": rms_person_rebounder_mm, "Y_world": rms_width_mm, "Z_world": rms_vertical_mm}
    weakest_axis = max(axis_rms, key=axis_rms.get)
    emit(f"  (b) largest-spread axis = {weakest_axis} (rms values: {axis_rms})")
    if weakest_axis != "Y_world":
        emit(f"      *** LOUD WARNING ***: the largest-spread axis is {weakest_axis}, not Y_world - "
             f"the axis identity above is likely WRONG (check the up_vec / baseline_dir construction "
             f"in STEP 1 before trusting any per-axis number in this report).")
    else:
        emit("      largest spread is Y_world (width/depth), as expected for this rig geometry - OK.")
    emit("")

    # ================================================================
    # STEP 4 - caveats
    # ================================================================
    emit("-" * 78)
    emit("STEP 4 - caveats")
    emit("-" * 78)
    emit("  - Single board at one depth/region: the numbers above are 5m-LOCAL precision, NOT a")
    emit("    volume-wide or system-wide precision figure.")
    emit("  - 'Up' comes from a clicked wall/plumb edge assumed to be truly vertical; the click was")
    emit("    fisheye-undistorted (via triangulate_points) before triangulation, same as the board corners.")
    emit("  - rms_width_mm (weak axis) is somewhat OPTIMISTIC: the board's own tilt mixes the strong")
    emit("    (X/Z) axes into the weak (Y) axis. Treat it as confirming the +/-100mm budget is met,")
    emit("    not as a definitive weak-axis number.")
    emit("")

    # ---- write outputs ------------------------------------------------------------
    report_txt_path = output_dir / REPORT_TXT_NAME
    report_txt_path.write_text("\n".join(report) + "\n")
    emit(f"Report written to {report_txt_path}")

    csv_path = output_dir / REPORT_CSV_NAME
    write_csv(
        csv_path,
        ["board", "depth_mm", "rms_person_rebounder_mm", "rms_width_mm", "rms_vertical_mm",
         "overall_rms_mm", "similarity_scale", "baseline_up_angle_deg",
         "vertical_tilt_cam0_deg", "vertical_tilt_cam1_deg"],
        ["img_0036", mean_z_mm, rms_person_rebounder_mm, rms_width_mm, rms_vertical_mm,
         overall_rms_mm, s_sim, baseline_up_angle, tilt_cam0, tilt_cam1],
    )
    print(f"CSV written to {csv_path}")


if __name__ == "__main__":
    main()
