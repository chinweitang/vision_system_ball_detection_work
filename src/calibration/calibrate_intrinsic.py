"""
Calibrate a single camera's intrinsics from a checkerboard image set, running
BOTH the pinhole (rational) and fisheye models so you can pick the better one
from evidence (RMS error, per-image outliers, undistort comparison) - this
script does not pick a winner for you.

Run from anywhere:
    python src/calibration/calibrate_intrinsic.py [camA|camB|<path>] [test_image]

  camA/camB/<path>  Which capture set to calibrate (default camA), i.e.
                    ..\\..\\data\\calibration_captures\\calib_intrinsic_camA\\
                    relative to this script, or a full path to another folder.
  test_image        Filename (e.g. img_0015.png) or full path of the frame to
                    undistort for the side-by-side comparison. Defaults to the
                    middle image of the successfully-detected set.

Outputs (written into the image folder):
  - cam_intrinsics_pinhole.npz  (K, dist, rms, image_size)
  - cam_intrinsics_fisheye.npz  (K, D, rms, image_size)
  - undistort_compare.png       (original / pinhole / fisheye, side by side)
Plus console output: usable-image count, both models' overall RMS, both
intrinsic matrices + distortion coeffs, and a per-image reprojection-error
table (sorted worst-first) to spot outlier frames.
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
import matplotlib.pyplot as plt

PATTERN_SIZE = (7, 11)  # internal corners (columns, rows)
SQUARE_SIZE_MM = 67.5

OBJP = np.zeros((PATTERN_SIZE[0] * PATTERN_SIZE[1], 3), np.float64)
OBJP[:, :2] = np.mgrid[0:PATTERN_SIZE[0], 0:PATTERN_SIZE[1]].T.reshape(-1, 2) * SQUARE_SIZE_MM

CRITERIA = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-6)


def detect_corners(gray):
    """
    Detect the PATTERN_SIZE internal chessboard corners in a grayscale image.
    Tries findChessboardCornersSB first (already sub-pixel accurate, robust to
    the fisheye distortion at frame edges); falls back to the classic
    detector + cornerSubPix only if SB fails. Same block as check_coverage.py.

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


def resolve_image_dir(target):
    root = Path(__file__).resolve().parents[2]
    candidate = Path(target)
    if candidate.is_dir():
        return candidate.resolve()
    return (root / "data/calibration_captures" / f"calib_intrinsic_{target}").resolve()


def per_image_errors_pinhole(objpoints, imgpoints, rvecs, tvecs, K, dist):
    errors = []
    for op, ip, rvec, tvec in zip(objpoints, imgpoints, rvecs, tvecs):
        projected, _ = cv2.projectPoints(op, rvec, tvec, K, dist)
        err = cv2.norm(ip, projected, cv2.NORM_L2) / np.sqrt(len(projected))
        errors.append(err)
    return errors


def per_image_errors_fisheye(objpoints, imgpoints, rvecs, tvecs, K, D):
    errors = []
    for op, ip, rvec, tvec in zip(objpoints, imgpoints, rvecs, tvecs):
        projected, _ = cv2.fisheye.projectPoints(op.reshape(1, -1, 3), rvec, tvec, K, D)
        projected = projected.reshape(-1, 1, 2)
        err = cv2.norm(ip, projected, cv2.NORM_L2) / np.sqrt(len(projected))
        errors.append(err)
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", nargs="?", default="camA",
                         help="camA / camB, or a full path to the image folder")
    parser.add_argument("test_image", nargs="?", default=None,
                         help="Filename or path of the frame to undistort (default: middle of the set)")
    args = parser.parse_args()

    image_dir = resolve_image_dir(args.target)
    image_paths = sorted(image_dir.glob("img_*.png"))
    if not image_paths:
        raise FileNotFoundError(f"No img_*.png frames found in: {image_dir}")

    print(f"Calibrating from: {image_dir}")
    print(f"Found {len(image_paths)} image(s).\n")

    objpoints, imgpoints, used_paths, failed = [], [], [], []
    image_size = None

    for path in image_paths:
        gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if gray is None:
            failed.append(path.name)
            continue

        found, corners = detect_corners(gray)
        if not found:
            failed.append(path.name)
            continue

        if image_size is None:
            image_size = gray.shape[::-1]  # (width, height)

        objpoints.append(OBJP.astype(np.float32).reshape(-1, 1, 3))
        imgpoints.append(corners.astype(np.float32).reshape(-1, 1, 2))
        used_paths.append(path)

    print(f"Usable: {len(used_paths)}/{len(image_paths)} images ({len(failed)} failed detection)")
    if failed:
        print("Failed detection (skipped):")
        for name in failed:
            print(f"  - {name}")
    print()

    if len(used_paths) < 4:
        print("Not enough usable images to calibrate (need at least a handful of varied poses).")
        sys.exit(1)

    # -- Pinhole (rational model: k1..k6, p1, p2) ------------------------------
    print("Calibrating pinhole (rational) model...")
    rms_pinhole, K_pinhole, dist_pinhole, rvecs_pinhole, tvecs_pinhole = cv2.calibrateCamera(
        objpoints, imgpoints, image_size, None, None,
        flags=cv2.CALIB_RATIONAL_MODEL, criteria=CRITERIA,
    )
    print(f"  Pinhole RMS reprojection error: {rms_pinhole:.4f} px\n")

    # -- Fisheye ----------------------------------------------------------------
    print("Calibrating fisheye model...")
    objpoints_fe = [op.astype(np.float64) for op in objpoints]
    imgpoints_fe = [ip.astype(np.float64) for ip in imgpoints]
    K_fe = np.zeros((3, 3))
    D_fe = np.zeros((4, 1))

    flags_fisheye = (
        cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC
        | cv2.fisheye.CALIB_FIX_SKEW
        | cv2.fisheye.CALIB_CHECK_COND
    )
    try:
        rms_fisheye, K_fe, D_fe, rvecs_fisheye, tvecs_fisheye = cv2.fisheye.calibrate(
            objpoints_fe, imgpoints_fe, image_size, K_fe, D_fe,
            flags=flags_fisheye, criteria=CRITERIA,
        )
    except cv2.error as e:
        print(f"  CALIB_CHECK_COND rejected an ill-conditioned frame ({e}); retrying without it.")
        flags_fisheye = cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC | cv2.fisheye.CALIB_FIX_SKEW
        K_fe = np.zeros((3, 3))
        D_fe = np.zeros((4, 1))
        rms_fisheye, K_fe, D_fe, rvecs_fisheye, tvecs_fisheye = cv2.fisheye.calibrate(
            objpoints_fe, imgpoints_fe, image_size, K_fe, D_fe,
            flags=flags_fisheye, criteria=CRITERIA,
        )
    print(f"  Fisheye RMS reprojection error: {rms_fisheye:.4f} px\n")

    # -- Per-image reprojection error table --------------------------------------
    errors_pinhole = per_image_errors_pinhole(objpoints, imgpoints, rvecs_pinhole, tvecs_pinhole, K_pinhole, dist_pinhole)
    errors_fisheye = per_image_errors_fisheye(objpoints_fe, imgpoints_fe, rvecs_fisheye, tvecs_fisheye, K_fe, D_fe)

    rows = list(zip(used_paths, errors_pinhole, errors_fisheye))
    rows.sort(key=lambda r: max(r[1], r[2]), reverse=True)

    print(f"{'filename':<20}{'pinhole (px)':>15}{'fisheye (px)':>15}")
    for path, e_pin, e_fe in rows:
        print(f"{path.name:<20}{e_pin:>15.4f}{e_fe:>15.4f}")
    print()

    # -- Undistort comparison -----------------------------------------------------
    if args.test_image:
        candidate = Path(args.test_image)
        test_path = candidate if candidate.is_file() else image_dir / args.test_image
    else:
        test_path = used_paths[len(used_paths) // 2]

    if not test_path.is_file():
        raise FileNotFoundError(f"Test image not found: {test_path}")

    print(f"Undistorting test image: {test_path.name}")
    test_img = cv2.imread(str(test_path), cv2.IMREAD_GRAYSCALE)

    new_K_pinhole, _ = cv2.getOptimalNewCameraMatrix(K_pinhole, dist_pinhole, image_size, alpha=1)
    undistorted_pinhole = cv2.undistort(test_img, K_pinhole, dist_pinhole, None, new_K_pinhole)

    new_K_fisheye = cv2.fisheye.estimateNewCameraMatrixForUndistortRectify(
        K_fe, D_fe, image_size, np.eye(3), balance=1.0,
    )
    map1, map2 = cv2.fisheye.initUndistortRectifyMap(
        K_fe, D_fe, np.eye(3), new_K_fisheye, image_size, cv2.CV_16SC2,
    )
    undistorted_fisheye = cv2.remap(test_img, map1, map2, interpolation=cv2.INTER_LINEAR)

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    for ax, img, title in zip(
        axes,
        [test_img, undistorted_pinhole, undistorted_fisheye],
        ["Original", "Pinhole (rational) undistorted", "Fisheye undistorted"],
    ):
        ax.imshow(img, cmap="gray")
        ax.set_title(title)
        ax.axis("off")
    plt.tight_layout()
    compare_path = image_dir / "undistort_compare.png"
    plt.savefig(compare_path, dpi=150)
    print(f"Saved undistort comparison to: {compare_path}\n")

    # -- Print + save results ------------------------------------------------------
    print("Pinhole intrinsic matrix (K):")
    print(K_pinhole)
    print("Pinhole distortion coeffs (k1,k2,p1,p2,k3,k4,k5,k6):")
    print(dist_pinhole.ravel())
    print()

    print("Fisheye intrinsic matrix (K):")
    print(K_fe)
    print("Fisheye distortion coeffs (k1,k2,k3,k4):")
    print(D_fe.ravel())
    print()

    np.savez(
        image_dir / "cam_intrinsics_pinhole.npz",
        K=K_pinhole, dist=dist_pinhole, rms=rms_pinhole, image_size=image_size,
    )
    np.savez(
        image_dir / "cam_intrinsics_fisheye.npz",
        K=K_fe, D=D_fe, rms=rms_fisheye, image_size=image_size,
    )
    print(f"Saved cam_intrinsics_pinhole.npz and cam_intrinsics_fisheye.npz to: {image_dir}")


if __name__ == "__main__":
    main()
