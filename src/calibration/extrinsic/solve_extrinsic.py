"""
Stereo EXTRINSIC calibration for the two-camera fisheye rig, holding the
already-solved intrinsics FIXED (cv2.fisheye.CALIB_FIX_INTRINSIC). Also runs
an independent triangulation/reprojection check as a smoke test of the same
triangulation pipeline that will be reused for ball 3D localization.

Rig convention: cam0 = RIGHT camera, cam1 = LEFT camera. cam0 is passed as
the FIRST camera to cv2.fisheye.stereoCalibrate, cam1 as the SECOND, so the
solved (R, T) map points from the cam0/right frame into the cam1/left frame:
    X_left = R @ X_right + T

FISHEYE ONLY: uses cv2.fisheye.stereoCalibrate / undistortPoints / projectPoints
throughout. Never mix in the plain (pinhole) cv2.stereoCalibrate or cv2.undistort -
that silently produces plausible-but-wrong numbers for a fisheye rig.

IMPORTANT: SQUARE_SIZE_MM below must be your CALIPER-MEASURED checkerboard
square size, not the nominal printed value.

Run from anywhere:
    python src/calibration/extrinsic/solve_extrinsic.py

Inputs (already-solved intrinsics - NOT re-estimated here):
    calibration_outputs/cam0_intrinsics_fisheye.npz  (K, D) - cam0 / right
    calibration_outputs/cam1_intrinsics_fisheye.npz  (K, D) - cam1 / left

Matched checkerboard pairs (same index = same physical board pose):
    data/2026_07_11_gym_session/extrinsic/cam0/img_XXXX.png  (right)
    data/2026_07_11_gym_session/extrinsic/cam1/img_XXXX.png  (left)

Outputs (dated per-session subfolder, intrinsics above are never overwritten):
    calibration_outputs/2026_07_11_session/stereo_extrinsic.npz  (R, T, image_size,
        square_size_mm, first/second camera labels, rms)
    calibration_outputs/2026_07_11_session/stereo_extrinsic.txt  (human-readable
        summary, including the convergence sweep table/verdict)
    calibration_outputs/2026_07_11_session/corner_order_debug_cam0.png / _cam1.png
        (corner index 0 marked on the first kept pair - confirm it's the same
        physical corner in both images; a mismatch here is the #1 cause of a
        high stereo RMS)
    calibration_outputs/2026_07_11_session/extrinsic_convergence.png
        (baseline and RMS vs number of pairs used - diagnoses whether the
        captured tilt/pose range was wide enough to constrain the extrinsic;
        RMS alone can look fine even when the pose range is too narrow)
"""

import argparse
import sys
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# -- Rig / checkerboard constants --------------------------------------------
PATTERN_SIZE = (7, 11)  # internal corners (columns, rows)
SQUARE_SIZE_MM = 67.5  # <-- CALIPER-MEASURED value, not the nominal printed size
IMAGE_SIZE = (1456, 1088)  # (width, height)

EXPECTED_BASELINE_MM = 850.0
RMS_PASS_THRESHOLD_PX = 1.0
MIN_PAIRS_WARN = 10
TRIANGULATION_SAMPLE_PAIRS = 5

# -- Per-pair pose-consistency outlier rejection -----------------------------
# A pair can pass per-camera corner detection in both views yet still be
# unusable for the joint solve: e.g. cv2.findChessboardCornersSB starts its
# corner numbering from the "wrong" physical corner in one view for that
# specific pose (a 180-degree in-plane relabeling), or the board was nudged
# between the two (sequential, not simultaneous) per-camera shutter triggers.
# Both symptoms show up as a per-pair implied cam0->cam1 rigid transform
# (from independent mono solvePnP in each view) that is wildly inconsistent
# with the rest of the kept pairs, even though every pair individually
# reprojects fine. Flag and drop those before stereoCalibrate rather than
# letting one bad pair make the whole joint solve fail to converge.
POSE_OUTLIER_ANGLE_DEG = 15.0  # normal rig-only variation is well under 1 degree
POSE_OUTLIER_BASELINE_PCT = 30.0  # vs. the per-session median implied baseline

# -- Baseline convergence sweep constants ------------------------------------
CONVERGENCE_SEED = 0  # fixed shuffle seed - curve reflects information content, not capture order
CONVERGENCE_MIN_N = 4  # practical minimum pair count for stereoCalibrate
CONVERGENCE_LAST_K = 3  # how many trailing N values define the "tail" for the verdict
CONVERGENCE_SPREAD_TOL_MM = 15.0  # tail baseline spread must be under this to call it converged
CONVERGENCE_BASELINE_TOL_PCT = 2.0  # final baseline must be within this % of EXPECTED_BASELINE_MM

CRITERIA = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-6)

OBJP = np.zeros((PATTERN_SIZE[0] * PATTERN_SIZE[1], 3), np.float64)
OBJP[:, :2] = np.mgrid[0:PATTERN_SIZE[0], 0:PATTERN_SIZE[1]].T.reshape(-1, 2) * SQUARE_SIZE_MM

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from src.stereo.triangulate import triangulate_points

INTRINSICS_DIR = ROOT / "calibration_outputs"  # cam0/cam1_intrinsics_fisheye.npz live here, never written to

# Overwritten in main() from CLI args - defaults match the original 2026-07-11 session.
OUTPUT_DIR = ROOT / "calibration_outputs/2026_07_11_session"
CAPTURE_DIR = ROOT / "data/2026_07_11_gym_session/extrinsic"
CAM0_DIR = CAPTURE_DIR / "cam0"
CAM1_DIR = CAPTURE_DIR / "cam1"
OUTPUT_NPZ = OUTPUT_DIR / "stereo_extrinsic.npz"
OUTPUT_TXT = OUTPUT_DIR / "stereo_extrinsic.txt"
DEBUG_CORNER0_CAM0 = OUTPUT_DIR / "corner_order_debug_cam0.png"
DEBUG_CORNER0_CAM1 = OUTPUT_DIR / "corner_order_debug_cam1.png"
CONVERGENCE_PLOT_PATH = OUTPUT_DIR / "extrinsic_convergence.png"


def detect_corners(gray):
    """
    Detect the PATTERN_SIZE internal chessboard corners in a grayscale image.
    Same block as calibrate_intrinsic.py / check_coverage.py / convergence_test.py:
    SB first (already sub-pixel accurate, more robust to fisheye edge distortion);
    falls back to the classic detector + cornerSubPix only if SB fails.

    Returns (found: bool, corners: np.ndarray of shape (N, 2) or None).
    """
    found, corners = cv2.findChessboardCornersSB(
        gray, PATTERN_SIZE,
        flags=cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY,
    )
    if found:
        return True, corners.reshape(-1, 2)

    found, corners = cv2.findChessboardCorners(
        gray, PATTERN_SIZE,
        flags=cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE,
    )
    if found:
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
        corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
        return True, corners.reshape(-1, 2)

    return False, None


def load_intrinsics(path, label):
    if not path.is_file():
        raise FileNotFoundError(f"{label}: intrinsics file not found: {path}")
    data = np.load(path)
    print(f"{label}: loaded {path.name}  (keys: {list(data.keys())})")
    if "K" not in data or "D" not in data:
        raise KeyError(f"{label}: expected keys 'K' and 'D' in {path}, found {list(data.keys())}")
    return data["K"].astype(np.float64), data["D"].astype(np.float64)


def find_matched_pairs():
    cam0_paths = {p.stem: p for p in CAM0_DIR.glob("img_*.png")}
    cam1_paths = {p.stem: p for p in CAM1_DIR.glob("img_*.png")}

    only_cam1 = sorted(set(cam1_paths) - set(cam0_paths))
    only_cam0 = sorted(set(cam0_paths) - set(cam1_paths))
    if only_cam0:
        print(f"WARNING: {len(only_cam0)} index(es) present in cam0 but not cam1 (unmatched, skipped): {only_cam0}")
    if only_cam1:
        print(f"WARNING: {len(only_cam1)} index(es) present in cam1 but not cam0 (unmatched, skipped): {only_cam1}")

    common = sorted(set(cam0_paths) & set(cam1_paths))
    return [(idx, cam0_paths[idx], cam1_paths[idx]) for idx in common]


def save_corner0_debug(idx, path0, path1, c0, c1):
    img0 = cv2.imread(str(path0))
    img1 = cv2.imread(str(path1))
    for img, corners, out_path in ((img0, c0, DEBUG_CORNER0_CAM0), (img1, c1, DEBUG_CORNER0_CAM1)):
        pt = tuple(int(v) for v in corners[0])
        cv2.circle(img, pt, 16, (0, 0, 255), 3)
        cv2.putText(img, "corner 0", (pt[0] + 20, pt[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
        cv2.imwrite(str(out_path), img)

    print(f"Corner-order debug images saved from pair '{idx}':")
    print(f"  {DEBUG_CORNER0_CAM0}")
    print(f"  {DEBUG_CORNER0_CAM1}")
    print("  Open both and confirm the marked corner is the SAME physical checkerboard")
    print("  corner in each view. If not, correspondence between cam0/cam1 is flipped")
    print("  and the solve below cannot be trusted for that pair (or possibly all pairs,")
    print("  if the mismatch is systematic).\n")


def mono_solve_pose(imgp, K, D):
    """Fisheye-undistort to normalized coords, then solvePnP against identity K."""
    undist = cv2.fisheye.undistortPoints(imgp, K, D)
    _, rvec, tvec = cv2.solvePnP(OBJP.reshape(-1, 1, 3), undist, np.eye(3), None,
                                  flags=cv2.SOLVEPNP_ITERATIVE)
    R, _ = cv2.Rodrigues(rvec)
    return R, tvec.reshape(3)


def find_pose_outliers(kept, imgpoints0, imgpoints1, K0, D0, K1, D1):
    """
    Independent mono solvePnP per view, per pair, then the implied cam0->cam1
    rigid transform (R_rel, T_rel). Flags pairs whose implied baseline or
    rotation deviates sharply from the per-session median - see the
    POSE_OUTLIER_* constants above for why this catches corner-order flips
    and non-simultaneous captures that per-view detection alone cannot.
    Returns (outlier_positions: set[int], report_lines: list[str]).
    """
    baselines, angles, rel = [], [], []
    for imgp0, imgp1 in zip(imgpoints0, imgpoints1):
        R0, t0 = mono_solve_pose(imgp0, K0, D0)
        R1, t1 = mono_solve_pose(imgp1, K1, D1)
        R_rel = R1 @ R0.T
        T_rel = t1 - R_rel @ t0
        baselines.append(float(np.linalg.norm(T_rel)))
        angles.append(float(np.degrees(np.arccos(np.clip((np.trace(R_rel) - 1) / 2, -1, 1)))))
        rel.append((R_rel, T_rel))

    median_baseline = float(np.median(baselines))
    median_angle = float(np.median(angles))

    outliers = set()
    report_lines = []
    for i, idx in enumerate(kept):
        baseline_dev_pct = 100.0 * abs(baselines[i] - median_baseline) / median_baseline
        angle_dev_deg = abs(angles[i] - median_angle)
        if angle_dev_deg > POSE_OUTLIER_ANGLE_DEG or baseline_dev_pct > POSE_OUTLIER_BASELINE_PCT:
            outliers.add(i)
            line = (f"  {idx}: REMOVED (pose-outlier) - implied baseline={baselines[i]:.1f} mm "
                     f"(median {median_baseline:.1f} mm, {baseline_dev_pct:+.0f}%), "
                     f"implied rotation={angles[i]:.2f} deg (median {median_angle:.2f} deg). "
                     f"Likely a corner-order mismatch between cam0/cam1 for this pose, or the "
                     f"board moved between the sequential cam0/cam1 shutter triggers.")
            print(line)
            report_lines.append(line.strip())

    return outliers, report_lines


def triangulation_check(objpoints, imgpoints0, imgpoints1, K0, D0, K1, D1, R, T):
    """
    Undistort detected corners to normalized coordinates, triangulate with
    P1=[I|0] (cam0/right at the world origin) and P2=[R|T] (cam1/left), then
    reproject the resulting 3D points back into both cameras with
    cv2.fisheye.projectPoints and compare against the original detections.
    """
    n = len(objpoints)
    sample_idx = sorted(set(np.linspace(0, n - 1, num=min(TRIANGULATION_SAMPLE_PAIRS, n), dtype=int).tolist()))

    rvec1, _ = cv2.Rodrigues(R)
    tvec1 = T.reshape(3, 1)
    rvec0 = np.zeros((3, 1))
    tvec0 = np.zeros((3, 1))

    print("Independent triangulation check (undistort -> triangulate -> reproject):")
    pair_means = []
    for i in sample_idx:
        pts0 = imgpoints0[i].reshape(-1, 2)
        pts1 = imgpoints1[i].reshape(-1, 2)

        pts3d = triangulate_points(pts0, pts1, K0, D0, K1, D1, R, T)

        reproj0, _ = cv2.fisheye.projectPoints(pts3d.reshape(-1, 1, 3), rvec0, tvec0, K0, D0)
        reproj1, _ = cv2.fisheye.projectPoints(pts3d.reshape(-1, 1, 3), rvec1, tvec1, K1, D1)

        err0 = np.linalg.norm(reproj0.reshape(-1, 2) - pts0.reshape(-1, 2), axis=1)
        err1 = np.linalg.norm(reproj1.reshape(-1, 2) - pts1.reshape(-1, 2), axis=1)
        pair_mean = float(np.mean(np.concatenate([err0, err1])))
        pair_means.append(pair_mean)
        print(f"  pair index {i}: mean reprojection error = {pair_mean:.4f} px "
              f"(cam0 {err0.mean():.4f} px, cam1 {err1.mean():.4f} px)")

    overall = float(np.mean(pair_means))
    verdict = "PASS" if overall < RMS_PASS_THRESHOLD_PX else "WARN"
    print(f"  Overall mean triangulation reprojection error: {overall:.4f} px [{verdict}]\n")
    return overall


def convergence_sweep(objpoints, imgpoints0, imgpoints1, K0, D0, K1, D1):
    """
    Diagnose whether the captured pose/tilt range sufficiently constrains the
    stereo extrinsic. RMS alone can look fine even when every pose was shot
    flat/face-on - the extrinsic can still be poorly constrained. Shuffles the
    KEPT pairs once (fixed seed) and re-solves cv2.fisheye.stereoCalibrate on
    growing prefixes of size N, tracking how the recovered baseline and RMS
    settle as N grows towards the full kept set.
    """
    n_total = len(objpoints)
    rng = np.random.default_rng(CONVERGENCE_SEED)
    order = rng.permutation(n_total)
    print(f"Baseline convergence sweep: kept-pair order shuffled with fixed seed {CONVERGENCE_SEED}.")

    objpoints_s = [objpoints[i] for i in order]
    imgpoints0_s = [imgpoints0[i] for i in order]
    imgpoints1_s = [imgpoints1[i] for i in order]

    n_values = list(range(min(CONVERGENCE_MIN_N, n_total), n_total + 1))
    baselines, rms_values = [], []

    for n in n_values:
        try:
            result = cv2.fisheye.stereoCalibrate(
                objpoints_s[:n], imgpoints0_s[:n], imgpoints1_s[:n],
                K0, D0, K1, D1,
                IMAGE_SIZE, flags=cv2.fisheye.CALIB_FIX_INTRINSIC, criteria=CRITERIA,
            )
            rms_n, T_n = result[0], result[6].reshape(3)
            baselines.append(float(np.linalg.norm(T_n)))
            rms_values.append(float(rms_n))
        except cv2.error:
            baselines.append(float("nan"))
            rms_values.append(float("nan"))

    print("\nBaseline convergence sweep (N pairs, shuffled order, intrinsics fixed):")
    print(f"  {'N':>3} | {'baseline_mm':>12} | {'rms_px':>8}")
    table_rows = []
    for n, b, r in zip(n_values, baselines, rms_values):
        b_str = f"{b:.2f}" if not np.isnan(b) else "FAILED"
        r_str = f"{r:.4f}" if not np.isnan(r) else "FAILED"
        print(f"  {n:>3} | {b_str:>12} | {r_str:>8}")
        table_rows.append(f"{n:>3} | {b_str:>12} | {r_str:>8}")

    # -- Plot ---------------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 8), sharex=True)

    ax1.plot(n_values, baselines, "-o", color="tab:blue", label="recovered baseline")
    ax1.axhline(EXPECTED_BASELINE_MM, color="tab:red", linestyle="--",
                label=f"expected ({EXPECTED_BASELINE_MM:.0f} mm)")
    ax1.set_ylabel("baseline |T| (mm)")
    ax1.set_title(f"Stereo extrinsic convergence vs N (shuffled, seed={CONVERGENCE_SEED})")
    ax1.legend()
    ax1.grid(alpha=0.3)

    ax2.plot(n_values, rms_values, "-o", color="tab:green")
    ax2.set_xlabel("N (pairs used, shuffled order)")
    ax2.set_ylabel("stereoCalibrate RMS (px)")
    ax2.grid(alpha=0.3)

    plt.tight_layout()
    CONVERGENCE_PLOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(CONVERGENCE_PLOT_PATH, dpi=150)
    plt.close(fig)
    print(f"\nSaved {CONVERGENCE_PLOT_PATH}")

    # -- Automatic read of the tail -------------------------------------------------
    valid = [(n, b) for n, b in zip(n_values, baselines) if not np.isnan(b)]
    verdict_lines = []
    if len(valid) < CONVERGENCE_LAST_K + 1:
        verdict = "INCONCLUSIVE"
        final_baseline = last_k_mean = last_k_spread = None
        print(f"\nNot enough successful solves to judge convergence (need at least "
              f"{CONVERGENCE_LAST_K + 1} valid N values).")
        verdict_lines.append("Convergence verdict: INCONCLUSIVE (too few successful solves)")
    else:
        last_k_baselines = [b for _, b in valid[-CONVERGENCE_LAST_K:]]
        final_baseline = valid[-1][1]
        last_k_mean = float(np.mean(last_k_baselines))
        last_k_spread = float(np.max(last_k_baselines) - np.min(last_k_baselines))
        final_pct_diff = 100.0 * abs(final_baseline - EXPECTED_BASELINE_MM) / EXPECTED_BASELINE_MM

        print(f"\nFinal N={valid[-1][0]} baseline = {final_baseline:.2f} mm; "
              f"mean of last {CONVERGENCE_LAST_K} = {last_k_mean:.2f} mm; "
              f"spread of last {CONVERGENCE_LAST_K} = {last_k_spread:.2f} mm")

        if last_k_spread < CONVERGENCE_SPREAD_TOL_MM and final_pct_diff < CONVERGENCE_BASELINE_TOL_PCT:
            verdict = "CONVERGED"
            print("CONVERGED - pose range appears sufficient.")
        else:
            verdict = "NOT CONVERGED"
            print("NOT CONVERGED - baseline still moving at the last pair; capture more")
            print("poses with varied PITCH (tip the board toward/away from the cameras),")
            print("not just more flat or same-tilt shots.")
        verdict_lines.append(f"Convergence verdict: {verdict}")
        verdict_lines.append(f"  Final N={valid[-1][0]} baseline={final_baseline:.2f} mm, "
                              f"last-{CONVERGENCE_LAST_K} mean={last_k_mean:.2f} mm, "
                              f"last-{CONVERGENCE_LAST_K} spread={last_k_spread:.2f} mm")
    print()

    return {
        "n_values": n_values,
        "baselines": baselines,
        "rms_values": rms_values,
        "table_rows": table_rows,
        "verdict": verdict,
        "verdict_lines": verdict_lines,
    }


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--capture-dir", default=str(CAPTURE_DIR),
                         help="Folder containing cam0/ and cam1/ matched checkerboard pairs "
                              "(default: data/2026_07_11_gym_session/extrinsic)")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR),
                         help="Folder to write stereo_extrinsic.npz/.txt and debug images into "
                              "(default: calibration_outputs/2026_07_11_session)")
    return parser.parse_args()


def main():
    global OUTPUT_DIR, CAPTURE_DIR, CAM0_DIR, CAM1_DIR
    global OUTPUT_NPZ, OUTPUT_TXT, DEBUG_CORNER0_CAM0, DEBUG_CORNER0_CAM1, CONVERGENCE_PLOT_PATH

    args = parse_args()
    CAPTURE_DIR = Path(args.capture_dir).resolve()
    OUTPUT_DIR = Path(args.output_dir).resolve()
    CAM0_DIR = CAPTURE_DIR / "cam0"
    CAM1_DIR = CAPTURE_DIR / "cam1"
    OUTPUT_NPZ = OUTPUT_DIR / "stereo_extrinsic.npz"
    OUTPUT_TXT = OUTPUT_DIR / "stereo_extrinsic.txt"
    DEBUG_CORNER0_CAM0 = OUTPUT_DIR / "corner_order_debug_cam0.png"
    DEBUG_CORNER0_CAM1 = OUTPUT_DIR / "corner_order_debug_cam1.png"
    CONVERGENCE_PLOT_PATH = OUTPUT_DIR / "extrinsic_convergence.png"

    print(f"Capture dir: {CAPTURE_DIR}")
    print(f"Output dir:  {OUTPUT_DIR}\n")
    print(f"Checkerboard: {PATTERN_SIZE[0]}x{PATTERN_SIZE[1]} internal corners, "
          f"square size = {SQUARE_SIZE_MM} mm (must be caliper-measured, not nominal)\n")

    K0, D0 = load_intrinsics(INTRINSICS_DIR / "cam0_intrinsics_fisheye.npz", "cam0 (right)")
    K1, D1 = load_intrinsics(INTRINSICS_DIR / "cam1_intrinsics_fisheye.npz", "cam1 (left)")
    print()

    pairs = find_matched_pairs()
    if not pairs:
        raise FileNotFoundError(f"No matched img_*.png pairs found in {CAM0_DIR} and {CAM1_DIR}")
    print(f"Found {len(pairs)} matched index(es).\n")

    objpoints, imgpoints0, imgpoints1 = [], [], []
    kept, skipped = [], []
    kept_paths = []  # (idx, path0, path1, c0, c1) per kept pair, for the corner-order debug image

    for idx, path0, path1 in pairs:
        g0 = cv2.imread(str(path0), cv2.IMREAD_GRAYSCALE)
        g1 = cv2.imread(str(path1), cv2.IMREAD_GRAYSCALE)
        if g0 is None or g1 is None:
            print(f"{idx}: SKIPPED (could not read image)")
            skipped.append(idx)
            continue

        found0, c0 = detect_corners(g0)
        found1, c1 = detect_corners(g1)
        if not (found0 and found1):
            missing = [name for name, found in (("cam0", found0), ("cam1", found1)) if not found]
            print(f"{idx}: SKIPPED (board not found in {', '.join(missing)})")
            skipped.append(idx)
            continue

        print(f"{idx}: KEPT")
        objpoints.append(OBJP.reshape(-1, 1, 3))
        imgpoints0.append(c0.astype(np.float64).reshape(-1, 1, 2))
        imgpoints1.append(c1.astype(np.float64).reshape(-1, 1, 2))
        kept.append(idx)
        kept_paths.append((idx, path0, path1, c0, c1))

    print(f"\nKept {len(kept)}/{len(pairs)} pairs ({len(skipped)} skipped).\n")
    if len(kept) < MIN_PAIRS_WARN:
        print(f"WARNING: only {len(kept)} pair(s) survived detection - fewer than the "
              f"recommended minimum of {MIN_PAIRS_WARN}. The stereo solve below may be "
              f"poorly conditioned; capture more varied poses if possible.\n")
    if len(kept) < 4:
        print("Not enough usable pairs to run stereoCalibrate (need at least a handful).")
        sys.exit(1)

    # -- Pose-consistency outlier rejection ---------------------------------------
    # Run even before the corner-order debug dump: a pose-outlier pair below could
    # itself be the corner-order-flip case that debug image is meant to catch.
    print("Checking per-pair pose consistency (independent mono solvePnP per view)...")
    outlier_positions, pose_outlier_lines = find_pose_outliers(kept, imgpoints0, imgpoints1, K0, D0, K1, D1)
    if outlier_positions:
        print(f"\nRemoved {len(outlier_positions)} pose-outlier pair(s) before stereoCalibrate.\n")
        keep_mask = [i for i in range(len(kept)) if i not in outlier_positions]
        kept = [kept[i] for i in keep_mask]
        objpoints = [objpoints[i] for i in keep_mask]
        imgpoints0 = [imgpoints0[i] for i in keep_mask]
        imgpoints1 = [imgpoints1[i] for i in keep_mask]
        kept_paths = [kept_paths[i] for i in keep_mask]
    else:
        print("No pose outliers found.\n")

    if len(kept) < 4:
        print("Not enough usable pairs left after pose-outlier rejection to run stereoCalibrate.")
        sys.exit(1)

    if kept_paths:
        save_corner0_debug(*kept_paths[0])

    # -- Stereo calibrate (fisheye, intrinsics FIXED) ----------------------------
    # cam0 (right) is the FIRST camera, cam1 (left) is the SECOND: R, T map the
    # cam0/right frame into the cam1/left frame (X_left = R @ X_right + T).
    flags = cv2.fisheye.CALIB_FIX_INTRINSIC
    try:
        result = cv2.fisheye.stereoCalibrate(
            objpoints, imgpoints0, imgpoints1,
            K0, D0, K1, D1,
            IMAGE_SIZE, flags=flags, criteria=CRITERIA,
        )
        # OpenCV builds vary between 7-tuple (retval,K1,D1,K2,D2,R,T) and
        # 9-tuple (adds per-pose rvecs, tvecs) - only R and T are needed here.
        rms, R, T = result[0], result[5], result[6]
    except cv2.error as e:
        print(f"\nERROR: cv2.fisheye.stereoCalibrate failed to converge: {e}")
        print("This is a common symptom of a corner-order mismatch between cam0/cam1")
        print("(check the corner-order debug images saved above), or of pairs that are")
        print("not actually the same simultaneous board pose (mismatched cam0/cam1")
        print("indices, or a pair captured non-simultaneously). Fix the correspondence")
        print("and re-run.")
        sys.exit(1)
    T = T.reshape(3)

    print("=" * 70)
    print("STEREO EXTRINSIC RESULT (cam0/right -> cam1/left)")
    print("=" * 70)

    rms_verdict = "PASS" if rms < RMS_PASS_THRESHOLD_PX else "WARN"
    print(f"stereoCalibrate RMS reprojection error: {rms:.4f} px "
          f"(threshold {RMS_PASS_THRESHOLD_PX} px) [{rms_verdict}]")
    if rms_verdict == "WARN":
        print("  WARNING: high RMS. The most likely cause is a corner-order mismatch")
        print("  between the cam0/cam1 views (e.g. one camera's detector started")
        print("  numbering from a different physical corner than the other). Check the")
        print("  corner-order debug images saved above - confirm corner 0 is the same")
        print("  physical corner in both. Also check for outlier poses (blur, board")
        print("  partially at the frame edge) among the kept pairs.")

    baseline_mm = float(np.linalg.norm(T))
    baseline_diff_pct = 100.0 * (baseline_mm - EXPECTED_BASELINE_MM) / EXPECTED_BASELINE_MM
    print(f"\nRecovered baseline |T| = {baseline_mm:.2f} mm "
          f"(expected ~{EXPECTED_BASELINE_MM:.0f} mm, {baseline_diff_pct:+.1f}%)")

    print(f"\nT vector (mm): x={T[0]:.2f}  y={T[1]:.2f}  z={T[2]:.2f}")
    dominant_axis = int(np.argmax(np.abs(T)))
    axis_name = ["x", "y", "z"][dominant_axis]
    print(f"  Dominant component: {axis_name} ({T[dominant_axis]:.2f} mm)")
    if dominant_axis != 0:
        print(f"  WARNING: for a horizontal side-by-side rig, the dominant baseline")
        print(f"  component is normally x, not {axis_name}. Check the rig mounting and")
        print(f"  the cam0=right / cam1=left convention above.")
    else:
        print("  This matches a horizontal side-by-side rig (dominant component is x).")
        print("  Sign convention: T maps cam0/right into cam1/left (X_left = R@X_right + T),")
        print("  so this is the right camera's position expressed in the left camera's frame.")

    print()
    triangulation_rms = triangulation_check(objpoints, imgpoints0, imgpoints1, K0, D0, K1, D1, R, T)

    # -- Save results -------------------------------------------------------------
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    np.savez(
        OUTPUT_NPZ,
        R=R, T=T, image_size=np.array(IMAGE_SIZE), square_size_mm=SQUARE_SIZE_MM,
        rms=rms, first_camera="cam0_right", second_camera="cam1_left",
    )
    print(f"Saved {OUTPUT_NPZ}")

    with open(OUTPUT_TXT, "w") as f:
        f.write("Stereo extrinsic calibration - fisheye rig\n")
        f.write("Convention: cam0 = RIGHT camera (first), cam1 = LEFT camera (second)\n")
        f.write("R, T map the cam0/right frame into the cam1/left frame: X_left = R @ X_right + T\n\n")
        f.write(f"Pairs kept / found: {len(kept)} / {len(pairs)}\n")
        f.write(f"Checkerboard: {PATTERN_SIZE[0]}x{PATTERN_SIZE[1]} internal corners, "
                f"square size = {SQUARE_SIZE_MM} mm\n\n")

        if skipped or pose_outlier_lines:
            f.write("-" * 70 + "\n")
            f.write("Anomalies (excluded from the solve)\n")
            f.write("-" * 70 + "\n")
            if skipped:
                f.write(f"Skipped, board not detected in at least one view ({len(skipped)}): "
                        f"{', '.join(skipped)}\n")
            if pose_outlier_lines:
                f.write(f"Removed as pose outliers ({len(pose_outlier_lines)}) - detection succeeded in "
                        f"both views but the implied cam0->cam1 rigid transform for that pair did not "
                        f"match the rest of the session (see POSE_OUTLIER_* thresholds in the script):\n")
                for line in pose_outlier_lines:
                    f.write(f"{line}\n")
            f.write("\n")

        f.write(f"stereoCalibrate RMS reprojection error: {rms:.4f} px [{rms_verdict}]\n")
        f.write(f"Independent triangulation mean reprojection error: {triangulation_rms:.4f} px\n\n")
        f.write(f"Baseline |T| = {baseline_mm:.2f} mm (expected ~{EXPECTED_BASELINE_MM:.0f} mm, "
                f"{baseline_diff_pct:+.1f}%)\n")
        f.write(f"T (mm): x={T[0]:.4f} y={T[1]:.4f} z={T[2]:.4f}\n\n")
        f.write("R:\n")
        f.write(f"{R}\n")
    print(f"Saved {OUTPUT_TXT}")

    # -- Baseline convergence sweep (diagnoses pose/tilt range, not just RMS) -----
    conv = convergence_sweep(objpoints, imgpoints0, imgpoints1, K0, D0, K1, D1)

    with open(OUTPUT_TXT, "a") as f:
        f.write("\n" + "=" * 70 + "\n")
        f.write(f"Baseline convergence sweep (kept pairs shuffled, seed={CONVERGENCE_SEED})\n")
        f.write("=" * 70 + "\n")
        f.write(f"{'N':>3} | {'baseline_mm':>12} | {'rms_px':>8}\n")
        for row in conv["table_rows"]:
            f.write(f"{row}\n")
        f.write("\n")
        for line in conv["verdict_lines"]:
            f.write(f"{line}\n")
    print(f"Appended convergence sweep to {OUTPUT_TXT}")


if __name__ == "__main__":
    main()
