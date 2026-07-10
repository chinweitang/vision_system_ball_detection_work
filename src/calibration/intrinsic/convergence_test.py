"""
Convergence / overfitting check for the FISHEYE intrinsic model: sweeps the
number of training images N, and at each N draws several random train/held-out
splits, calibrating on the train subset and measuring reprojection error on
the held-out (validation) images. Confirms whether enough images were
captured (validation error and parameters stop moving) and whether the fit is
overfitting (train error much lower than held-out error).

Run from anywhere:
    python src/calibration/intrinsic/convergence_test.py [camA|camB|<path>]

Defaults to camA, i.e. ..\\..\\..\\data\\calibration_captures\\calib_intrinsic_camA\\
relative to this script.

Output (written into the image folder): convergence_camA.png (or _camB), plus
a console verdict on the "enough images" point and the train/validation gap.
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

N_LIST = [3, 5, 8, 12, 16, 20, 25, 30, 35, 40]
DRAWS_PER_N = 8
MAX_ATTEMPTS_FACTOR = 3  # give up on a draw slot after this many failed redraws
PLATEAU_TOLERANCE = 0.05  # "enough images" = within 5% of the best observed validation mean
SEED = 42


def detect_corners(gray):
    """
    Detect the PATTERN_SIZE internal chessboard corners in a grayscale image.
    Same block as check_coverage.py / calibrate_intrinsic.py: SB first (already
    sub-pixel accurate), classic detector + cornerSubPix only as a fallback.
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
    root = Path(__file__).resolve().parents[3]
    candidate = Path(target)
    if candidate.is_dir():
        return candidate.resolve()
    return (root / "data/calibration_captures" / f"calib_intrinsic_{target}").resolve()


def calibrate_fisheye(objpoints, imgpoints, image_size):
    """Fisheye calibrate with CALIB_CHECK_COND, dropping it on ill-conditioning."""
    flags = cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC | cv2.fisheye.CALIB_FIX_SKEW | cv2.fisheye.CALIB_CHECK_COND
    K = np.zeros((3, 3))
    D = np.zeros((4, 1))
    try:
        rms, K, D, _, _ = cv2.fisheye.calibrate(objpoints, imgpoints, image_size, K, D, flags=flags, criteria=CRITERIA)
        return rms, K, D
    except cv2.error:
        flags = cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC | cv2.fisheye.CALIB_FIX_SKEW
        K = np.zeros((3, 3))
        D = np.zeros((4, 1))
        rms, K, D, _, _ = cv2.fisheye.calibrate(objpoints, imgpoints, image_size, K, D, flags=flags, criteria=CRITERIA)
        return rms, K, D


def solve_pnp_fisheye(objp, imgp, K, D):
    """Pose of one held-out board under a fixed fisheye intrinsic model: undistort
    its corners into rectified pixel space, then solvePnP there (zero distortion)."""
    imgp64 = imgp.reshape(1, -1, 2).astype(np.float64)
    rectified = cv2.fisheye.undistortPoints(imgp64, K, D, P=K).reshape(-1, 1, 2)
    ok, rvec, tvec = cv2.solvePnP(objp.astype(np.float64), rectified, K, None)
    return ok, rvec, tvec


def fisheye_reproj_error(objp, imgp, rvec, tvec, K, D):
    projected, _ = cv2.fisheye.projectPoints(objp.reshape(1, -1, 3), rvec, tvec, K, D)
    projected = projected.reshape(-1, 1, 2)
    err = cv2.norm(imgp.reshape(-1, 1, 2).astype(np.float64), projected, cv2.NORM_L2) / np.sqrt(len(projected))
    return err


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", nargs="?", default="camA",
                         help="camA / camB, or a full path to the image folder")
    args = parser.parse_args()

    image_dir = resolve_image_dir(args.target)
    image_paths = sorted(image_dir.glob("img_*.png"))
    if not image_paths:
        raise FileNotFoundError(f"No img_*.png frames found in: {image_dir}")

    print(f"Loading from: {image_dir}")
    print(f"Found {len(image_paths)} image(s).\n")

    objpoints_all, imgpoints_all = [], []
    image_size = None
    failed = []
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
            image_size = gray.shape[::-1]
        objpoints_all.append(OBJP.copy())
        imgpoints_all.append(corners.astype(np.float64))

    usable_count = len(objpoints_all)
    print(f"Usable: {usable_count}/{len(image_paths)} images ({len(failed)} failed detection)\n")
    if usable_count < 4:
        print("Not enough usable images for a convergence sweep.")
        sys.exit(1)

    n_list = sorted(set(n for n in N_LIST if n <= usable_count))
    if usable_count not in n_list:
        n_list.append(usable_count)

    rng = np.random.default_rng(SEED)
    results = {}

    for n in n_list:
        full_set = n >= usable_count
        draws_needed = 1 if full_set else DRAWS_PER_N
        max_attempts = draws_needed * MAX_ATTEMPTS_FACTOR
        successes = []
        attempts = 0

        while len(successes) < draws_needed and attempts < max_attempts:
            attempts += 1
            if full_set:
                train_idx = np.arange(usable_count)
            else:
                train_idx = rng.choice(usable_count, size=n, replace=False)
            train_set = set(train_idx.tolist())

            train_obj = [objpoints_all[i] for i in train_idx]
            train_img = [imgpoints_all[i].reshape(-1, 1, 2) for i in train_idx]
            train_obj_3d = [o.reshape(-1, 1, 3) for o in train_obj]

            try:
                rms_train, K, D = calibrate_fisheye(train_obj_3d, train_img, image_size)
            except cv2.error:
                continue  # ill-conditioned / degenerate subset - redraw

            held_idx = [i for i in range(usable_count) if i not in train_set]
            val_errors = []
            for i in held_idx:
                ok, rvec, tvec = solve_pnp_fisheye(objpoints_all[i], imgpoints_all[i], K, D)
                if not ok:
                    continue
                val_errors.append(fisheye_reproj_error(objpoints_all[i], imgpoints_all[i], rvec, tvec, K, D))

            val_mean = float(np.mean(val_errors)) if val_errors else np.nan
            val_max = float(np.max(val_errors)) if val_errors else np.nan

            successes.append(dict(
                train_rms=rms_train, val_mean=val_mean, val_max=val_max,
                fx=K[0, 0], fy=K[1, 1], cx=K[0, 2], cy=K[1, 2],
                k1=D[0, 0], k2=D[1, 0], k3=D[2, 0], k4=D[3, 0],
            ))

        results[n] = successes
        note = "" if attempts == len(successes) else f" ({attempts} attempts)"
        print(f"N={n:>2}: {len(successes)}/{draws_needed} successful draws{note}")

    print()

    # -- Aggregate median + IQR per N for each metric ----------------------------
    # Median/IQR rather than mean/std: small-N draws occasionally produce a
    # badly-conditioned fit whose held-out error is enormous, and a mean/std
    # band gets dominated by that single outlier draw.
    metrics = ["train_rms", "val_mean", "val_max", "fx", "fy", "cx", "cy", "k1", "k2", "k3", "k4"]
    agg = {m: {"n": [], "mean": [], "lo": [], "hi": []} for m in metrics}
    for n in n_list:
        rows = results[n]
        if not rows:
            continue
        for m in metrics:
            vals = np.array([r[m] for r in rows], dtype=float)
            if np.all(np.isnan(vals)):
                continue
            agg[m]["n"].append(n)
            agg[m]["mean"].append(np.nanmedian(vals))
            agg[m]["lo"].append(np.nanpercentile(vals, 25))
            agg[m]["hi"].append(np.nanpercentile(vals, 75))
    for m in metrics:
        for k in ("n", "mean", "lo", "hi"):
            agg[m][k] = np.array(agg[m][k])

    # -- Plot ---------------------------------------------------------------------
    fig, axes = plt.subplots(4, 1, figsize=(9, 16))

    ax = axes[0]
    for m, label, style in [("train_rms", "training (median)", "-"), ("val_mean", "validation mean (median)", "-"), ("val_max", "validation max (median)", "--")]:
        n_arr, mean_arr, lo_arr, hi_arr = agg[m]["n"], agg[m]["mean"], agg[m]["lo"], agg[m]["hi"]
        if len(n_arr) == 0:
            continue
        ax.plot(n_arr, mean_arr, style, label=label, marker="o")
        ax.fill_between(n_arr, lo_arr, hi_arr, alpha=0.2)
    ax.set_yscale("log")
    ax.set_xlabel("N (training images)")
    ax.set_ylabel("reprojection error (px, log scale)")
    ax.set_title(f"Fisheye convergence - {args.target} ({usable_count} usable images)")
    ax.legend()
    ax.grid(alpha=0.3, which="both")

    ax = axes[1]
    for m, label in [("fx", "fx"), ("fy", "fy")]:
        n_arr, mean_arr, lo_arr, hi_arr = agg[m]["n"], agg[m]["mean"], agg[m]["lo"], agg[m]["hi"]
        ax.plot(n_arr, mean_arr, "-", label=label, marker="o")
        ax.fill_between(n_arr, lo_arr, hi_arr, alpha=0.2)
    ax.set_xlabel("N (training images)")
    ax.set_ylabel("focal length (px)")
    ax.set_title("Focal length stability (median + IQR)")
    ax.legend()
    ax.grid(alpha=0.3)

    ax = axes[2]
    for m, label in [("cx", "cx"), ("cy", "cy")]:
        n_arr, mean_arr, lo_arr, hi_arr = agg[m]["n"], agg[m]["mean"], agg[m]["lo"], agg[m]["hi"]
        ax.plot(n_arr, mean_arr, "-", label=label, marker="o")
        ax.fill_between(n_arr, lo_arr, hi_arr, alpha=0.2)
    ax.set_xlabel("N (training images)")
    ax.set_ylabel("principal point (px)")
    ax.set_title("Principal point stability (median + IQR)")
    ax.legend()
    ax.grid(alpha=0.3)

    ax = axes[3]
    for m in ["k1", "k2", "k3", "k4"]:
        n_arr, mean_arr, lo_arr, hi_arr = agg[m]["n"], agg[m]["mean"], agg[m]["lo"], agg[m]["hi"]
        ax.plot(n_arr, mean_arr, "-", label=m, marker="o")
        ax.fill_between(n_arr, lo_arr, hi_arr, alpha=0.2)
    ax.set_xlabel("N (training images)")
    ax.set_ylabel("distortion coeff")
    ax.set_title("Fisheye distortion coefficients (k1..k4) stability (median + IQR)")
    ax.legend()
    ax.grid(alpha=0.3)

    plt.tight_layout()
    out_path = image_dir / f"convergence_{args.target}.png"
    plt.savefig(out_path, dpi=150)
    print(f"Saved convergence report to: {out_path}\n")

    # -- Verdict --------------------------------------------------------------------
    val_n, val_mean_arr = agg["val_mean"]["n"], agg["val_mean"]["mean"]
    if len(val_n) == 0:
        print("No held-out validation data was collected - cannot judge convergence.")
        return

    best_val = float(np.min(val_mean_arr))
    plateau_n = int(val_n[np.argmax(val_mean_arr <= best_val * (1 + PLATEAU_TOLERANCE))])

    final_n = int(val_n[-1])
    final_val_mean = float(val_mean_arr[-1])
    train_n, train_mean_arr = agg["train_rms"]["n"], agg["train_rms"]["mean"]
    final_train_mean = float(train_mean_arr[np.where(train_n == final_n)[0][0]])
    gap = final_val_mean - final_train_mean
    gap_ratio = gap / final_train_mean if final_train_mean > 0 else float("nan")

    print(f"Validation error plateaus by N={plateau_n} (within {PLATEAU_TOLERANCE*100:.0f}% of the best "
          f"observed validation mean, {best_val:.4f} px). More images beyond this point buy little.")
    print(f"At N={final_n}: training RMS={final_train_mean:.4f} px, validation mean={final_val_mean:.4f} px, "
          f"gap={gap:.4f} px ({gap_ratio*100:.1f}% of training error).")
    if gap_ratio > 0.5:
        print("Validation error is notably higher than training error - possible overfitting; "
              "consider more/varied images or check for degenerate poses.")
    else:
        print("Validation error is close to training error - no strong sign of overfitting.")


if __name__ == "__main__":
    main()
